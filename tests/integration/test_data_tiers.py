"""Owner request 2026-10-24: every run states its data tier (synthetic | sample | complete); tiers are a config-only
switch inside one experiment; default output eval/<exp_id>__<tier>/; compare and summaries refuse to mix tiers (exit 2).

The sample/complete runs here use generated data relabelled as non-synthetic: an interface test of the tier
plumbing only, not a result on real data."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from xferbench.cli.main import app
from xferbench.data.tiers import TierError, TierMixError, require_single_tier, resolve_tier
from xferbench.experiments.runner import ExperimentConfig, ExperimentError
from xferbench.experiments.workspace import run_one, summary_table

ROOT = Path(__file__).resolve().parents[2]
EXP = "exp02_synthetic_chronos_zero_shot"


def test_resolve_tier_rules() -> None:
    assert resolve_tier(None, True) == "synthetic" and resolve_tier(None, False) == "complete"
    assert resolve_tier("sample", False) == "sample"
    for req, syn in (("sample", True), ("complete", True), ("synthetic", False), ("full", False)):
        with pytest.raises(TierError):
            resolve_tier(req, syn)


def test_require_single_tier() -> None:
    assert require_single_tier([("a", "sample"), ("b", "sample")]) == "sample"
    with pytest.raises(TierMixError, match="sample: a; synthetic: b"):
        require_single_tier([("a", "sample"), ("b", "synthetic")])
    with pytest.raises(TierMixError, match="unlabeled"):
        require_single_tier([("a", None), ("b", "complete")])


def test_summary_table_refuses_mixed_tiers() -> None:
    row = {"status": "ok", "ran": 1, "not_run": 0, "out": "", "detail": ""}
    with pytest.raises(TierMixError):
        summary_table([{**row, "experiment": "a", "tier": "synthetic"}, {**row, "experiment": "b", "tier": "sample"}])


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    r = tmp_path_factory.mktemp("tiers")
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    shutil.copy(ROOT / ".gitignore", r / ".gitignore")
    shutil.copytree(ROOT / "experiments" / EXP, r / "experiments" / EXP, ignore=shutil.ignore_patterns("runs"))
    assert (
        CliRunner().invoke(app, ["synth", "generate", "--out", str(r / "local/s"), "--preset", "tiny"]).exit_code == 0
    )
    md = r / "local/s/metadata.json"
    m = json.loads(md.read_text(encoding="utf-8"))
    m["dataset"]["synthetic"] = False  # stand-in for the user's own data (tier plumbing test only)
    md.write_text(json.dumps(m), encoding="utf-8")
    for t in ("sample", "complete"):
        p = r / "experiments" / EXP / "configs" / f"{t}.yaml"
        p.write_text(p.read_text(encoding="utf-8").replace('metadata: ""', f"metadata: {md}"), encoding="utf-8")
    for t in ("synthetic", "sample", "complete"):
        run_one(EXP, r, progress=lambda _m: None, tier=t)
    return r


@pytest.mark.parametrize("tier", ["synthetic", "sample", "complete"])
def test_tier_is_written_everywhere(repo: Path, tier: str) -> None:
    out = repo / "eval" / f"{EXP}__{tier}"
    assert out.is_dir()
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert res["tier"] == tier and {r["tier"] for r in res["test_rows"]} == {tier}
    for run in ("validation-run", "test-run"):
        assert json.loads((out / run / "run_manifest.json").read_text(encoding="utf-8"))["tier"] == tier
        assert json.loads((out / run / "metrics.json").read_text(encoding="utf-8"))["tier"] == tier
        assert set(pd.read_csv(out / run / "leaderboard.csv")["tier"]) == {tier}
        assert f"Data tier: {tier}" in (out / run / "summary.md").read_text(encoding="utf-8").replace("*", "")
        assert f"Data tier: <b>{tier}</b>" in (out / run / "report.html").read_text(encoding="utf-8")
    assert f"Data tier: <b>{tier}</b>" in (out / "leaderboard.html").read_text(encoding="utf-8")
    assert f"<td>{tier}</td>" in (out / "leaderboard.html").read_text(encoding="utf-8")
    assert f"Data tier: {tier}" in (out / "SUMMARY.md").read_text(encoding="utf-8").replace("*", "")
    banner = "LOCAL DATA: results on your own data" in (out / "report.html").read_text(encoding="utf-8")
    assert banner == (tier != "synthetic")  # benchmark/local separation and the LOCAL DATA banner are kept
    sel = json.loads((out / "_work/selection.json").read_text(encoding="utf-8"))
    assert sel["tier"] == tier and sel["data_class"] == ("synthetic" if tier == "synthetic" else "local")


def test_compare_refuses_mixed_tiers_exit_2(repo: Path) -> None:
    r = CliRunner()
    a, b = (str(repo / "eval" / f"{EXP}__{t}" / "test-run") for t in ("sample", "complete"))
    for extra in ([], ["--allow-incompatible"]):
        res = r.invoke(app, ["compare", "--runs", a, "--runs", b, "--out", str(repo / "eval/mix.html"), *extra])
        assert res.exit_code == 2 and "refusing to mix data tiers" in res.output
    assert not (repo / "eval/mix.html").exists()
    s = str(repo / "eval" / f"{EXP}__synthetic" / "test-run")
    res = r.invoke(app, ["compare", "--runs", a, "--runs", s, "--out", str(repo / "eval/mix2.html")])
    assert res.exit_code == 2  # tier check comes before the data-class check
    same = [str(repo / "eval" / f"{EXP}__sample" / x) for x in ("validation-run", "test-run")]
    res = r.invoke(
        app,
        [
            "compare",
            "--runs",
            same[0],
            "--runs",
            same[1],
            "--out",
            str(repo / "eval/same.html"),
            "--allow-incompatible",
        ],
    )
    assert res.exit_code == 0 and "tier sample" in res.output


def test_second_run_gets_a_new_folder_and_cli_prints_tier(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    res = CliRunner().invoke(app, ["experiment", "run", EXP])
    assert res.exit_code == 0, res.output
    assert "data tier: synthetic" in res.output and (repo / "eval" / f"{EXP}__synthetic-2" / "results.json").exists()


def test_bad_tier_and_missing_metadata_exit_2(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    r = CliRunner()
    assert r.invoke(app, ["experiment", "run", EXP, "--tier", "full"]).exit_code == 2
    shutil.copytree(ROOT / "experiments" / EXP, tmp_path / EXP, ignore=shutil.ignore_patterns("runs"))
    with pytest.raises(ExperimentError, match=r"needs data\.metadata"):
        ExperimentConfig.load(tmp_path / EXP / "config.yaml", "complete")


def test_synthetic_data_cannot_be_labelled_sample(repo: Path, tmp_path: Path) -> None:
    gen = tmp_path / "g"
    assert CliRunner().invoke(app, ["synth", "generate", "--out", str(gen), "--preset", "tiny"]).exit_code == 0
    d = repo / "experiments" / EXP / "configs" / "sample.yaml"
    old = d.read_text(encoding="utf-8")
    try:
        d.write_text(f"data:\n  metadata: {gen / 'metadata.json'}\n", encoding="utf-8")
        with pytest.raises(ExperimentError, match="synthetic"):
            run_one(EXP, repo, progress=lambda _m: None, tier="sample", out=repo / "eval/should-not-run")
    finally:
        d.write_text(old, encoding="utf-8")


def test_shipped_experiments_switch_tier_by_config_only() -> None:
    for d in sorted((ROOT / "experiments").glob("exp0[12]_*")):
        assert ExperimentConfig.load(d / "config.yaml").tier == "synthetic"
        for t in ("sample", "complete"):
            assert (d / "configs" / f"{t}.yaml").is_file()
