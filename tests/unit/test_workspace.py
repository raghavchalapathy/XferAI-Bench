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


@pytest.mark.parametrize(
    "bad",
    ["", "ab", "Exp1", "1exp", "../x", "a/b", "x-y", "a" * 65, "exp01 ", "é_x", "my_exp", "exp1_synthetic_b0",
     "exp01_synthetic", "exp01_Synthetic_b0", "exp01_synthetic_b0_", "exp01-synthetic-b0", "exp01_synthetic_" + "a" * 60],
)  # fmt: skip
def test_name_validation_rejects(bad: str) -> None:
    with pytest.raises(ExperimentError):
        validate_name(bad)


def test_new_scaffold_is_valid_and_standard(repo: Path) -> None:
    d = new_experiment("exp03_synthetic_mine", repo)
    assert sorted(p.name for p in d.iterdir()) == ["README.md", "config.yaml", "configs"]
    assert sorted(p.name for p in (d / "configs").iterdir()) == ["complete.yaml", "sample.yaml"]
    cfg = ExperimentConfig.load(d / "config.yaml")
    assert cfg.id == "exp03_synthetic_mine" and cfg.backend == "polars" and cfg.mode == "local"
    text = (d / "README.md").read_text(encoding="utf-8")
    for needle in ("Paper", "Data:", "Models:", "xferbench experiment run exp03_synthetic_mine", "not a ranking",
                   "eval/exp03_synthetic_mine__<tier>/", "Data tiers:"):  # fmt: skip
        assert needle in text


def test_new_from_copies_config_but_not_runs(repo: Path) -> None:
    src = repo / "experiments/exp01_synthetic_lightgbm_analogs"
    (src / "runs/20260101T000000Z").mkdir(parents=True)
    (src / "notes.md").write_text("extra", encoding="utf-8")
    d = new_experiment("exp04_synthetic_copy", repo, from_id="exp01_synthetic_lightgbm_analogs")
    a = yaml.safe_load((src / "config.yaml").read_text(encoding="utf-8"))
    b = yaml.safe_load((d / "config.yaml").read_text(encoding="utf-8"))
    assert b["id"] == "exp04_synthetic_copy" and {k: v for k, v in a.items() if k != "id"} == {
        k: v for k, v in b.items() if k != "id"
    }
    assert (d / "notes.md").read_text(encoding="utf-8") == "extra"
    assert not (d / "runs").exists()


def test_new_from_unknown_fails(repo: Path) -> None:
    with pytest.raises(ExperimentError, match="not found"):
        new_experiment("exp05_synthetic_x", repo, from_id="nope_missing")


