"""Transparent cold-pair baselines and business rules: B0, B1, B2, B2.raw_units, M1, M2.

All produce season-neutral rates per household (or per FPG for the raw ablation) from origin-scoped
donor data and multiply by a mean-one seasonal profile at most once.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from xferbench.contracts.methods import CapabilitySpec, ModelArtifact, Rights
from xferbench.features.aggregates import national_rates, pair_rates, profile_for_item
from xferbench.features.context import OriginContext
from xferbench.methods.base import RowResult, TrainingContext, expand, join_reasons, stateless_artifact

VERSION = "1.0.0"
OWN_CODE = Rights(
    code_license="Apache-2.0",
    code_source="xferbench (this package)",
    notes="Newly authored recipe; no third-party code or weights.",
)
STATELESS_NOTE = (
    "No parameters are learned from training labels; rates and seasonal profiles are estimated "
    "from origin-scoped donor history at prediction time."
)


def _spec(
    method_id: str,
    name: str,
    description: str,
    *,
    features: list[str],
    required: list[str] | None = None,
    family: str = "baseline",
) -> CapabilitySpec:
    return CapabilitySpec(
        method_id=method_id,
        version=VERSION,
        family=family,
        display_name=name,
        task_profiles=["retail_pair_zero_v1"],
        board="cold_c0",
        identity="native",
        min_own_pair_history_weeks=0,
        min_donor_history_weeks=1,
        required_features=required or [],
        supports_new_location=True,
        point_statistic="mean",
        rights=OWN_CODE,
        used_features=features,
        description=description,
        history_rules="Zero own-pair history; same-item donor history at other FPGs only as available at origin; "
        "held-out pairs and the stage's new FPGs are excluded from every aggregate.",
    )


def _target_households(ctx: OriginContext, fpg_id: str) -> float | None:
    h = ctx.locations.set_index("fpg_id")["households"].get(fpg_id)
    return None if h is None or pd.isna(h) or h <= 0 else float(h)


def _forecast_weeks(origin: pd.Timestamp, horizon: int) -> list[pd.Timestamp]:
    return [origin + pd.Timedelta(days=7 * h) for h in range(horizon)]


class _Base:
    spec: CapabilitySpec

    def capabilities(self) -> CapabilitySpec:
        return self.spec

    def variants(self) -> list[dict[str, Any]]:
        return [{}]

    def fit(
        self, training: TrainingContext, inner_validation: TrainingContext | None, config: dict[str, Any]
    ) -> ModelArtifact:
        return stateless_artifact(self.spec, training, config, STATELESS_NOTE, self.variants())

    def predict_batch(self, requests: pd.DataFrame, ctx: OriginContext, artifact: ModelArtifact) -> pd.DataFrame:
        h = ctx.metadata.time.horizon_weeks
        results = [self._one(r, ctx, artifact.config, h) for r in requests.itertuples(index=False)]
        return expand(requests, results, h)

    def _one(self, req: Any, ctx: OriginContext, cfg: dict[str, Any], h: int) -> RowResult:
        raise NotImplementedError


def national_level(ctx: OriginContext, req: Any) -> tuple[float | None, str, str]:
    """H_target * r_item (B0). Returns (level, status, reason)."""
    hh = _target_households(ctx, req.fpg_id)
    if hh is None:
        return None, "failed", "target households unknown at origin"
    nr = national_rates(ctx).get(req.item_id)
    if nr is None or nr.rate is None:
        return None, "failed", "no origin-valid national history for item"
    if nr.footprint != "consistent":
        return hh * nr.rate, "fallback", "no consistently exposed donor footprint; used all measured donor weeks"
    return hh * nr.rate, "success", ""


def _seasonal(ctx: OriginContext, req: Any, h: int) -> tuple[np.ndarray, str]:
    prof = profile_for_item(ctx, req.item_id)
    reason = "" if prof.status == "estimated" else f"flat seasonal profile ({prof.reason})"
    return prof.at(_forecast_weeks(req.origin, h)), reason


class B0NationalRate(_Base):
    spec = _spec(
        "B0",
        "National flat rate x households",
        "H_target x r_item, r_item = national season-neutral weekly units per consistently exposed household.",
        features=["households", "donor observations"],
    )

    def _one(self, req: Any, ctx: OriginContext, cfg: dict[str, Any], h: int) -> RowResult:
        level, status, reason = national_level(ctx, req)
        if level is None:
            return RowResult(req.request_id, None, status, reason)
        return RowResult(req.request_id, np.full(h, level), status, reason)


class B1NationalSeasonal(_Base):
    spec = _spec(
        "B1",
        "National rate x households x seasonal profile",
        "B0 x S_category(week), S donor-estimated, calendar-aligned, mean one.",
        features=["households", "donor observations", "item category"],
    )

    def _one(self, req: Any, ctx: OriginContext, cfg: dict[str, Any], h: int) -> RowResult:
        level, status, reason = national_level(ctx, req)
        if level is None:
            return RowResult(req.request_id, None, status, reason)
        s, s_reason = _seasonal(ctx, req, h)
        if s_reason:
            status = "fallback"
        return RowResult(req.request_id, level * s, status, join_reasons(reason, s_reason))


def _similarity(ctx: OriginContext, target: str, donors: pd.Series, cfg: dict[str, Any]) -> pd.Series | None:
    loc = ctx.locations.set_index("fpg_id")
    shares = list(ctx.share_columns)
    if target not in loc.index:
        return None
    t = loc.loc[target]
    if shares and t[shares].isna().any():
        return None
    d_loc = loc.reindex(donors.to_numpy())
    dist = pd.Series(0.0, index=d_loc.index)
    if shares:
        diff = d_loc[shares].to_numpy(dtype=float) - t[shares].to_numpy(dtype=float)
        dist += np.sqrt(np.nansum(diff**2, axis=1)) / np.sqrt(2.0)
        dist[d_loc[shares].isna().any(axis=1).to_numpy()] = np.inf
    dist += cfg["w_households"] * np.abs(np.log(d_loc["households"].astype(float)) - np.log(float(t["households"])))
    region_diff = (d_loc["region"].astype(object) != t["region"]) | d_loc["region"].isna() | pd.isna(t["region"])
    dist += cfg["w_region"] * region_diff.astype(float).to_numpy()
    return dist


def analog_donors(ctx: OriginContext, req: Any, cfg: dict[str, Any]) -> tuple[pd.DataFrame | None, str]:
    pr = pair_rates(ctx)
    cand = pr[(pr["item_id"] == req.item_id) & pr["consistent"] & (pr["fpg_id"] != req.fpg_id)]
    if cand.empty:
        return None, "no consistently exposed same-item donor FPG"
    dist = _similarity(ctx, req.fpg_id, cand["fpg_id"], cfg)
    if dist is None:
        return None, "target FPG attributes unknown; similarity undefined"
    cand = cand.assign(distance=dist.to_numpy())
    cand = cand[np.isfinite(cand["distance"])].sort_values(["distance", "fpg_id"]).head(int(cfg["k"]))
    if len(cand) < int(cfg.get("min_donors", 1)):
        return None, "too few comparable donor FPGs"
    cand = cand.assign(weight=1.0 / (cand["distance"] + cfg["distance_offset"]))
    return cand, ""


B2_GRID = [
    {"k": k, "kappa": kappa, "w_households": 0.25, "w_region": 0.25, "distance_offset": 0.05, "min_donors": 1}
    for k in (3, 8)
    for kappa in (1.0, 4.0)
]


class B2AnalogRate(_Base):
    spec = _spec(
        "B2",
        "Same-item analog FPG rate (household-adjusted, shrunk)",
        "H_target x r_B2 x S, r_B2 = (n*weighted donor rate + kappa*r_national)/(n+kappa) over the k most "
        "similar same-item donor FPGs (inverse-distance weights on demographic shares, log households, "
        "region). Falls back to B1 when no comparable donors exist.",
        features=["households", "demographic shares", "region", "donor observations", "item category"],
    )

    def variants(self) -> list[dict[str, Any]]:
        return [dict(c) for c in B2_GRID]

    def _one(self, req: Any, ctx: OriginContext, cfg: dict[str, Any], h: int) -> RowResult:
        level, status, reason = national_level(ctx, req)
        if level is None:
            return RowResult(req.request_id, None, status, reason)
        hh = _target_households(ctx, req.fpg_id)
        assert hh is not None
        r_nat = level / hh
        s, s_reason = _seasonal(ctx, req, h)
        donors, d_reason = analog_donors(ctx, req, cfg)
        if donors is None:
            return RowResult(
                req.request_id, level * s, "fallback", join_reasons(f"B1 fallback: {d_reason}", reason, s_reason)
            )
        n = len(donors)
        r_analog = float((donors["weight"] * donors["rate"]).sum() / donors["weight"].sum())
        r = (n * r_analog + cfg["kappa"] * r_nat) / (n + cfg["kappa"])
        st = "fallback" if (s_reason or status == "fallback") else "success"
        return RowResult(req.request_id, hh * r * s, st, join_reasons(reason, s_reason))


B2_RAW_GRID = [
    {"k": k, "w_households": 0.25, "w_region": 0.25, "distance_offset": 0.05, "min_donors": 1} for k in (3, 8)
]


class B2RawUnits(_Base):
    spec = _spec(
        "B2.raw_units",
        "Ablation: raw k-FPG unit mean (no household adjustment)",
        "Weighted mean weekly units of the k most similar same-item donor FPGs x S. Exposure-unadjusted "
        "ablation of B2; not a recommended recipe.",
        features=["demographic shares", "region", "households (similarity only)", "donor observations"],
        family="ablation",
    )

    def variants(self) -> list[dict[str, Any]]:
        return [dict(c) for c in B2_RAW_GRID]

    def _one(self, req: Any, ctx: OriginContext, cfg: dict[str, Any], h: int) -> RowResult:
        s, s_reason = _seasonal(ctx, req, h)
        donors, d_reason = analog_donors(ctx, req, cfg)
        if donors is None:
            return RowResult(req.request_id, None, "failed", f"no raw-unit analog: {d_reason}")
        units = float((donors["weight"] * donors["avg_units"]).sum() / donors["weight"].sum())
        return RowResult(req.request_id, units * s, "fallback" if s_reason else "success", s_reason)


def propensity(ctx: OriginContext, req: Any) -> tuple[float | None, str]:
    spec = ctx.metadata.features.propensity
    if spec is None:
        return None, "metadata declares no propensity feature"
    f = ctx.feature(spec.feature_name)
    row = f[(f["scope"] == "pair") & (f["item_id"] == req.item_id) & (f["fpg_id"] == req.fpg_id)]
    if row.empty or row["value"].isna().all():
        return None, f"missing feature '{spec.feature_name}' for pair at origin"
    if (row["unit"] != spec.unit).any():
        return None, f"propensity unit is not {spec.unit}"
    return float(row.sort_values("known_at")["value"].iloc[-1]), ""


def _m_spec(method_id: str, name: str, desc: str, seasonal: bool) -> CapabilitySpec:
    feats = ["households", "propensity_rate P (origin snapshot)"] + (
        ["item category", "donor observations"] if seasonal else []
    )
    return _spec(method_id, name, desc, features=feats, required=["propensity_rate"], family="business_rule")


class M1FlatRule(_Base):
    spec = _m_spec(
        "M1",
        "Business rule H x P",
        "H x P with P = season-neutral expected weekly units per household (not a probability).",
        False,
    )

    def _one(self, req: Any, ctx: OriginContext, cfg: dict[str, Any], h: int) -> RowResult:
        hh = _target_households(ctx, req.fpg_id)
        if hh is None:
            return RowResult(req.request_id, None, "failed", "target households unknown at origin")
        p, reason = propensity(ctx, req)
        if p is None:
            return RowResult(req.request_id, None, "failed", reason)
        return RowResult(req.request_id, np.full(h, hh * p), "success")


class M2SeasonalRule(_Base):
    spec = _m_spec(
        "M2",
        "Business rule H x P x S",
        "H x P x S with mean-one donor-estimated S; no anchor-week division; affinity not re-applied.",
        True,
    )

    def _one(self, req: Any, ctx: OriginContext, cfg: dict[str, Any], h: int) -> RowResult:
        hh = _target_households(ctx, req.fpg_id)
        if hh is None:
            return RowResult(req.request_id, None, "failed", "target households unknown at origin")
        p, reason = propensity(ctx, req)
        if p is None:
            return RowResult(req.request_id, None, "failed", reason)
        s, s_reason = _seasonal(ctx, req, h)
        return RowResult(req.request_id, hh * p * s, "fallback" if s_reason else "success", s_reason)
