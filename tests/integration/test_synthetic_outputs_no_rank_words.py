"""V2-1: the Reviewer's probes as tests. On synthetic runs, `select` writes no recommended/recommended_reason
and `report` writes HTML free of rankable / ranked / ranking / recommended (outputs outside any git repo)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from xferbench.reports.html import SYNTHETIC_BANNED

_NEXT = Path(sys.executable).parent / ("xferbench.exe" if sys.platform == "win32" else "xferbench")
CLI = str(_NEXT) if _NEXT.exists() else (shutil.which("xferbench") or str(_NEXT))


def _cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    r = subprocess.run([CLI, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert r.returncode == 0, (args, r.stdout[-2000:], r.stderr[-2000:])
    return r


def test_select_json_has_no_recommendation_on_synthetic(tiny_runs: dict[str, Path], tmp_path: Path) -> None:
    out = tmp_path / "probe_sel.json"
    r = _cli("select", "--validation-run", str(tiny_runs["validation"]), "--out", str(out), cwd=tmp_path)
    sel = json.loads(out.read_text(encoding="utf-8"))
    assert "recommended" not in sel and "recommended_reason" not in sel
    assert "recommended" not in out.read_text(encoding="utf-8").lower()
    assert "recommended" not in (r.stdout + r.stderr).lower()
    assert sel["families"]


def test_report_html_has_no_rank_words_on_synthetic(tiny_runs: dict[str, Path], tmp_path: Path) -> None:
    run = tmp_path / "run"
    shutil.copytree(tiny_runs["test"], run)
    out = tmp_path / "probe_rep.html"
    _cli("report", "--run", str(run), "--out", str(out), cwd=tmp_path)
    for text in (out.read_text(encoding="utf-8").lower(), (run / "summary.md").read_text(encoding="utf-8").lower()):
        hits = [w for w in SYNTHETIC_BANNED if w in text]
        assert hits == [], hits
