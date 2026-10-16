"""Licence gates: blocked benchmark data (VISUELLE) and opt-in-only research-only methods."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from xferbench.cli.main import app
from xferbench.data.classes import DataClassError, load_benchmark_manifest
from xferbench.methods.registry import entries_for_profile, research_only_ids
from xferbench.orchestration.runner import EXIT_LICENCE, BenchmarkRunner, RunConfig, RunError

runner = CliRunner()
RESEARCH_ONLY = {"FM.moirai2", "FM.tabpfn_ts", "EXT.pop", "FM.timesfm3"}


def _manifest(tmp_path: Path, **over: object) -> Path:
    man = {
        "benchmark_id": "public-x",
        "version": "1.0.0",
        "kind": "public",
        "licence": "CC-BY-4.0",
        "source": {"metadata": "metadata.json"},
        "dataset_hash": "",
    }
    man.update(over)
    p = tmp_path / "BENCHMARK.json"
    p.write_text(json.dumps(man))
    return p


def test_visuelle_blocklisted_as_benchmark(tmp_path: Path) -> None:
    for bid in ("visuelle-v1", "VISUELLE2"):
        with pytest.raises(DataClassError, match="licence-blocked"):
            load_benchmark_manifest(str(_manifest(tmp_path, benchmark_id=bid)))
    with pytest.raises(DataClassError, match="licence-blocked"):
        load_benchmark_manifest(str(_manifest(tmp_path, source={"url": "https://github.com/HumaticsLAB/visuelle2.0"})))


def test_usage_tag_blocked_refused(tmp_path: Path) -> None:
    with pytest.raises(DataClassError, match="usage_tag=blocked"):
        load_benchmark_manifest(str(_manifest(tmp_path, usage_tag="blocked")))


def test_unblocked_public_manifest_still_loads(tmp_path: Path) -> None:
    man, _ = load_benchmark_manifest(str(_manifest(tmp_path)))
    assert man["benchmark_id"] == "public-x"


def test_cli_blocked_benchmark_exits_2(tmp_path: Path) -> None:
    p = _manifest(tmp_path, benchmark_id="visuelle-2.0")
    r = runner.invoke(
        app,
        [
            "run",
            "--splits",
            str(tmp_path / "s.json"),
            "--stage",
            "validation",
            "--out",
            str(tmp_path / "o"),
            "--benchmark",
            str(p),
            "--benchmark-data",
            str(tmp_path / "d"),
        ],
    )
    assert r.exit_code == 2, r.output


def test_research_only_never_default() -> None:
    assert research_only_ids() >= RESEARCH_ONLY
    for prof in ("core", "all"):
        ids = {e.spec.method_id for e in entries_for_profile(prof)}
        assert not ids & research_only_ids()
    assert {e.spec.method_id for e in entries_for_profile("all", allow_research_only=True)} >= RESEARCH_ONLY


def test_explicit_research_only_needs_flag(tiny_split_path: Path) -> None:
    r = BenchmarkRunner(
        RunConfig(Path("m.json"), tiny_split_path, "validation", Path("unused"), methods=["FM.moirai2"])
    )
    with pytest.raises(RunError, match="--allow-research-only") as ei:
        r._requested(None)
    assert ei.value.exit_code == EXIT_LICENCE == 2
    ok = BenchmarkRunner(
        RunConfig(
            Path("m.json"), tiny_split_path, "validation", Path("unused"), methods=["EXT.pop"], allow_research_only=True
        )
    )
    chosen, explicit = ok._requested(None)
    assert [e.spec.method_id for e in chosen] == ["EXT.pop"] and explicit


def test_standard_run_labeled_standard(tiny_runs: dict[str, Path]) -> None:
    man = json.loads((tiny_runs["validation"] / "run_manifest.json").read_text())
    assert man["usage_label"] == "standard"
