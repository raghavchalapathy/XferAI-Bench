"""Retail cold-pair domain plugin (profile ``retail_pair_zero_v1``)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from xferbench.calendar import to_ts
from xferbench.contracts.splits import SplitManifest
from xferbench.data.io import Dataset
from xferbench.data.issues import Issue
from xferbench.domains.retail.splits import build_retail_splits, target_rows
from xferbench.domains.retail.validation import validate_retail
from xferbench.features.context import ContextBuilder, Exclusions

MEASURED_STATES = ("observed", "observed_censored")


class RetailDomain:
    id: str = "retail"
    version: str = "1.0"
    task_profiles: tuple[str, ...] = ("retail_pair_zero_v1",)
    entity_columns: tuple[str, ...] = ("item_id", "fpg_id")
    scenarios: tuple[str, ...] = ("PAIR0-E", "PAIR0-N")
    slice_columns: tuple[str, ...] = ("category", "region")
    slice_week_columns: tuple[str, ...] = ("availability",)
    # Methods in order, each adding one idea (optional plugin attribute, read by reports/progression.py).
    method_order: tuple[tuple[str, str], ...] = (
        ("B0", "H x r, flat: households x national season-neutral item rate"),
        ("B1", "B0 x S(national product type, week): adds mean-one seasonality"),
        ("B2.raw_units", "item's mean weekly sales in the k FPGs with the most similar customer mix"),
        ("M1", "H x P, flat: uses the location propensity P instead of the national rate"),
        ("M2", "H x P x S(i,f,w), mean-one S, no anchor-week division: adds seasonality to M1"),
        ("M3", "user ramp/blend/calibration rule (recipe required)"),
        ("M4.lightgbm", "gradient-boosted trees on origin-built features (optional extra)"),
    )
    # (candidate, reference, note): delta = candidate - reference
    method_comparisons: tuple[tuple[str, str, str], ...] = (
        ("M1", "B0", "P vs national rate (both flat)"),
        ("B1", "B0", "adds seasonality to the national rate"),
        ("M2", "M1", "adds seasonality to H x P"),
        ("M3", "M2", "adds the user rule"),
        ("M4.lightgbm", "M2", "M3 pending recipe: compared with M2 instead"),
    )

    def validate(self, dataset: Dataset) -> list[Issue]:
        return validate_retail(dataset)

    def build_splits(self, dataset: Dataset) -> SplitManifest:
        return build_retail_splits(dataset)

    def _launch_frame(self, dataset: Dataset, split: SplitManifest, stage: str, ids: list[str] | None) -> pd.DataFrame:
        recs = (
            split.stages[stage].launches
            if ids is None
            else [r for s in split.stages.values() for r in s.launches if r.launch_id in set(ids)]
        )
        stage_of = {r.launch_id: s for s, st in split.stages.items() for r in st.launches}
        rows = [
            {
                "request_id": r.launch_id,
                "launch_id": r.launch_id,
                "item_id": r.item_id,
                "fpg_id": r.fpg_id,
                "origin": to_ts(r.origin),
                "scenario": r.scenario,
                "board": r.board,
                "ranked": r.ranked,
                "fixture_kind": r.fixture_kind,
                "source_stage": stage_of[r.launch_id],
            }
            for r in recs
        ]
        df = pd.DataFrame(
            rows,
            columns=[
                "request_id",
                "launch_id",
                "item_id",
                "fpg_id",
                "origin",
                "scenario",
                "board",
                "ranked",
                "fixture_kind",
                "source_stage",
            ],
        )
        return self._attach_slices(dataset, df)

    def _attach_slices(self, dataset: Dataset, req: pd.DataFrame) -> pd.DataFrame:
        if req.empty:
            return req.assign(category=pd.Series(dtype=object), region=pd.Series(dtype=object))
        cats, regs = [], []
        items, locs = dataset["items"], dataset["locations"]
        for r in req.itertuples(index=False):
            it = items[
                (items["item_id"] == r.item_id)
                & (items["known_at"] <= r.origin)
                & (items["effective_from"] <= r.origin)
            ].sort_values("effective_from")
            lc = locs[
                (locs["fpg_id"] == r.fpg_id) & (locs["known_at"] <= r.origin) & (locs["effective_from"] <= r.origin)
            ].sort_values("effective_from")
            cats.append(it["category"].iloc[-1] if len(it) and pd.notna(it["category"].iloc[-1]) else "unknown")
            regs.append(lc["region"].iloc[-1] if len(lc) and pd.notna(lc["region"].iloc[-1]) else "unknown")
        return req.assign(category=cats, region=regs)

    def requests(self, dataset: Dataset, split: SplitManifest, stage: str) -> pd.DataFrame:
        return self._launch_frame(dataset, split, stage, None)

    def training_requests(self, dataset: Dataset, split: SplitManifest, stage: str) -> pd.DataFrame:
        return self._launch_frame(dataset, split, stage, split.stages[stage].fit_launch_ids)

    def targets(self, dataset: Dataset, requests: pd.DataFrame) -> pd.DataFrame:
        la = requests[["launch_id", "item_id", "fpg_id", "origin"]].reset_index(drop=True)
        tr = target_rows(dataset, la)
        off = dataset["offers"][["item_id", "fpg_id", "week_start", "stockout_state"]]
        tr = tr.merge(
            off,
            left_on=["item_id", "fpg_id", "forecast_week"],
            right_on=["item_id", "fpg_id", "week_start"],
            how="left",
        ).drop(columns=["week_start"])
        tr["measured"] = tr["observation_state"].isin(MEASURED_STATES) & tr["units"].notna()
        tr["availability"] = np.where(tr["stockout_state"] == "stockout", "stockout", "in_stock")
        tr = tr.rename(columns={"units": "actual", "launch_id": "request_id"})
        return tr[
            ["request_id", "horizon_week", "forecast_week", "actual", "observation_state", "measured", "availability"]
        ]

    def context_builder(self, dataset: Dataset, split: SplitManifest, stage: str) -> ContextBuilder:
        st = split.stages[stage]
        pairs = frozenset(tuple(p.split("|", 1)) for p in st.excluded_pairs)
        return ContextBuilder(dataset, Exclusions(pairs=pairs, fpgs=frozenset(st.excluded_fpgs)))  # type: ignore[arg-type]

    def data_profile(self, dataset: Dataset, split: SplitManifest | None) -> dict:
        return retail_data_profile(dataset, split)


def _zero_stats(units: pd.Series) -> dict:
    n = int(units.notna().sum())
    z = int((units == 0).sum())
    return {"measured_weeks": n, "zero_weeks": z, "zero_fraction": (z / n) if n else None}


def retail_data_profile(dataset: Dataset, split: SplitManifest | None) -> dict:
    obs = dataset["observations"]
    off = dataset["offers"]
    prof: dict = {
        "rows": {n: len(df) for n, df in dataset.tables.items()},
        "items": int(dataset["items"]["item_id"].nunique()),
        "locations": int(dataset["locations"]["fpg_id"].nunique()),
        "observation_states": obs["observation_state"].value_counts().to_dict(),
        "stockout_states": off["stockout_state"].value_counts().to_dict(),
        "history_start": obs["week_start"].min(),
        "history_end": obs["week_start"].max(),
        "all_measured_weeks": _zero_stats(obs["units"]),
    }
    if split is None:
        return prof
    first_val = to_ts(split.stages["validation"].origin_start)
    prof["training_period_measured_weeks"] = {
        "definition": f"all measured offered weeks ending before the first validation origin {first_val.date()}",
        **_zero_stats(obs.loc[obs["week_end"] <= first_val, "units"]),
    }
    plugin = RetailDomain()
    per: list[dict] = []
    for s in split.stages:
        req = plugin.requests(dataset, split, s)
        if req.empty:
            continue
        tg = plugin.targets(dataset, req).merge(req[["request_id", "scenario", "category", "board"]], on="request_id")
        tg = tg[tg["measured"]]
        for keys, grp in tg.groupby(["board", "scenario", "category"]):
            per.append(
                {"stage": s, "board": keys[0], "scenario": keys[1], "category": keys[2], **_zero_stats(grp["actual"])}
            )
        for keys, grp in tg.groupby(["board", "availability"]):
            per.append(
                {
                    "stage": s,
                    "board": keys[0],
                    "scenario": "all",
                    "category": f"availability={keys[1]}",
                    **_zero_stats(grp["actual"]),
                }
            )
        lt = tg.groupby("request_id")["actual"].sum()
        per.append(
            {
                "stage": s,
                "board": "all",
                "scenario": "all",
                "category": "all_zero_launches",
                "measured_weeks": len(lt),
                "zero_weeks": int((lt == 0).sum()),
                "zero_fraction": float((lt == 0).mean()) if len(lt) else None,
            }
        )
    prof["target_zero_fractions"] = per
    return prof
