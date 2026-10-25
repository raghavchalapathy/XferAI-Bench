"""v4 usability: experiment workspaces (new / list / run / run-all) and their guardrails."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from xferbench.cli.main import app
from xferbench.experiments.runner import ExperimentConfig, ExperimentError
from xferbench.experiments.workspace import list_experiments, new_experiment, run_all, summary_table, validate_name

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "experiments", tmp_path / "experiments", ignore=shutil.ignore_patterns("runs"))
    return tmp_path


@pytest.mark.parametrize("bad", ["", "ab", "Exp1", "1exp", "../x", "a/b", "x-y", "a" * 65, "exp01 ", "é_x"])
def test_name_validation_rejects(bad: str) -> None:
    with pytest.raises(ExperimentError):
        validate_name(bad)


def test_new_scaffold_is_valid_and_standard(repo: Path) -> None:
    d = new_experiment("exp03_mine", repo)
    assert sorted(p.name for p in d.iterdir()) == ["README.md", "config.yaml"]
    cfg = ExperimentConfig.load(d / "config.yaml")
    assert cfg.id == "exp03_mine" and cfg.backend == "polars" and cfg.mode == "local"
    text = (d / "README.md").read_text(encoding="utf-8")
    for needle in ("Paper", "Data:", "Models:", "xferbench experiment run exp03_mine", "not a ranking"):
        assert needle in text


def test_new_from_copies_config_but_not_runs(repo: Path) -> None:
    src = repo / "experiments/exp01_m5_lightgbm_analogs"
    (src / "runs/20260101T000000Z").mkdir(parents=True)
    (src / "notes.md").write_text("extra", encoding="utf-8")
    d = new_experiment("exp04_copy", repo, from_id="exp01_m5_lightgbm_analogs")
    a = yaml.safe_load((src / "config.yaml").read_text(encoding="utf-8"))
    b = yaml.safe_load((d / "config.yaml").read_text(encoding="utf-8"))
    assert b["id"] == "exp04_copy" and {k: v for k, v in a.items() if k != "id"} == {
        k: v for k, v in b.items() if k != "id"
    }
    assert (d / "notes.md").read_text(encoding="utf-8") == "extra"
    assert not (d / "runs").exists()


def test_new_from_unknown_fails(repo: Path) -> None:
    with pytest.raises(ExperimentError, match="not found"):
        new_experiment("exp05_x", repo, from_id="nope_missing")


def test_no_overwrite_without_force(repo: Path) -> None:
    d = new_experiment("exp06_x", repo)
    (d / "config.yaml").write_text((d / "config.yaml").read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    with pytest.raises(ExperimentError, match="--force"):
        new_experiment("exp06_x", repo)
    assert "# edited" in (d / "config.yaml").read_text(encoding="utf-8")
    new_experiment("exp06_x", repo, force=True)
    assert "# edited" not in (d / "config.yaml").read_text(encoding="utf-8")


def test_cli_new_list_and_errors(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    r = CliRunner()
    assert r.invoke(app, ["experiment", "new", "exp07_cli", "--from", "exp02_chronos_zero_shot"]).exit_code == 0
    assert r.invoke(app, ["experiment", "new", "exp07_cli"]).exit_code == 2
    assert r.invoke(app, ["experiment", "new", "Bad-Name"]).exit_code == 2
    out = r.invoke(app, ["experiment", "list"]).output
    assert "exp01_m5_lightgbm_analogs" in out and "exp07_cli" in out
    assert "NOT A DAY-ZERO RESULT" in out.split("exp07_cli")[1]


def test_list_reports_invalid_config(repo: Path) -> None:
    bad = repo / "experiments/zz_broken"
    bad.mkdir()
    (bad / "config.yaml").write_text("id: zz_broken\nmethods: []\n", encoding="utf-8")
    info = {i.id: i for i in list_experiments(repo)}
    assert info["zz_broken"].error


def test_run_all_continues_past_failures(repo: Path) -> None:
    keep = {"exp02_chronos_zero_shot"}
    for d in (repo / "experiments").iterdir():
        if d.is_dir() and d.name not in keep:
            shutil.rmtree(d)
    bad = repo / "experiments/aa_fails"
    bad.mkdir()
    (bad / "config.yaml").write_text(
        yaml.safe_dump({"id": "aa_fails", "methods": ["NOPE_METHOD"], "data": {"flavour": "synthetic"}}),
        encoding="utf-8",
    )
    inv = repo / "experiments/ab_invalid"
    inv.mkdir()
    (inv / "config.yaml").write_text("id: ab_invalid\nmethods: []\n", encoding="utf-8")
    rows = run_all(repo, progress=lambda _m: None)
    status = {r["experiment"]: r["status"] for r in rows}
    assert status == {"aa_fails": "failed", "ab_invalid": "invalid_config", "exp02_chronos_zero_shot": "ok"}
    assert [r["experiment"] for r in rows] == sorted(status)  # alphabetical, never by score
    ok = next(r for r in rows if r["status"] == "ok")
    out = Path(ok["out"])
    assert out.parent.name == "runs" and (out / "leaderboard.html").exists()
    assert not (out / "selection.json").exists() and (out / "_work/selection.json").exists()
    table = summary_table(rows)
    assert "not a ranking" in table and "rank" not in table.lower().replace("not a ranking", "")
    assert "NOT A DAY-ZERO RESULT" in table


def test_runtime_config_validation(tmp_path: Path) -> None:
    def load(rt: dict) -> ExperimentConfig:
        p = tmp_path / "c.yaml"
        p.write_text(
            yaml.safe_dump({"id": "x", "methods": ["B0"], "data": {"flavour": "synthetic"}, "runtime": rt}),
            encoding="utf-8",
        )
        return ExperimentConfig.load(p)

    assert load({"backend": "spark", "mode": "cluster", "master": "yarn"}).master == "yarn"
    for bad in ({"backend": "dask"}, {"mode": "cloud"}, {"backend": "polars", "mode": "cluster"}):
        with pytest.raises(ExperimentError):
            load(bad)


def test_runs_dirs_are_gitignored() -> None:
    p = "experiments/exp01_m5_lightgbm_analogs/runs/20260101T000000Z/results.json"
    r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", p], check=False)
    assert r.returncode == 0, "experiments/<id>/runs/ must be git-ignored"


def test_every_experiment_readme_states_paper_data_models_run() -> None:
    for d in sorted((ROOT / "experiments").glob("*/config.yaml")):
        text = (d.parent / "README.md").read_text(encoding="utf-8")
        for needle in ("Paper", "Data", "Models", f"xferbench experiment run {d.parent.name}"):
            assert needle in text, (d.parent.name, needle)
