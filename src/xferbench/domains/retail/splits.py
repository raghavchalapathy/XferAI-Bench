"""Chronological natural-launch cohorts with computed label availability and leakage checks."""

from __future__ import annotations

import itertools

import pandas as pd

from xferbench.calendar import WEEK, declared_label_available_at, target_end, to_ts
from xferbench.contracts.splits import LaunchRecord, SplitCheck, SplitManifest, StageSplit
from xferbench.data.io import Dataset
from xferbench.util import hash_obj

STAGE_ORDER = ("train", "validation", "test")


def _d(ts: pd.Timestamp | None) -> str | None:
    return None if ts is None or pd.isna(ts) else ts.date().isoformat()


def target_rows(dataset: Dataset, launches: pd.DataFrame) -> pd.DataFrame:
    """All horizon weeks for each launch joined to its (possibly absent) observation rows."""
    h = dataset.metadata.time.horizon_weeks
    if launches.empty:
        return pd.DataFrame(
            columns=[
                "launch_id",
                "horizon_week",
                "forecast_week",
                "units",
                "observation_state",
                "known_at",
                "item_id",
                "fpg_id",
            ]
        )
    rep = launches.loc[launches.index.repeat(h), ["launch_id", "item_id", "fpg_id", "origin"]].reset_index(drop=True)
    rep["horizon_week"] = list(range(1, h + 1)) * len(launches)
    rep["forecast_week"] = rep["origin"] + WEEK * (rep["horizon_week"] - 1)
    obs = dataset["observations"][["item_id", "fpg_id", "week_start", "units", "observation_state", "known_at"]]
    out = rep.merge(
        obs, left_on=["item_id", "fpg_id", "forecast_week"], right_on=["item_id", "fpg_id", "week_start"], how="left"
    ).drop(columns=["week_start"])
    return out


