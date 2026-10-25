"""VISUELLE/GTM reproduction: excluded by default, licence-gated download, adapter on a SYNTHETIC fixture."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from tests._bash import BASH_EXE
from xferbench.cli.main import app
from xferbench.experiments.workspace import ResearchOnlyError, list_experiments, run_all, run_one
from xferbench.repro.visuelle import PAPER, GtmWrapper, ReproError, adapt_visuelle, report_markdown, wape

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "exp03_visuelle_gtm"
SCRIPT = EXP / "scripts" / "download_visuelle.sh"
FIXTURE = ROOT / "tests" / "fixtures" / "visuelle_synthetic"


def _tracked_and_untracked() -> str:
    return subprocess.run(
        ["git", "status", "--porcelain", "--ignored", "--", "."], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", check=False,
    ).stdout  # fmt: skip


def test_repro_excluded_by_default() -> None:
    ids = [i.id for i in list_experiments(ROOT)]
    assert "exp03_visuelle_gtm" not in ids
    assert "exp03_visuelle_gtm" in [i.id for i in list_experiments(ROOT, allow_research_only=True)]


def test_run_all_skips_repro_by_default(tmp_path: Path) -> None:
    (tmp_path / "experiments").mkdir()
    shutil.copytree(EXP, tmp_path / "experiments" / "exp03_visuelle_gtm")
    assert run_all(tmp_path, progress=lambda m: None) == []
    rows = run_all(tmp_path, progress=lambda m: None, allow_research_only=True)
    assert [r["status"] for r in rows] == ["blocked"]
    assert "RESEARCH ONLY" in rows[0]["detail"]
    with pytest.raises(ResearchOnlyError):
        run_one("exp03_visuelle_gtm", tmp_path, progress=lambda m: None)


def test_blocked_report_lists_reasons_and_paper_number(tmp_path: Path) -> None:
    (tmp_path / "experiments").mkdir()
    shutil.copytree(EXP, tmp_path / "experiments" / "exp03_visuelle_gtm", ignore=shutil.ignore_patterns("runs"))
    with pytest.raises(ReproError):
        run_one("exp03_visuelle_gtm", tmp_path, progress=lambda m: None, allow_research_only=True)
    # reproductions default to data tier "complete" -> eval/<id>__complete/
    report = (tmp_path / "eval" / "exp03_visuelle_gtm__complete" / "report.md").read_text(encoding="utf-8")
    assert "Paper-reported** | 55.2" in report and "PENDING" in report
    assert "licence status is 'not_found'" in report and "GTM-Transformer local install not found" in report


def test_cli_list_hides_and_run_requires_flag() -> None:
    r = CliRunner()
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        assert "exp03_visuelle_gtm" not in r.invoke(app, ["experiment", "list"]).output
        assert "RESEARCH ONLY" in r.invoke(app, ["experiment", "list", "--allow-research-only"]).output
        assert r.invoke(app, ["experiment", "run", "exp03_visuelle_gtm"]).exit_code == 2
    finally:
        os.chdir(cwd)


@pytest.mark.skipif(BASH_EXE is None, reason="needs a real bash (not the WSL launcher stub)")
def test_download_refuses_without_acceptance_and_writes_nothing() -> None:
    before = _tracked_and_untracked()
    p = subprocess.run(
        [BASH_EXE, SCRIPT.as_posix(), "--archive", "/nonexistent.zip"], cwd=ROOT, input="I ACCEPT THE VISUELLE TERMS\n",
        capture_output=True, text=True, encoding="utf-8", check=False,
    )  # fmt: skip
    assert p.returncode == 3 and "interactive" in p.stderr
    assert _tracked_and_untracked() == before
    assert not (ROOT / "data" / "visuelle" / "input" / "raw").exists()


@pytest.mark.skipif(BASH_EXE is None, reason="needs a real bash (not the WSL launcher stub)")
@pytest.mark.parametrize("dest", ["src/xferbench", "data/visuelle/metadata", "data/../src", "experiments"])
def test_download_refuses_tracked_destinations(dest: str) -> None:
    p = subprocess.run(
        [BASH_EXE, SCRIPT.as_posix(), "--dest", dest], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        check=False, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    assert p.returncode == 4


def test_download_script_uses_official_source_only() -> None:
    s = SCRIPT.read_text(encoding="utf-8")
    assert "https://forms.gle/cVGQAmxhHf7eRJ937" in s
    assert "curl " not in s and "wget " not in s and "git clone" not in s


def test_adapter_on_synthetic_fixture(tmp_path: Path) -> None:
    meta = adapt_visuelle(FIXTURE, tmp_path / "data", "visuelle_synth", synthetic=True)
    assert meta["synthetic"] is True and "SYNTHETIC" in meta["source"]
    assert meta["products"] == {"train": 6, "test": 3}
    sales = pl.read_parquet(tmp_path / "data/visuelle_synth/input/sales.parquet")
    assert sales.height == 9 * 12 and sales["week"].max() == 11
    assert (tmp_path / "data/visuelle_synth/metadata/metadata.json").is_file()
    fc = sales.rename({"sales": "forecast"})
    assert wape(sales, fc) == 0.0
    assert wape(sales, fc.with_columns(pl.lit(0.0).alias("forecast"))) == pytest.approx(100.0)


def test_adapter_rejects_wrong_shape(tmp_path: Path) -> None:
    (tmp_path / "train.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "test.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ReproError, match="missing VISUELLE columns"):
        adapt_visuelle(tmp_path, tmp_path / "out")


def test_gtm_wrapper_needs_local_install(tmp_path: Path) -> None:
    with pytest.raises(ReproError):
        GtmWrapper(tmp_path / "nope").check()
    for f in ("forecast.py", "train.py", "LICENSE"):
        (tmp_path / f).write_text("", encoding="utf-8")
    w = GtmWrapper(tmp_path, "python")
    w.check()
    cmd = w.forecast_command(Path("d"), Path("c.pth"))
    assert cmd[:4] == ["python", "forecast.py", "--data_folder", "d/"] and "52" in cmd


def test_report_labels_numbers_separately() -> None:
    r = report_markdown(None, {"id": "x"}, ["data blocked"])
    assert "**Paper-reported** | 55.2" in r and "**Reproduced by us** | PENDING" in r and "- data blocked" in r
    assert PAPER["wape_reported"] == 55.2


def test_no_vendored_gtm_code() -> None:
    hits = [p for p in ROOT.rglob("*.py") if "GTM" in p.name or p.name == "data_multitrends.py"]
    assert not [p for p in hits if ".venv" not in p.parts]


def test_reviewer_record_points_at_citation_check() -> None:
    rec = PAPER["reviewer_record"]
    assert rec.startswith("citation-checked: factory/inbox/reviewer/usability-v4-v2-review-20261024/review.md")
    assert "fd0d8ceacf2bcf7ca500376cf51169214084c0c79cb0fa42f23aa9867df95911" in rec
    assert "reproduction pending" in rec and PAPER["reproduction"] == "pending"
