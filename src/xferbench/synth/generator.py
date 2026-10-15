"""Deterministic synthetic retail cold-pair data.

Order of construction: entities -> donor offers -> natural launch events -> latent demand ->
observed sales under exposure/stock limits -> company-style origin features computed by the
engine's own origin-scoped context builder (so P, rank and affinity never see hidden truth).

Hidden truth (true rates, affinities, seasonal curves, bursts, latent demand) is written only to
``_synthetic_truth/`` and is never referenced by metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from xferbench.calendar import WEEK, cycle_week, to_ts, week_range
from xferbench.contracts.metadata import (
    CohortSpec,
    DatasetInfo,
    FeatureSpec,
    Metadata,
    Rights,
    StageWindow,
    TableSource,
    TimeSpec,
)
from xferbench.contracts.tables import TABLES
from xferbench.data.io import Dataset, load_dataset
from xferbench.features.aggregates import national_rates, pair_rates
from xferbench.features.context import ContextBuilder, Exclusions
from xferbench.synth.presets import SynthConfig
from xferbench.util import atomic_write_csv, atomic_write_text, hash_frame, hash_obj, write_json

CLUSTERS = ("families", "young_adults", "seniors", "students")
SHARE_COLUMNS = [f"share_{c}" for c in CLUSTERS]
REGIONS = ("north", "south", "east", "west")
# name, seasonality class, amplitude, peak cycle week
CATEGORIES = (
    ("garden", "seasonal", 0.9, 26),
    ("winter_care", "seasonal", 0.8, 2),
    ("pantry", "replenishable", 0.12, 48),
    ("household", "replenishable", 0.1, 12),
)
FIXTURE_CATEGORY = ("gift_sets", "seasonal", 1.0, 50)
STAGES = ("train", "validation", "test")
FEATURE_VERSION = "synthetic_company_features_v1"
TRUTH_DIR = "_synthetic_truth"


@dataclass
class _Entities:
    items: pd.DataFrame
    fpgs: pd.DataFrame
    stage_origins: dict[str, list[pd.Timestamp]]


def _seasonal_curve(amplitude: float, peak: int) -> np.ndarray:
    w = np.arange(1, 53)
    s = np.exp(amplitude * np.cos(2 * np.pi * (w - peak) / 52))
    return s / s.mean()


def _entities(cfg: SynthConfig, rng: np.random.Generator) -> _Entities:
    n = cfg.n_items
    cat_idx = np.arange(n) % len(CATEGORIES)
    rng.shuffle(cat_idx)
    rows = []
    for i in range(n):
        name, cls, amp, peak = CATEGORIES[cat_idx[i]]
        rows.append(
            {
                "item_id": f"{100 + i:06d}",
                "category": name,
                "seasonality_class": cls,
                "product_type": f"{name}_{'ab'[int(rng.integers(2))]}",
                "amp": amp,
                "peak": peak,
                "fixture": False,
            }
        )
    if cfg.include_edge_fixtures:
        name, cls, amp, peak = FIXTURE_CATEGORY
        rows.append(
            {
                "item_id": f"{100 + n:06d}",
                "category": name,
                "seasonality_class": cls,
                "product_type": f"{name}_a",
                "amp": amp,
                "peak": peak,
                "fixture": True,
            }
        )
    items = pd.DataFrame(rows)
    m = len(items)
    items["true_rate"] = rng.lognormal(0.0, 0.7, m)
    items["true_gate"] = rng.beta(3.0, 1.5, m)
    items["true_trend"] = rng.normal(0.0, 0.04, m)
    items["true_amp"] = items["amp"] * (1 + rng.normal(0, 0.1, m))

    stage_origins: dict[str, list[pd.Timestamp]] = {}
    for s in STAGES:
        lo, hi = cfg.stage_windows[s]
        mondays = week_range(lo, hi)
        k = min(cfg.origins_per_stage[s], len(mondays))
        idx = np.unique(np.linspace(0, len(mondays) - 1, k).round().astype(int))
        stage_origins[s] = [mondays[j] for j in idx]

    def fpg_row(fid: str, open_at: pd.Timestamp | None, stage: str | None, fixture: bool = False) -> dict:
        shares = rng.dirichlet([2.0] * len(CLUSTERS))
        return {
            "fpg_id": fid,
            "region": REGIONS[int(rng.integers(len(REGIONS)))],
            "households": float(round(rng.lognormal(np.log(cfg.households_median), 0.5))),
            "fpg_open_at": open_at,
            "new_in_stage": stage,
            "fixture": fixture,
            **{c: float(v) for c, v in zip(SHARE_COLUMNS, shares, strict=True)},
        }

    fpgs = [fpg_row(f"F{j + 1:03d}", None, None) for j in range(cfg.n_established_fpgs)]
    for s in STAGES:
        origins = list(stage_origins[s])
        order = rng.permutation(len(origins))
        for j in range(cfg.new_fpgs[s]):
            fpgs.append(fpg_row(f"N-{s[:3].upper()}-{j + 1:02d}", origins[order[j % len(origins)]], s))
    if cfg.include_edge_fixtures:
        fpgs.append(fpg_row("NX-FIX-01", stage_origins["test"][0], "test", fixture=True))
    return _Entities(items, pd.DataFrame(fpgs), stage_origins)


def _pairs(cfg: SynthConfig, ent: _Entities, rng: np.random.Generator) -> pd.DataFrame:
    items, fpgs = ent.items, ent.fpgs
    est = fpgs[fpgs["new_in_stage"].isna()].reset_index(drop=True)
    normal_items = items[~items["fixture"]]["item_id"].tolist()
    rows: list[dict] = []
    used: set[tuple[str, str]] = set()
    for it in items["item_id"]:
        offered = rng.random(len(est)) < cfg.donor_offer_prob
        if offered.sum() < cfg.min_donor_fpgs_per_item:
            offered[rng.choice(len(est), cfg.min_donor_fpgs_per_item, replace=False)] = True
        for f in est.loc[offered, "fpg_id"]:
            rows.append({"item_id": it, "fpg_id": f, "kind": "donor", "start": to_ts(cfg.history_start)})
            used.add((it, f))

    launch_no = 0

    def add_launch(
        item: str,
        fpg: str,
        origin: pd.Timestamp,
        stage: str,
        scenario: str,
        fixture_kind: str | None = None,
        first_offer_at: pd.Timestamp | None = None,
    ) -> None:
        nonlocal launch_no
        launch_no += 1
        lid = f"L-FX-{fixture_kind}" if fixture_kind else f"L-{stage[:3].upper()}-{launch_no:04d}"
        rows.append(
            {
                "item_id": item,
                "fpg_id": fpg,
                "kind": "launch",
                "start": origin,
                "launch_id": lid,
                "stage": stage,
                "scenario": scenario,
                "fixture_kind": fixture_kind,
                "first_offer_at": first_offer_at if first_offer_at is not None else origin,
            }
        )
        used.add((item, fpg))

    for s in STAGES:
        first = ent.stage_origins[s][0]
        open_before = fpgs[fpgs["new_in_stage"].isna() | (fpgs["fpg_open_at"] < first - 52 * WEEK)]
        open_before = open_before[~open_before["fixture"]]
        cands = [(i, f) for i in normal_items for f in open_before["fpg_id"] if (i, f) not in used]
        pick = rng.choice(len(cands), min(cfg.e_launches[s], len(cands)), replace=False)
        for j in sorted(pick):
            i, f = cands[j]
            add_launch(i, f, ent.stage_origins[s][int(rng.integers(len(ent.stage_origins[s])))], s, "PAIR0-E")
        for nf in fpgs[(fpgs["new_in_stage"] == s) & ~fpgs["fixture"]].itertuples(index=False):
            for i in rng.choice(normal_items, min(cfg.items_per_new_fpg, len(normal_items)), replace=False):
                add_launch(str(i), nf.fpg_id, nf.fpg_open_at, s, "PAIR0-N")

    if cfg.include_edge_fixtures:
        o = ent.stage_origins["test"][0]
        est_ids = est["fpg_id"].tolist()
        fixture_item = items[items["fixture"]]["item_id"].iloc[0]

        def free_pair(item_pool: list[str]) -> tuple[str, str]:
            for _ in range(10_000):
                i = str(rng.choice(item_pool))
                f = str(rng.choice(est_ids))
                if (i, f) not in used:
                    return i, f
            raise RuntimeError("no free pair for edge fixture")

        for kind in ("partial_week", "stockout_heavy", "missing_targets", "missing_propensity"):
            i, f = free_pair(normal_items)
            add_launch(i, f, o, "test", "PAIR0-E", kind, o + pd.Timedelta(days=2) if kind == "partial_week" else o)
        i, f = free_pair([fixture_item])
        add_launch(i, f, o, "test", "PAIR0-E", "unseen_category")
        add_launch(str(rng.choice(normal_items)), "NX-FIX-01", o, "test", "PAIR0-N", "unknown_attributes")

    pairs = pd.DataFrame(rows)
    for c in ("launch_id", "stage", "scenario", "fixture_kind", "first_offer_at"):
        if c not in pairs:
            pairs[c] = None
    is_launch = (pairs["kind"] == "launch") & pairs["fixture_kind"].isna()
    dead = is_launch & (rng.random(len(pairs)) < cfg.dead_pair_fraction)
    pairs["dead"] = dead
    return pairs


def _household_versions(fpgs: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for f in fpgs.itertuples(index=False):
        if pd.isna(f.fpg_open_at):
            eff = to_ts("2018-01-01")
            rows.append({"fpg_id": f.fpg_id, "effective_from": eff, "known_at": eff, "households": f.households})
            h2 = float(round(f.households * (1 + rng.normal(0, 0.04))))
            rows.append(
                {
                    "fpg_id": f.fpg_id,
                    "effective_from": to_ts("2024-01-01"),
                    "known_at": to_ts("2023-12-18"),
                    "households": h2,
                }
            )
        else:
            eff = f.fpg_open_at - pd.Timedelta(days=28)
            rows.append({"fpg_id": f.fpg_id, "effective_from": eff, "known_at": eff, "households": f.households})
    return pd.DataFrame(rows)


def _expected_zero(alpha: float, base_mu: np.ndarray, gate: np.ndarray, k: float) -> float:
    m = alpha * base_mu / gate
    return float(np.mean((1 - gate) + gate * (k / (k + m)) ** k))


def _calibrate_alpha(base_mu: np.ndarray, gate: np.ndarray, k: float, target: float) -> float:
    lo, hi = -14.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _expected_zero(np.exp(mid), base_mu, gate, k) > target:
            lo = mid
        else:
            hi = mid
    return float(np.exp((lo + hi) / 2))


def _simulate(
    cfg: SynthConfig, ent: _Entities, pairs: pd.DataFrame, hh_versions: pd.DataFrame, rng: np.random.Generator
) -> tuple[pd.DataFrame, dict]:
    weeks = pd.DatetimeIndex(week_range(cfg.history_start, cfg.last_week))
    T = len(weeks)
    woy = cycle_week(weeks)
    years = np.asarray((weeks - weeks[0]).days, dtype=float) / 365.25
    items = ent.items.set_index("item_id")
    fpgs = ent.fpgs.set_index("fpg_id")
    item_pos = {it: j for j, it in enumerate(items.index)}

    beta_cat = {c[0]: rng.normal(0, 0.6, len(CLUSTERS)) for c in (*CATEGORIES, FIXTURE_CATEGORY)}
    beta_item = rng.normal(0, 0.3, (len(items), len(CLUSTERS)))
    shares = fpgs[SHARE_COLUMNS].to_numpy(float)
    est_mask = fpgs["new_in_stage"].isna().to_numpy()

    def x_of(it: str) -> np.ndarray:
        b = beta_cat[items.loc[it, "category"]] + beta_item[item_pos[it]]
        return shares @ b

    x_all = {it: x_of(it) for it in items.index}
    x_center = {it: float(x_all[it][est_mask].mean()) for it in items.index}
    fpg_pos = {f: j for j, f in enumerate(fpgs.index)}
    pairs = pairs.copy()
    pairs["true_affinity"] = [
        float(
            np.exp(x_all[r.item_id][fpg_pos[r.fpg_id]] - x_center[r.item_id] + rng.normal(0, 0.35))
            * (0.01 if r.dead else 1.0)
        )
        for r in pairs.itertuples(index=False)
    ]
    start_idx = np.searchsorted(weeks, pairs["start"].to_numpy())
    lengths = T - start_idx
    P = len(pairs)
    pidx = np.repeat(np.arange(P), lengths)
    offsets = np.repeat(np.cumsum(lengths) - lengths, lengths)
    widx = np.arange(lengths.sum()) - offsets + np.repeat(start_idx, lengths)

    it_idx = pairs["item_id"].map(item_pos).to_numpy()[pidx]
    fp_idx = pairs["fpg_id"].map(fpg_pos).to_numpy()[pidx]
    true_s = np.vstack([_seasonal_curve(a, p) for a, p in zip(items["true_amp"], items["peak"], strict=True)])
    bursts = np.ones((len(items), T))
    bmask = rng.random((len(items), T)) < cfg.burst_prob
    bursts[bmask] = rng.uniform(2, 4, int(bmask.sum()))

    hv = hh_versions.sort_values(["fpg_id", "effective_from"])
    h_week = np.zeros((len(fpgs), T))
    for f, grp in hv.groupby("fpg_id"):
        for v in grp.itertuples(index=False):
            h_week[fpg_pos[f], weeks >= v.effective_from] = v.households

    first_offer_at = pairs["first_offer_at"].to_numpy()[pidx]
    week_starts = weeks[widx]
    offered_days = np.full(len(pidx), 7, dtype=np.int64)
    partial = (pairs["fixture_kind"].to_numpy()[pidx] == "partial_week") & (
        week_starts == pairs["start"].to_numpy()[pidx]
    )
    if partial.any():
        offered_days[partial] = 7 - (pd.DatetimeIndex(first_offer_at[partial]) - week_starts[partial]).days.to_numpy()

    base_mu = (
        h_week[fp_idx, widx]
        * items["true_rate"].to_numpy()[it_idx]
        * pairs["true_affinity"].to_numpy()[pidx]
        * true_s[it_idx, woy[widx] - 1]
        * np.exp(items["true_trend"].to_numpy()[it_idx] * years[widx])
        * bursts[it_idx, widx]
        * offered_days
        / 7.0
    )
    gate = items["true_gate"].to_numpy()[it_idx]
    calib_end = to_ts(cfg.stage_windows["validation"][0])
    calib = (week_starts + WEEK) <= calib_end
    alpha = _calibrate_alpha(base_mu[calib], gate[calib], cfg.nb_shape, cfg.target_zero_fraction)
    mu = alpha * base_mu
    active = rng.random(len(mu)) < gate
    lam = rng.gamma(cfg.nb_shape, (mu / gate) / cfg.nb_shape)
    demand = rng.poisson(lam) * active

    kind = pairs["fixture_kind"].to_numpy()[pidx]
    so_p = np.where(kind == "stockout_heavy", 0.4, cfg.stockout_prob)
    stockout = rng.random(len(mu)) < so_p
    available = offered_days.copy()
    available[stockout] = rng.integers(0, np.maximum(offered_days[stockout], 1))
    sold = np.where(stockout, rng.binomial(demand, available / np.maximum(offered_days, 1)), demand).astype(float)
    missing = rng.random(len(mu)) < cfg.missing_prob
    mt = np.where(kind == "missing_targets")[0]
    if len(mt):
        rel = widx[mt] - start_idx[pidx[mt]]
        chosen = mt[np.isin(rel, [4, 9, 15, 22, 30, 31, 38, 45])]
        missing[chosen] = True
    units = np.where(missing, np.nan, sold)
    week_end = week_starts + WEEK
    known = week_end + pd.Timedelta(days=cfg.reporting_delay_days)
    late = rng.random(len(mu)) < cfg.late_report_prob
    known = known + pd.to_timedelta(np.where(late, 14, 0), unit="D")

    rows = pd.DataFrame(
        {
            "item_id": pairs["item_id"].to_numpy()[pidx],
            "fpg_id": pairs["fpg_id"].to_numpy()[pidx],
            "week_start": week_starts,
            "week_end": week_end,
            "units": units,
            "observation_state": np.where(missing, "missing", np.where(stockout, "observed_censored", "observed")),
            "known_at": known,
            "offered_days": offered_days,
            "available_days": available,
            "stockout_state": np.where(stockout, "stockout", "in_stock"),
            "latent_demand": demand.astype(float),
            "latent_mean": mu,
            "pair_kind": pairs["kind"].to_numpy()[pidx],
        }
    )
    expected_zero = _expected_zero(alpha, base_mu[calib], gate[calib], cfg.nb_shape)
    meas = rows.loc[calib & ~missing, "units"]
    info = {
        "alpha": alpha,
        "calibration_period_end": calib_end.date().isoformat(),
        "calibration_rows": int(calib.sum()),
        "expected_zero_fraction_calibration": expected_zero,
        "realized_zero_fraction_calibration": float((meas == 0).mean()),
        "beta_category": {k: v.tolist() for k, v in beta_cat.items()},
        "true_seasonality": {it: true_s[j].tolist() for j, it in enumerate(items.index)},
        "bursts": [
            {"item_id": items.index[i], "week_start": weeks[t].date().isoformat(), "multiplier": bursts[i, t]}
            for i, t in zip(*np.where(bmask), strict=True)
        ],
    }
    return rows, {"info": info, "pairs": pairs}


def build_metadata(cfg: SynthConfig, fmt: str, paths: dict[str, str]) -> Metadata:
    return Metadata(
        dataset=DatasetInfo(
            id=f"retail_synthetic_{cfg.preset}",
            version=f"seed{cfg.seed}-v1",
            description="Synthetic retail cold-pair data generated by xferbench. Demonstrates software behavior only.",
            synthetic=True,
            generator={"preset": cfg.preset, "seed": cfg.seed, "config_hash": hash_obj(cfg.to_dict())},
        ),
        time=TimeSpec(reporting_delay_days=cfg.reporting_delay_days),
        tables={n: TableSource(path=p, format=fmt) for n, p in paths.items()},  # type: ignore[arg-type]
        features=FeatureSpec(demographic_share_columns=list(SHARE_COLUMNS)),
        cohorts=CohortSpec(
            stages={s: StageWindow(origin_start=a, origin_end=b) for s, (a, b) in cfg.stage_windows.items()}
        ),
        rights=Rights(
            data_owner="synthetic (generated by xferbench)",
            permitted_use="education and software validation",
            input_license="CC0-1.0 (generated data)",
        ),
    )


def _frames(
    cfg: SynthConfig, ent: _Entities, pairs: pd.DataFrame, rows: pd.DataFrame, hh_versions: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    obs = rows[list(TABLES["observations"].column_names)].copy()
    offers = rows[
        ["item_id", "fpg_id", "week_start", "week_end", "offered_days", "available_days", "stockout_state", "known_at"]
    ].copy()
    offers["offer_state"] = "offered"
    offers["exposure_fraction"] = offers["offered_days"] / 7.0
    offers = offers[TABLES["offers"].column_names]
    eff = to_ts("2018-01-01")
    items = ent.items.assign(effective_from=eff, known_at=eff)[
        ["item_id", "category", "product_type", "seasonality_class", "effective_from", "known_at"]
    ]
    f = ent.fpgs.set_index("fpg_id")
    loc = hh_versions.copy()
    loc["region"] = loc["fpg_id"].map(f["region"])
    loc["fpg_open_at"] = loc["fpg_id"].map(f["fpg_open_at"])
    for c in SHARE_COLUMNS:
        loc[c] = loc["fpg_id"].map(f[c])
    fx = loc["fpg_id"].map(f["fixture"]).astype(bool)
    loc.loc[fx, SHARE_COLUMNS] = np.nan
    loc.loc[fx, "region"] = None
    loc = loc[["fpg_id", "region", "fpg_open_at", "households", "effective_from", "known_at", *SHARE_COLUMNS]]

    lp = pairs[pairs["kind"] == "launch"]
    launches = pd.DataFrame(
        {
            "launch_id": lp["launch_id"],
            "pair_id": lp["item_id"] + "|" + lp["fpg_id"],
            "item_id": lp["item_id"],
            "fpg_id": lp["fpg_id"],
            "first_offer_at": pd.to_datetime(lp["first_offer_at"]),
            "first_offer_week": lp["start"],
            "fpg_open_at": lp["fpg_id"].map(f["fpg_open_at"]),
            "origin": lp["start"],
            "scenario": lp["scenario"],
            "qualification": np.where(lp["fixture_kind"].isna(), "qualified", "edge_fixture"),
            "launch_type": "natural",
            "cohort_id": np.where(lp["fixture_kind"].isna(), lp["stage"] + "_" + lp["scenario"], "test_edge_fixtures"),
            "fixture_kind": lp["fixture_kind"],
        }
    ).reset_index(drop=True)

    donor_rows = rows[(rows["pair_kind"] == "donor") & rows["units"].notna()].copy()
    donor_rows["hh"] = _households_at(hh_versions, donor_rows)
    donors = (
        donor_rows.groupby(["item_id", "week_start"])
        .agg(
            week_end=("week_end", "first"),
            units=("units", "sum"),
            household_coverage=("hh", "sum"),
            known_at=("known_at", "max"),
        )
        .reset_index()
    )
    donors["donor_scope_id"] = "established_footprint_v1"
    donors["source_version"] = "synthetic_national_v1"
    donors = donors[TABLES["donors"].column_names]
    return {
        "observations": obs,
        "offers": offers,
        "items": items,
        "locations": loc,
        "launches": launches,
        "donors": donors,
    }


def _households_at(hh_versions: pd.DataFrame, rows: pd.DataFrame) -> np.ndarray:
    out = np.full(len(rows), np.nan)
    for f, grp in hh_versions.sort_values("effective_from").groupby("fpg_id"):
        m = (rows["fpg_id"] == f).to_numpy()
        if not m.any():
            continue
        ws = rows.loc[m, "week_start"].to_numpy()
        vals = np.full(m.sum(), np.nan)
        for v in grp.itertuples(index=False):
            vals[ws >= np.datetime64(v.effective_from)] = v.households
        out[m] = vals
    return out


def _ridge(X: np.ndarray, y: np.ndarray, lam: float = 1.0) -> np.ndarray:
    return np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ y)


def _origin_features(
    cfg: SynthConfig, frames: dict[str, pd.DataFrame], metadata: Metadata, rng: np.random.Generator
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Company-style features computed ONLY from origin-scoped observed data (no hidden truth)."""
    ds = Dataset(metadata=metadata, base_dir=Path("."), tables=frames)
    la = frames["launches"]
    stage_of = {}
    for s in STAGES:
        lo, hi = (to_ts(x) for x in cfg.stage_windows[s])
        for lid, o in zip(la["launch_id"], la["origin"], strict=True):
            if lo <= o <= hi:
                stage_of[lid] = s
    la = la.assign(stage=la["launch_id"].map(stage_of))
    feats: list[dict] = []
    covs: list[pd.DataFrame] = []
    sigma = cfg.propensity_noise_sigma
    items_cat = frames["items"].set_index("item_id")["category"]
    for s in STAGES:
        sl = la[la["stage"] == s]
        ex = Exclusions(
            pairs=frozenset(zip(sl["item_id"], sl["fpg_id"], strict=True)),
            fpgs=frozenset(sl.loc[sl["scenario"] == "PAIR0-N", "fpg_id"]),
        )
        builder = ContextBuilder(ds, ex)
        for origin, grp in sl.groupby("origin"):
            ctx = builder.at(origin)
            known_at = origin - pd.Timedelta(days=7)
            nat = national_rates(ctx)
            pr = pair_rates(ctx)
            pr = pr[pr["consistent"]].copy()
            loc = ctx.locations.set_index("fpg_id")
            pr["x"] = list(loc.reindex(pr["fpg_id"])[SHARE_COLUMNS].to_numpy(float))
            pr["category"] = pr["item_id"].map(items_cat)
            pr["r_nat"] = pr["item_id"].map({i: (r.rate or np.nan) for i, r in nat.items()})
            gammas: dict[str, np.ndarray] = {}
            for c, cg in pr.dropna(subset=["r_nat"]).groupby("category"):
                X = np.vstack(cg["x"].to_numpy())
                eps = 0.5 / (cg["households"] * cg["n_obs"])
                y = np.log((cg["rate"] + eps) / cg["r_nat"]).to_numpy()
                gammas[str(c)] = _ridge(X, y)
            obs13 = ctx.observations[ctx.observations["week_start"] > ctx.latest_usable_week - 13 * WEEK]
            nat13 = obs13.groupby("item_id")["units"].sum()
            nat13 = nat13.reindex(ctx.items["item_id"]).fillna(0.0)
            ranks = nat13.rank(ascending=False, method="min")
            for it in ctx.items["item_id"]:
                base = {
                    "scope": "item",
                    "item_id": it,
                    "fpg_id": None,
                    "scope_id": None,
                    "origin": origin,
                    "known_at": known_at,
                    "source_version": FEATURE_VERSION,
                }
                feats.append({**base, "feature_name": "item_prelaunch_rank", "value": float(ranks[it]), "unit": "rank"})
                feats.append(
                    {**base, "feature_name": "national_units_13w", "value": float(nat13[it]), "unit": "item_units"}
                )
                g = gammas.get(str(items_cat.get(it)))
                if g is not None:
                    aff = np.exp(g - g.mean())
                    for cl, v in zip(CLUSTERS, aff, strict=True):
                        feats.append(
                            {**base, "feature_name": f"item_affinity_{cl}", "value": float(v), "unit": "ratio"}
                        )
            for r in grp.itertuples(index=False):
                nr = nat.get(r.item_id)
                g = gammas.get(str(items_cat.get(r.item_id)))
                tx = loc.loc[r.fpg_id, SHARE_COLUMNS].to_numpy(float) if r.fpg_id in loc.index else None
                donors = pr[pr["item_id"] == r.item_id]
                if (
                    r.fixture_kind != "missing_propensity"
                    and nr is not None
                    and nr.rate
                    and g is not None
                    and tx is not None
                    and not np.isnan(tx).any()
                    and len(donors)
                ):
                    w = (donors["households"] * donors["n_obs"]).to_numpy()
                    norm = float(np.sum(w * np.exp(np.vstack(donors["x"].to_numpy()) @ g)) / w.sum())
                    ratio = float(np.exp(tx @ g)) / norm
                    p = nr.rate * ratio * float(np.exp(rng.normal(0, sigma) - sigma**2 / 2))
                    feats.append(
                        {
                            "feature_name": "propensity_rate",
                            "scope": "pair",
                            "item_id": r.item_id,
                            "fpg_id": r.fpg_id,
                            "scope_id": None,
                            "origin": origin,
                            "value": p,
                            "unit": "units_per_household_per_week",
                            "known_at": known_at,
                            "source_version": FEATURE_VERSION,
                        }
                    )
                fw = [origin + WEEK * h for h in range(metadata.time.horizon_weeks)]
                exposure = np.ones(len(fw))
                if r.fixture_kind == "partial_week":
                    exposure[0] = 1 - (r.first_offer_at - origin).days / 7
                covs.append(
                    pd.DataFrame(
                        {
                            "feature_name": "planned_exposure_fraction",
                            "item_id": r.item_id,
                            "fpg_id": r.fpg_id,
                            "scope_id": None,
                            "origin": origin,
                            "forecast_week": fw,
                            "value": exposure,
                            "availability_class": "planned",
                            "known_at": known_at,
                            "source_version": "synthetic_offer_plan_v1",
                        }
                    )
                )
    of = pd.DataFrame(feats)[TABLES["origin_features"].column_names]
    of = of.drop_duplicates(subset=list(TABLES["origin_features"].key), keep="first").reset_index(drop=True)
    fc = pd.concat(covs, ignore_index=True)[TABLES["future_covariates"].column_names]
    return of, fc


