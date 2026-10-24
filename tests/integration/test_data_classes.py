"""Benchmark data vs local data separation (docs/DATA_CLASSES.md)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from xferbench.cli.main import app
from xferbench.data.classes import (
    DataClassError,
    check_local_output,
    list_benchmarks,
    materialize_benchmark,
    redact_ids,
    resolve_source,
)
from xferbench.domains.registry import get_domain
from xferbench.util import write_json

runner = CliRunner()
SENT = "ZZSENTINEL"


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    shutil.copyfile(Path(__file__).resolve().parents[2] / ".gitignore", path / ".gitignore")
    return path


@pytest.fixture(scope="module")
def local_copy(tiny_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Tiny data with every item/FPG/launch ID prefixed by a sentinel, posing as the user's own data."""
    dst = tmp_path_factory.mktemp("userdata") / "mydata"
    shutil.copytree(tiny_dir, dst, ignore=shutil.ignore_patterns("*.csv", "metadata.csv.json", "_synthetic_truth"))
    for p in (dst / "data").glob("*.parquet"):
        df = pd.read_parquet(p)
        for c in ("item_id", "fpg_id", "launch_id", "donor_fpg_id"):
            if c in df.columns:
                df[c] = df[c].map(lambda v: None if v is None or pd.isna(v) else f"{SENT}{v}")
        df.to_parquet(p, index=False)
    md = json.loads((dst / "metadata.json").read_text(encoding="utf-8"))
    md["dataset"]["expected_hash"] = None
    md["dataset"]["synthetic"] = False
    (dst / "metadata.json").write_text(json.dumps(md), encoding="utf-8")
    return dst / "metadata.json"


def test_builtin_benchmarks_listed_and_hash_verified(tmp_path: Path) -> None:
    assert {"synthetic-tiny@1.1.0", "synthetic-small@1.1.0"} <= set(list_benchmarks())
    src = materialize_benchmark("synthetic-tiny@1.1.0", tmp_path / "bench")
    assert src.data_class == "benchmark" and src.benchmark_id == "synthetic-tiny"


def test_tampered_benchmark_rejected(tmp_path: Path) -> None:
    d = tmp_path / "bench"
    materialize_benchmark("synthetic-tiny@1.1.0", d)
    p = d / "data" / "items.parquet"
    df = pd.read_parquet(p)
    df.loc[0, "category"] = "tampered"
    df.to_parquet(p, index=False)
    with pytest.raises(DataClassError, match="hash mismatch"):
        materialize_benchmark("synthetic-tiny@1.1.0", d)


def test_exactly_one_source_and_legacy_metadata_is_local(tmp_path: Path) -> None:
    with pytest.raises(DataClassError):
        resolve_source(benchmark="synthetic-tiny@1.1.0", local_data=tmp_path, metadata=None, data_dir=tmp_path)
    with pytest.warns(UserWarning, match="LOCAL"):
        src = resolve_source(benchmark=None, local_data=None, metadata=tmp_path / "metadata.json")
    assert src.data_class == "local"
    inside = tmp_path / "benchmarks" / "x" / "1" / "metadata.json"
    assert resolve_source(benchmark=None, local_data=None, metadata=inside).data_class == "benchmark"


def test_local_output_inside_repo_must_be_gitignored(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    with pytest.raises(DataClassError, match="not ignored"):
        check_local_output(repo / "shared_out")
    check_local_output(repo / "runs" / "local" / "r1")  # ignored -> allowed
    check_local_output(repo / "local" / "out")
    check_local_output(tmp_path / "outside")  # not a work tree -> allowed


def test_gitignore_keeps_local_data_out_of_git(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    for rel in (
        "local/sales.parquet",
        "runs/local/r/report.html",
        "my.local.csv",
        "runs/benchmark/x/report.html",
        "data/complete_data/input/sales.parquet",
        "data/sample_data/output/x.csv",
    ):
        r = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", rel])
        assert r.returncode == 0, rel


def test_redact_ids_longest_first() -> None:
    out = redact_ids("a I1 b I10 c XI1", {"I1", "I10"}, "s")
    assert "I1 " not in out and "I10" not in out and "XI1" in out


def test_cli_rejects_mixed_flags(tmp_path: Path, tiny_split_path: Path) -> None:
    res = runner.invoke(
        app,
        [
            "run",
            "--benchmark",
            "synthetic-tiny@1.1.0",
            "--benchmark-data",
            str(tmp_path / "b"),
            "--local-data",
            str(tmp_path / "m.json"),
            "--splits",
            str(tiny_split_path),
            "--stage",
            "validation",
            "--out",
            str(tmp_path / "o"),
        ],
    )
    assert res.exit_code == 2


def test_local_run_is_labeled_and_leaks_no_ids(local_copy: Path, tmp_path: Path) -> None:
    from xferbench.data.io import load_from_metadata_path

    ds = load_from_metadata_path(local_copy)
    split = get_domain("retail").build_splits(ds)
    sp = tmp_path / "splits.json"
    write_json(sp, split.model_dump(mode="json"))
    out = tmp_path / "local-run"
    res = runner.invoke(
        app,
        ["run", "--local-data", str(local_copy), "--splits", str(sp), "--stage", "validation", "--out", str(out)],
    )
    assert res.exit_code == 0, res.output
    man = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert man["data"]["data_class"] == "local"
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "LOCAL DATA" in html
    for name in (
        "report.html",
        "summary.md",
        "leaderboard.csv",
        "slices.csv",
        "failures.csv",
        "metrics.json",
        "data_quality.json",
        "method_support.json",
        "run_manifest.json",
    ):
        p = out / name
        if p.exists():
            assert SENT not in p.read_text(encoding="utf-8"), f"sentinel ID leaked into {name}"


def test_compare_refuses_mixed_classes(tiny_runs: dict[str, Path], tmp_path: Path) -> None:
    from xferbench.reports.compare import CompareError, compare_runs

    a, b = tmp_path / "a", tmp_path / "b"
    shutil.copytree(tiny_runs["test"], a)
    shutil.copytree(tiny_runs["test"], b)
    m = json.loads((b / "run_manifest.json").read_text(encoding="utf-8"))
    m["data"] = {"data_class": "local"}
    (b / "run_manifest.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(CompareError, match="data classes"):
        compare_runs([a, b], tmp_path / "c.html")


def test_demo_is_labeled_benchmark(tmp_path: Path) -> None:
    res = runner.invoke(app, ["demo", "--preset", "tiny", "--out", str(tmp_path / "d")])
    assert res.exit_code == 0, res.output
    man = json.loads((tmp_path / "d" / "test-run" / "run_manifest.json").read_text(encoding="utf-8"))
    assert man["data"] == {
        "data_class": "benchmark",
        "benchmark_id": "synthetic-tiny",
        "benchmark_version": "1.1.0",
        "benchmark_kind": "synthetic",
    }