def test_no_overwrite_without_force(repo: Path) -> None:
    d = new_experiment("exp06_synthetic_x", repo)
    (d / "config.yaml").write_text((d / "config.yaml").read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    with pytest.raises(ExperimentError, match="--force"):
        new_experiment("exp06_synthetic_x", repo)
    assert "# edited" in (d / "config.yaml").read_text(encoding="utf-8")
    new_experiment("exp06_synthetic_x", repo, force=True)
    assert "# edited" not in (d / "config.yaml").read_text(encoding="utf-8")


def test_cli_new_list_and_errors(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    r = CliRunner()
    assert (
        r.invoke(
            app, ["experiment", "new", "exp07_synthetic_cli", "--from", "exp02_synthetic_chronos_zero_shot"]
        ).exit_code
        == 0
    )
    assert r.invoke(app, ["experiment", "new", "exp07_synthetic_cli"]).exit_code == 2
    assert r.invoke(app, ["experiment", "new", "Bad-Name"]).exit_code == 2
    out = r.invoke(app, ["experiment", "list"]).output
    assert "exp01_synthetic_lightgbm_analogs" in out and "exp07_synthetic_cli" in out
    assert "NOT A DAY-ZERO RESULT" in out.split("exp07_synthetic_cli")[1]


def test_list_reports_invalid_config(repo: Path) -> None:
    bad = repo / "experiments/zz_broken"
    bad.mkdir()
    (bad / "config.yaml").write_text("id: zz_broken\nmethods: []\n", encoding="utf-8")
    info = {i.id: i for i in list_experiments(repo)}
    assert info["zz_broken"].error


def test_run_all_continues_past_failures(repo: Path) -> None:
    keep = {"exp02_synthetic_chronos_zero_shot"}
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
    assert status == {"aa_fails": "failed", "ab_invalid": "invalid_config", "exp02_synthetic_chronos_zero_shot": "ok"}
    assert [r["experiment"] for r in rows] == sorted(status)  # alphabetical, never by score
    ok = next(r for r in rows if r["status"] == "ok")
    out = Path(ok["out"])
    assert out.parent.name == "eval" and out.name == "exp02_synthetic_chronos_zero_shot__synthetic"
    assert (out / "leaderboard.html").exists() and ok["tier"] == "synthetic"
    assert not (out / "selection.json").exists() and (out / "_work/selection.json").exists()
    table = summary_table(rows)
    assert "not a ranking" in table and "rank" not in table.lower().replace("not a ranking", "")
    assert "Data tier: synthetic" in table and "| tier |" in table
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
    for p in (
        "eval/exp01_synthetic_lightgbm_analogs__synthetic/results.json",
        "eval/exp01_synthetic_lightgbm_analogs__sample-2/results.json",
        "experiments/exp01_synthetic_lightgbm_analogs/runs/20260101T000000Z/results.json",
    ):
        r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", p], check=False)
        assert r.returncode == 0, f"{p} must be git-ignored"


def test_every_experiment_readme_states_paper_data_models_run() -> None:
    for d in sorted((ROOT / "experiments").glob("*/config.yaml")):
        text = (d.parent / "README.md").read_text(encoding="utf-8")
        for needle in ("Paper", "Data", "Models", f"xferbench experiment run {d.parent.name}"):
            assert needle in text, (d.parent.name, needle)


@pytest.mark.parametrize("good", ["exp01_synthetic_lightgbm_analogs", "exp03_visuelle_gtm", "exp10_m5_b0"])
def test_name_validation_accepts(good: str) -> None:
    assert validate_name(good) == good


def test_every_shipped_experiment_follows_the_naming_rule() -> None:
    for i in list_experiments(ROOT, allow_research_only=True):
        assert i.name_problem is None, (i.id, i.name_problem)
        assert i.id == i.path.name


def test_list_flags_bad_names(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = repo / "experiments/my_old_exp"
    shutil.copytree(repo / "experiments/exp01_synthetic_lightgbm_analogs", bad)
    mism = repo / "experiments/exp09_m5_b0"
    shutil.copytree(repo / "experiments/exp01_synthetic_lightgbm_analogs", mism)
    info = {i.path.name: i for i in list_experiments(repo)}
    assert "exp<NN>_<dataset>_<method>" in (info["my_old_exp"].name_problem or "")
    assert "data.flavour" in (info["exp09_m5_b0"].name_problem or "")
    monkeypatch.chdir(repo)
    out = CliRunner().invoke(app, ["experiment", "list"]).output
    assert "NAME: name does not follow" in out and "NAME: dataset part 'm5'" in out


def test_deprecated_alias_resolves_with_warning() -> None:
    from xferbench.experiments.workspace import resolve_id

    with pytest.warns(FutureWarning, match="exp02_synthetic_chronos_zero_shot"):  # shown by default (V3-A)
        assert resolve_id("exp02_chronos_zero_shot") == "exp02_synthetic_chronos_zero_shot"


def test_cli_deprecated_alias_warns_on_stderr(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """V3-A: the CLI tells the user (stderr) that an old id is deprecated, then runs the new one."""
    monkeypatch.chdir(repo)
    r = CliRunner().invoke(app, ["experiment", "run", "exp01_m5_lightgbm_analogs"])
    assert r.exit_code == 0, r.output
    assert "deprecated" in r.stderr and "exp01_synthetic_lightgbm_analogs" in r.stderr
    assert "is deprecated" not in r.stdout
    assert (repo / "eval" / "exp01_synthetic_lightgbm_analogs__synthetic").is_dir()


def test_cli_run_all_refuses_mixed_tiers_before_running(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """V3-B: a selection that would mix tiers exits 2 before any experiment runs (no eval/ output at all)."""
    # synthetic experiments default to tier synthetic, the research-only reproduction to tier complete
    monkeypatch.chdir(repo)
    r = CliRunner().invoke(app, ["experiment", "run-all", "--allow-research-only"])
    assert r.exit_code == 2, r.output
    assert "refusing to mix data tiers" in r.stderr and "nothing was run" in r.stderr
    assert not (repo / "eval").exists() or not any((repo / "eval").iterdir())
    assert "running" not in r.stdout.lower()


def test_new_from_rewrites_empty_overlays_and_own_data_name(repo: Path) -> None:
    new_experiment("exp04_mydata_lightgbm", repo, from_id="exp01_synthetic_lightgbm_analogs")
    over = repo / "experiments" / "exp04_mydata_lightgbm" / "configs" / "sample.yaml"
    text = over.read_text(encoding="utf-8")
    assert "exp04_mydata_lightgbm --tier sample" in text and "exp01_" not in text
    assert "data/sample_data/metadata/metadata.json" in text
    info = next(i for i in list_experiments(repo) if i.id == "exp04_mydata_lightgbm")
    assert info.name_problem  # base flavour is synthetic and no own data yet
    over.write_text("data:\n  metadata: data/sample_data/metadata/metadata.json\n", encoding="utf-8")
    info = next(i for i in list_experiments(repo) if i.id == "exp04_mydata_lightgbm")
    assert not info.name_problem  # <dataset> now names the user's own data
