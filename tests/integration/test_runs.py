"""End-to-end validation -> frozen selection -> test runs on the tiny synthetic preset."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from xferbench.contracts.methods import ModelArtifact
from xferbench.contracts.splits import SplitManifest
from xferbench.features.context import OriginContext
from xferbench.methods.base import RowResult, TrainingContext, expand, stateless_artifact
from xferbench.methods.baselines.rates import B0NationalRate
from xferbench.methods.registry import RegistryEntry, all_entries, register_method, unregister_method
from xferbench.orchestration.runner import BenchmarkRunner, RunConfig, RunError
from xferbench.reports.compare import CompareError, compare_runs
from xferbench.util import read_json


def _manifest(run: Path) -> dict:
    return read_json(run / "run_manifest.json")


def test_run_outputs_exist(tiny_runs: dict[str, Path]) -> None:
    for stage in ("validation", "test"):
        run = tiny_runs[stage]
        for name in (
            "run_manifest.json",
            "metrics.json",
            "forecasts.parquet",
            "leaderboard.csv",
            "slices.csv",
            "failures.csv",
            "method_support.json",
            "resources.json",
            "data_quality.json",
            "report.html",
            "summary.md",
        ):
            assert (run / name).exists(), f"{stage}/{name}"
        assert _manifest(run)["status"] == "complete"


def test_every_request_has_52_rows_per_variant(tiny_runs: dict[str, Path], tiny_split: SplitManifest) -> None:
    for stage in ("validation", "test"):
        fc = pd.read_parquet(tiny_runs[stage] / "forecasts.parquet")
        n_req = len(tiny_split.stages[stage].launches)
        for vid, grp in fc.groupby("variant_id"):
            assert grp["request_id"].nunique() == n_req, vid
            assert (grp.groupby("request_id")["horizon_week"].nunique() == 52).all(), vid
            ok = grp["status"].isin(["success", "fallback"])
            assert np.isfinite(grp.loc[ok, "point_units"]).all() and (grp.loc[ok, "point_units"] >= 0).all()
            assert grp.loc[~ok, "point_units"].isna().all()


def test_core_baselines_are_rankable_and_scenarios_reported(tiny_runs: dict[str, Path]) -> None:
    metrics = read_json(tiny_runs["validation"] / "metrics.json")
    rows = metrics["boards"]["cold_c0"]
    methods = {r["method_id"] for r in rows}
    assert {"B0", "B1", "B2", "B2.raw_units", "M1", "M2"} <= methods
    for r in rows:
        assert set(r["scenarios"]) == {"PAIR0-E", "PAIR0-N"}
        assert r["rankable"], r["variant_id"]
        assert r["scenarios"]["PAIR0-E"]["n_launches"] > 0 and r["scenarios"]["PAIR0-N"]["n_launches"] > 0
    assert len({r["variant_id"] for r in rows if r["method_id"] == "B2"}) == 4


def test_same_population_for_every_method(tiny_runs: dict[str, Path]) -> None:
    metrics = read_json(tiny_runs["test"] / "metrics.json")
    rows = metrics["boards"]["cold_c0"]
    for s in ("PAIR0-E", "PAIR0-N"):
        assert len({r["scenarios"][s]["n_eligible"] for r in rows}) == 1


def test_edge_fixtures_are_unranked_and_visible(tiny_runs: dict[str, Path]) -> None:
    metrics = read_json(tiny_runs["test"] / "metrics.json")
    assert "edge_fixtures" in metrics["boards"]
    assert all(r["rank"]["objective"] is None for r in metrics["boards"]["edge_fixtures"])
    kinds = {f["fixture_kind"] for f in metrics["edge_fixture_status"]}
    assert {"missing_propensity", "unknown_attributes"} <= kinds
    m1 = [
        f
        for f in metrics["edge_fixture_status"]
        if f["fixture_kind"] == "missing_propensity" and f["variant_id"] == "M1"
    ]
    assert m1 and "failed" in m1[0]["statuses"]


def test_selection_uses_symmetric_bias_limit(tiny_runs: dict[str, Path]) -> None:
    sel = read_json(tiny_runs["selection"])
    fam = {f["method_id"]: f for f in sel["families"]}
    metrics = read_json(tiny_runs["validation"] / "metrics.json")
    for r in metrics["boards"]["cold_c0"]:
        too_biased = any(abs(r["scenarios"][s]["Bias"]) > 0.5 for s in ("PAIR0-E", "PAIR0-N"))
        if too_biased:
            assert r["variant_id"] in {x["variant_id"] for x in sel["rejected_variants"]}
    if not fam["B2.raw_units"]["eligible"]:
        assert "Bias" in fam["B2.raw_units"]["reason"]
    assert sel["recommended"] in {f["variant_id"] for f in sel["families"] if f["eligible"]}


def test_test_run_scores_only_frozen_variants(tiny_runs: dict[str, Path]) -> None:
    sel = read_json(tiny_runs["selection"])
    frozen = {f["variant_id"] for f in sel["families"] if f["eligible"]}
    fc = pd.read_parquet(tiny_runs["test"] / "forecasts.parquet")
    assert set(fc["variant_id"]) == frozen
    assert _manifest(tiny_runs["test"])["selection"]["validation_run_id"] == sel["validation_run_id"]


def test_test_requires_selection(tiny_runs: dict[str, Path], tmp_path: Path) -> None:
    cfg = RunConfig(tiny_runs["metadata"], tiny_runs["splits"], "test", tmp_path / "t")
    with pytest.raises(RunError, match="requires --selection"):
        BenchmarkRunner(cfg).run()


def test_tampered_selection_rejected(tiny_runs: dict[str, Path], tmp_path: Path) -> None:
    sel = read_json(tiny_runs["selection"])
    sel["split_hash"] = "f" * 64
    p = tmp_path / "selection.json"
    p.write_text(json.dumps(sel))
    cfg = RunConfig(tiny_runs["metadata"], tiny_runs["splits"], "test", tmp_path / "t", selection_path=p)
    with pytest.raises(RunError, match="different dataset/split"):
        BenchmarkRunner(cfg).run()


def test_output_directory_is_append_only(tiny_runs: dict[str, Path]) -> None:
    cfg = RunConfig(tiny_runs["metadata"], tiny_runs["splits"], "validation", tiny_runs["validation"])
    with pytest.raises(RunError, match="append-only"):
        BenchmarkRunner(cfg).run()


def test_explicit_m3_is_rejected_not_substituted(tiny_runs: dict[str, Path], tmp_path: Path) -> None:
    cfg = RunConfig(tiny_runs["metadata"], tiny_runs["splits"], "validation", tmp_path / "m3", methods=["M3"])
    with pytest.raises(RunError) as exc:
        BenchmarkRunner(cfg).run()
    assert exc.value.exit_code == 3
    assert "config_required" in str(exc.value) or "M3" in str(exc.value)


def test_budget_stop_reports_partial(tiny_runs: dict[str, Path], tmp_path: Path) -> None:
    cfg = RunConfig(
        tiny_runs["metadata"], tiny_runs["splits"], "validation", tmp_path / "p", methods=["B0"], max_seconds=1e-6
    )
    res = BenchmarkRunner(cfg).run()
    assert res.status == "partial" and res.exit_code == 4
    assert _manifest(res.out)["status"] == "partial"
    lb = pd.read_csv(res.out / "leaderboard.csv")
    assert lb["rank"].isna().all() and not lb["rankable"].any()
    metrics = read_json(res.out / "metrics.json")
    assert all(not r["rankable"] for r in metrics["boards"]["cold_c0"])


def test_unknown_method_rejected(tiny_runs: dict[str, Path], tmp_path: Path) -> None:
    cfg = RunConfig(tiny_runs["metadata"], tiny_runs["splits"], "validation", tmp_path / "u", methods=["NOPE"])
    with pytest.raises(RunError) as exc:
        BenchmarkRunner(cfg).run()
    assert exc.value.exit_code == 3


def test_every_registry_entry_accounted_for(tiny_runs: dict[str, Path]) -> None:
    support = read_json(tiny_runs["validation"] / "method_support.json")["entries"]
    assert {s["method_id"] for s in support} == {e.spec.method_id for e in all_entries()}
    by_id = {s["method_id"]: s for s in support}
    assert by_id["M3"]["implementation_state"] == "config_required"
    assert by_id["M3"]["execution_state"] == "not_run"
    assert by_id["FM.timesfm3"]["eligibility_state"] == "license_blocked"
    assert by_id["SVC.timegpt"]["eligibility_state"] == "service_required"
    assert by_id["REF.croston_sba"]["eligibility_state"] == "unsupported_history"
    for s in support:
        if s["implementation_state"] != "implemented":
            assert s["execution_state"] != "success", s["method_id"]


class _SpyMethod:
    """External adapter registered at runtime; records what training data it was given."""

    seen: dict[str, Any] = {}

    def __init__(self) -> None:
        self.spec = B0NationalRate.spec.model_copy(
            update={
                "method_id": "EXT.spy",
                "display_name": "<script>alert(1)</script> spy",
                "family": "external",
                "rights": B0NationalRate.spec.rights.model_copy(update={"code_source": "tests"}),
            }
        )

    def capabilities(self):  # type: ignore[no-untyped-def]
        return self.spec

    def variants(self) -> list[dict[str, Any]]:
        return [{"scale": 1.0}]

    def fit(self, training: TrainingContext, inner: TrainingContext | None, config: dict[str, Any]) -> ModelArtifact:
        _SpyMethod.seen["fit_ids"] = set(training.requests["request_id"])
        _SpyMethod.seen["label_ids"] = set(training.labels["request_id"]) if len(training.labels) else set()
        _SpyMethod.seen["cutoff"] = training.fit_cutoff
        return stateless_artifact(self.spec, training, config, "spy", self.variants())

    def predict_batch(self, requests: pd.DataFrame, ctx: OriginContext, artifact: ModelArtifact) -> pd.DataFrame:
        _SpyMethod.seen.setdefault("max_obs_week", []).append(ctx.observations["week_end"].max() <= ctx.origin)
        return expand(
            requests,
            [RowResult(r.request_id, np.full(52, 1.0), "success") for r in requests.itertuples(index=False)],
            52,
        )


@pytest.fixture
def spy_registered():  # type: ignore[no-untyped-def]
    m = _SpyMethod()
    register_method(RegistryEntry(spec=m.spec, implementation_state="experimental", factory=_SpyMethod))
    yield
    unregister_method("EXT.spy")


def test_external_method_and_training_boundary(
    spy_registered,
    tiny_runs: dict[str, Path],  # type: ignore[no-untyped-def]
    tiny_split: SplitManifest,
    tmp_path: Path,
) -> None:
    res = BenchmarkRunner(
        RunConfig(tiny_runs["metadata"], tiny_runs["splits"], "validation", tmp_path / "ext", methods=["EXT.spy", "B0"])
    ).run()
    assert res.exit_code == 0
    st = tiny_split.stages["validation"]
    assert _SpyMethod.seen["fit_ids"] == set(st.fit_launch_ids)
    assert _SpyMethod.seen["label_ids"] <= set(st.fit_launch_ids)
    assert not _SpyMethod.seen["fit_ids"] & {r.launch_id for r in st.launches}
    assert all(_SpyMethod.seen["max_obs_week"])
    lb = pd.read_csv(res.out / "leaderboard.csv")
    assert "EXT.spy" in set(lb["variant_id"])
    html = (res.out / "report.html").read_text()
    assert "<script>alert(1)</script>" not in html
    assert not re.search(r'(?:src|href)="https?://', html)
    assert "Content-Security-Policy" in html


def test_compare_runs(tiny_runs: dict[str, Path], tmp_path: Path) -> None:
    out = compare_runs([tiny_runs["validation"], tiny_runs["validation"]], tmp_path / "cmp.html")
    assert (tmp_path / "cmp.html").exists() and out
    with pytest.raises(CompareError):
        compare_runs([tiny_runs["validation"], tiny_runs["test"]], tmp_path / "bad.html")


def test_report_has_both_scenarios_and_no_raw_rows(tiny_runs: dict[str, Path], tiny_dir: Path) -> None:
    html = (tiny_runs["test"] / "report.html").read_text()
    for needle in ("PAIR0-E", "PAIR0-N", "Frozen validation selection", "Edge fixtures", "Synthetic data"):
        assert needle in html
    truth = list((tiny_dir / "_synthetic_truth").glob("*"))
    assert truth, "synthetic truth should be written separately"
    assert "_synthetic_truth" not in html