def build_retail_splits(dataset: Dataset) -> SplitManifest:
    md = dataset.metadata
    h, delay = md.time.horizon_weeks, md.time.reporting_delay_days
    cohorts = md.cohorts
    la = dataset["launches"].copy()
    obs = dataset["observations"]
    checks: list[SplitCheck] = []

    windows = {s: (to_ts(w.origin_start), to_ts(w.origin_end)) for s, w in cohorts.stages.items()}
    for a, b in itertools.pairwise(STAGE_ORDER):
        ok = windows[a][1] < windows[b][0]
        checks.append(
            SplitCheck(
                check="chronological_stage_windows",
                passed=ok,
                stage=b,
                detail=f"{a} ends {_d(windows[a][1])} before {b} starts {_d(windows[b][0])}",
            )
        )

    tr = target_rows(dataset, la)
    agg = tr.groupby("launch_id").agg(
        rows=("observation_state", "size"),
        present=("observation_state", lambda s: int(s.notna().sum())),
        measured=("units", lambda s: int(s.notna().sum())),
        missing=("observation_state", lambda s: int((s == "missing").sum())),
        label_known=("known_at", "max"),
    )
    la = la.join(agg, on="launch_id")
    la["stage"] = None
    for s in STAGE_ORDER:
        lo, hi = windows[s]
        la.loc[(la["origin"] >= lo) & (la["origin"] <= hi), "stage"] = s
    unassigned = la[la["stage"].isna()]
    if len(unassigned):
        checks.append(
            SplitCheck(
                check="launch_outside_stage_windows",
                passed=True,
                detail=f"{len(unassigned)} launches outside all stage windows are not used",
            )
        )

    first_obs_pair = obs.groupby(["item_id", "fpg_id"])["week_start"].min()
    first_obs_fpg = obs.groupby("fpg_id")["week_start"].min()

    stages: dict[str, StageSplit] = {}
    new_fpgs_by_stage: dict[str, set[str]] = {}
    for s in STAGE_ORDER:
        lo, hi = windows[s]
        sl = la[la["stage"] == s].sort_values(["origin", "launch_id"])
        records: list[LaunchRecord] = []
        for r in sl.itertuples(index=False):
            ranked = r.qualification in cohorts.ranked_qualifications and r.launch_type in cohorts.ranked_launch_types
            complete = int(r.present) == h and pd.notna(r.label_known)
            records.append(
                LaunchRecord(
                    launch_id=r.launch_id,
                    item_id=r.item_id,
                    fpg_id=r.fpg_id,
                    scenario=r.scenario,
                    origin=_d(r.origin),
                    board="cold_c0" if ranked else "edge_fixtures",
                    ranked=ranked,
                    qualification=r.qualification,
                    launch_type=r.launch_type,
                    cohort_id=r.cohort_id,
                    fixture_kind=getattr(r, "fixture_kind", None)
                    if pd.notna(getattr(r, "fixture_kind", None))
                    else None,
                    target_end=_d(target_end(r.origin, h)),
                    declared_label_available_at=_d(declared_label_available_at(r.origin, h, delay)),
                    label_available_at=_d(r.label_known) if complete else None,
                    label_status="complete" if complete else "incomplete",
                    measured_target_weeks=int(r.measured),
                    missing_target_weeks=int(r.missing),
                )
            )
            pre_pair = first_obs_pair.get((r.item_id, r.fpg_id))
            c0 = pre_pair is None or pre_pair >= r.origin
            checks.append(
                SplitCheck(
                    check="c0_zero_own_pair_history",
                    passed=bool(c0),
                    stage=s,
                    launch_id=r.launch_id,
                    detail="no own-pair observation before origin"
                    if c0
                    else f"own-pair observation at {_d(pre_pair)} before origin",
                )
            )
            if r.scenario == "PAIR0-N":
                f0 = first_obs_fpg.get(r.fpg_id)
                ok = f0 is None or f0 >= r.origin
                checks.append(
                    SplitCheck(
                        check="new_fpg_zero_transactions",
                        passed=bool(ok),
                        stage=s,
                        launch_id=r.launch_id,
                        detail="no target-FPG transactions before origin"
                        if ok
                        else f"FPG {r.fpg_id} has transactions from {_d(f0)}",
                    )
                )
        excluded_pairs = sorted(f"{x.item_id}|{x.fpg_id}" for x in records)
        new_fpgs = sorted({x.fpg_id for x in records if x.scenario == "PAIR0-N"})
        new_fpgs_by_stage[s] = set(new_fpgs)
        stage = StageSplit(
            name=s,
            origin_start=_d(lo),
            origin_end=_d(hi),
            origins=sorted({x.origin for x in records}),
            launches=records,
            excluded_pairs=excluded_pairs,
            excluded_fpgs=new_fpgs,
            counts={
                "launches": len(records),
                "ranked": sum(x.ranked for x in records),
                "PAIR0-E": sum(x.ranked and x.scenario == "PAIR0-E" for x in records),
                "PAIR0-N": sum(x.ranked and x.scenario == "PAIR0-N" for x in records),
                "edge_fixtures": sum(not x.ranked for x in records),
                "incomplete_labels": sum(x.label_status == "incomplete" for x in records),
            },
        )
        stages[s] = stage

    for i, a in enumerate(STAGE_ORDER):
        for b in STAGE_ORDER[i + 1 :]:
            overlap = new_fpgs_by_stage[a] & new_fpgs_by_stage[b]
            checks.append(
                SplitCheck(
                    check="new_fpg_cohorts_disjoint",
                    passed=not overlap,
                    stage=b,
                    detail=f"{a}/{b} new-FPG overlap: {sorted(overlap)}",
                )
            )

    def fit_for(stage: str, sources: list[str]) -> None:
        st = stages[stage]
        if not st.origins:
            return
        cutoff = to_ts(st.origins[0])
        st.fit_cutoff = _d(cutoff)
        for src in sources:
            for rec in stages[src].launches:
                if not rec.ranked:
                    continue
                avail = to_ts(rec.label_available_at) if rec.label_available_at else None
                if avail is not None and avail <= cutoff:
                    st.fit_launch_ids.append(rec.launch_id)
                else:
                    st.fit_exclusions.append(
                        {
                            "launch_id": rec.launch_id,
                            "reason": "labels incomplete"
                            if avail is None
                            else f"labels available {_d(avail)} after fit cutoff {_d(cutoff)}",
                        }
                    )
        latest = max(
            (
                to_ts(r.label_available_at)
                for s2 in sources
                for r in stages[s2].launches
                if r.launch_id in set(st.fit_launch_ids)
            ),
            default=None,
        )
        for o in st.origins:
            ok = latest is None or latest <= to_ts(o)
            checks.append(
                SplitCheck(
                    check="fit_labels_available_before_origin",
                    passed=ok,
                    stage=stage,
                    detail=f"origin {o}: latest fit label available {_d(latest)}",
                )
            )

    fit_for("validation", ["train"])
    fit_for("test", [s for s in cohorts.test_fit_stages if s in ("train", "validation")])

    for s in ("validation", "test"):
        st = stages[s]
        incomplete = [r.launch_id for r in st.launches if r.ranked and r.label_status == "incomplete"]
        checks.append(
            SplitCheck(
                check="scored_labels_complete",
                passed=not incomplete,
                stage=s,
                detail="all ranked launches have 52 target rows"
                if not incomplete
                else f"{len(incomplete)} ranked launches lack complete targets ({incomplete[:5]}); "
                "use a forecast-only workflow for launches without completed actuals",
            )
        )
        avail = [to_ts(r.label_available_at) for r in st.launches if r.label_available_at]
        st.scoring_cutoff = _d(max(avail)) if avail else None

    selection_cutoff = stages["validation"].scoring_cutoff
    if selection_cutoff and stages["test"].origins:
        ok = to_ts(selection_cutoff) <= to_ts(stages["test"].origins[0])
        checks.append(
            SplitCheck(
                check="selection_frozen_before_test",
                passed=ok,
                stage="test",
                detail=f"validation labels complete {selection_cutoff}; first test origin {stages['test'].origins[0]}",
            )
        )

    manifest = SplitManifest(
        dataset_id=md.dataset.id,
        dataset_version=md.dataset.version,
        dataset_hash=dataset.content_hash,
        metadata_hash=hash_obj(md.model_dump(mode="json", exclude={"dataset": {"expected_hash"}})),
        domain=md.domain_plugin,
        task_profile=md.task_profile,
        horizon_weeks=h,
        reporting_delay_days=delay,
        week_start=md.time.week_start,
        stages=stages,
        selection_cutoff=selection_cutoff,
        checks=checks,
    )
    return manifest.frozen()
