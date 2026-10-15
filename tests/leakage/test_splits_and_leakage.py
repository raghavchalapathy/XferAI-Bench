"""Chronology, zero-history and holdout-exclusion guarantees."""

from __future__ import annotations

import pandas as pd

from tests import handmade as hm
from xferbench.contracts.splits import SplitManifest
from xferbench.data.io import Dataset
from xferbench.domains.registry import get_domain
from xferbench.features.context import ContextBuilder, Exclusions
from xferbench.methods.base import TrainingContext
from xferbench.methods.baselines.rates import B2AnalogRate

DOMAIN = get_domain("retail")


def test_all_split_checks_pass(tiny_split: SplitManifest) -> None:
    assert tiny_split.verify()
    assert not tiny_split.failed_checks
    checks = {c.check for c in tiny_split.checks}
    assert {
        "chronological_stage_windows",
        "c0_zero_own_pair_history",
        "new_fpg_zero_transactions",
        "new_fpg_cohorts_disjoint",
        "fit_labels_available_before_origin",
        "scored_labels_complete",
        "selection_frozen_before_test",
    } <= checks


def test_tampered_split_fails_hash(tiny_split: SplitManifest) -> None:
    bad = tiny_split.model_copy(deep=True)
    bad.stages["test"].launches = bad.stages["test"].launches[1:]
    assert not bad.verify()


def test_stages_chronological_and_new_fpgs_disjoint(tiny_split: SplitManifest) -> None:
    st = tiny_split.stages
    assert max(st["train"].origins) < min(st["validation"].origins) < min(st["test"].origins)
    new = {s: {r.fpg_id for r in st[s].launches if r.scenario == "PAIR0-N"} for s in st}
    assert not (new["train"] & new["validation"]) and not (new["validation"] & new["test"])
    assert not (new["train"] & new["test"])


def test_both_scenarios_present_each_stage(tiny_split: SplitManifest) -> None:
    for s, stage in tiny_split.stages.items():
        assert {r.scenario for r in stage.launches if r.ranked} == {"PAIR0-E", "PAIR0-N"}, s


def test_fit_labels_available_before_fit_cutoff(tiny: Dataset, tiny_split: SplitManifest) -> None:
    ids = {r.launch_id: r for st in tiny_split.stages.values() for r in st.launches}
    delay = pd.Timedelta(days=tiny.metadata.time.reporting_delay_days)
    for stage in ("validation", "test"):
        cutoff = pd.Timestamp(tiny_split.stages[stage].fit_cutoff)
        assert tiny_split.stages[stage].fit_launch_ids
        for lid in tiny_split.stages[stage].fit_launch_ids:
            rec = ids[lid]
            label_end = pd.Timestamp(rec.origin) + pd.Timedelta(weeks=52)
            assert label_end + delay <= cutoff, lid
            assert pd.Timestamp(rec.label_available_at) <= cutoff, lid
            assert rec.launch_id not in {r.launch_id for r in tiny_split.stages[stage].launches}


def test_stage_contexts_exclude_holdouts(tiny: Dataset, tiny_split: SplitManifest) -> None:
    for stage in ("validation", "test"):
        st = tiny_split.stages[stage]
        builder = DOMAIN.context_builder(tiny, tiny_split, stage)
        new_fpgs = {r.fpg_id for r in st.launches if r.scenario == "PAIR0-N"}
        assert new_fpgs <= set(st.excluded_fpgs)
        ctx = builder.at(st.origins[-1])
        assert not set(ctx.observations["fpg_id"]) & set(st.excluded_fpgs)
        pairs = set(zip(ctx.observations["item_id"], ctx.observations["fpg_id"], strict=True))
        held = {tuple(p.split("|", 1)) for p in st.excluded_pairs}
        assert not pairs & held


def test_context_only_contains_origin_valid_rows(tiny: Dataset, tiny_split: SplitManifest) -> None:
    st = tiny_split.stages["test"]
    ctx = DOMAIN.context_builder(tiny, tiny_split, "test").at(st.origins[0])
    o = ctx.origin
    assert (ctx.observations["week_end"] <= o).all() and (ctx.observations["known_at"] <= o).all()
    assert (ctx.items["known_at"] <= o).all() and (ctx.locations["effective_from"] <= o).all()
    assert (ctx.origin_features["known_at"] <= o).all()
    assert (ctx.origin_features["origin"] == o).all()


def test_mutating_future_data_does_not_change_context_or_forecast() -> None:
    def run(ds: Dataset) -> tuple[str, pd.Series]:
        ctx = ContextBuilder(ds, Exclusions(fpgs=frozenset({"X"}))).at(hm.ORIGIN)
        m = B2AnalogRate()
        tc = TrainingContext(pd.DataFrame(), pd.DataFrame(), hm.ORIGIN, "h", lambda _: None)  # type: ignore[arg-type,return-value]
        out = m.predict_batch(hm.request(), ctx, m.fit(tc, None, m.variants()[0]))
        return ctx.content_hash(), out["point_units"]

    ds = hm.build()
    h0, f0 = run(ds)
    fut = {k: v.copy() for k, v in ds.tables.items()}
    obs = fut["observations"]
    future = obs["week_start"] >= hm.ORIGIN - pd.Timedelta(days=7)
    obs.loc[future, "units"] = obs.loc[future, "units"] * 1000 + 5
    fut["locations"] = pd.concat(
        [
            fut["locations"],
            fut["locations"]
            .iloc[[0]]
            .assign(
                households=1e6,
                effective_from=hm.ORIGIN + pd.Timedelta(days=1),
                known_at=hm.ORIGIN + pd.Timedelta(days=1),
            ),
        ]
    )
    h1, f1 = run(Dataset(ds.metadata, ds.base_dir, fut))
    assert h0 == h1
    pd.testing.assert_series_equal(f0, f1)


def test_pair0_n_targets_have_no_location_history(tiny: Dataset, tiny_split: SplitManifest) -> None:
    obs = tiny["observations"]
    for st in tiny_split.stages.values():
        for r in st.launches:
            if r.scenario != "PAIR0-N":
                continue
            prior = obs[(obs["fpg_id"] == r.fpg_id) & (obs["week_start"] < pd.Timestamp(r.origin))]
            assert prior.empty, r.launch_id


def test_target_pairs_have_zero_own_history(tiny: Dataset, tiny_split: SplitManifest) -> None:
    obs = tiny["observations"]
    for st in tiny_split.stages.values():
        for r in st.launches:
            prior = obs[
                (obs["item_id"] == r.item_id)
                & (obs["fpg_id"] == r.fpg_id)
                & (obs["week_start"] < pd.Timestamp(r.origin))
            ]
            assert prior.empty, r.launch_id