def _write_table(df: pd.DataFrame, name: str, path: Path, fmt: str) -> None:
    spec = TABLES[name]
    extra = {c: pa.float64() for c in df.columns if c not in spec.column_names}
    frame = df.copy()
    for c in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[c]):
            frame[c] = frame[c].dt.date.where(frame[c].notna(), None)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "parquet":
        table = pa.Table.from_pandas(frame, schema=spec.arrow_schema(extra), preserve_index=False)
        tmp = path.with_suffix(".parquet.tmp")
        pq.write_table(table, tmp)
        tmp.replace(path)
    else:
        atomic_write_csv(path, df)


def generate(cfg: SynthConfig, out: Path, formats: tuple[str, ...] = ("parquet",)) -> dict:
    """Generate a dataset under ``out``; returns a summary dict."""
    from xferbench.contracts.tables import field_dictionary_markdown
    from xferbench.domains.retail.plugin import retail_data_profile
    from xferbench.domains.retail.splits import build_retail_splits
    from xferbench.synth.story import data_story

    rng = np.random.default_rng(cfg.seed)
    ent = _entities(cfg, rng)
    pairs = _pairs(cfg, ent, rng)
    hh = _household_versions(ent.fpgs, rng)
    rows, sim = _simulate(cfg, ent, pairs, hh, rng)
    frames = _frames(cfg, ent, sim["pairs"], rows, hh)
    rel = {n: f"data/{n}.parquet" for n in TABLES}
    md_mem = build_metadata(cfg, "parquet", rel)
    feat_rng = np.random.default_rng(cfg.seed + 1)
    frames["origin_features"], frames["future_covariates"] = _origin_features(cfg, frames, md_mem, feat_rng)

    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for fmt in formats:
        paths = {n: f"data/{n}.{fmt}" for n in frames}
        for n, df in frames.items():
            _write_table(df, n, out / paths[n], fmt)
        md = build_metadata(cfg, fmt, paths)
        name = "metadata.json" if fmt == formats[0] else f"metadata.{fmt}.json"
        loaded = load_dataset(md, out, verify_hash=False)
        md.dataset.expected_hash = loaded.content_hash
        hashes[fmt] = loaded.content_hash
        write_json(out / name, md.model_dump(mode="json", exclude_none=False))
        written[fmt] = out / name

    truth = out / TRUTH_DIR
    truth.mkdir(exist_ok=True)
    atomic_write_text(
        truth / "README.txt",
        "Hidden synthetic truth for diagnostics only. Never map these files in "
        "metadata; benchmark adapters must not read them.\n",
    )
    rows[["item_id", "fpg_id", "week_start", "latent_demand", "latent_mean"]].to_parquet(
        truth / "latent_demand.parquet", index=False
    )
    sim["pairs"][["item_id", "fpg_id", "kind", "launch_id", "dead", "true_affinity"]].to_parquet(
        truth / "pairs.parquet", index=False
    )
    ent.items[["item_id", "category", "true_rate", "true_gate", "true_trend", "true_amp", "peak"]].to_parquet(
        truth / "items.parquet", index=False
    )
    write_json(truth / "process.json", sim["info"] | {"config": cfg.to_dict()})

    primary = load_dataset(build_metadata(cfg, formats[0], {n: f"data/{n}.{formats[0]}" for n in frames}), out)
    split = build_retail_splits(primary)
    profile = retail_data_profile(primary, split)
    report = {
        "generator": "xferbench.synth",
        "config": cfg.to_dict(),
        "config_hash": hash_obj(cfg.to_dict()),
        "dataset_hash": hashes,
        "csv_parquet_equivalent": len(set(hashes.values())) == 1,
        "calibration": {
            k: sim["info"][k]
            for k in (
                "alpha",
                "calibration_period_end",
                "calibration_rows",
                "expected_zero_fraction_calibration",
                "realized_zero_fraction_calibration",
            )
        },
        "calibration_note": "alpha is chosen so the EXPECTED zero fraction of training-period offered weeks is near "
        "the target; outcomes are never rewritten and validation/test outcomes are not used.",
        "table_hashes": {n: hash_frame(df, TABLES[n].key) for n, df in frames.items()},
        "profile": profile,
        "split_counts": {s: st.counts for s, st in split.stages.items()},
    }
    write_json(out / "generation_report.json", report)
    atomic_write_text(out / "FIELD_DICTIONARY.md", field_dictionary_markdown())
    atomic_write_text(out / "DATA_STORY.md", data_story(cfg, primary, split, sim["info"], report))
    return {"out": out, "metadata": written, "report": report}
