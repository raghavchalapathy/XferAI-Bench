"""Report ranking heading must say real benchmark rankings are pending (synthetic runs test the interface)."""

from __future__ import annotations

from pathlib import Path

from xferbench.reports.html import RANKING_HEADING, RANKING_NOTE


def test_heading_text() -> None:
    assert "real benchmark rankings pending" in RANKING_HEADING
    assert "only test the interface" in RANKING_NOTE
    assert "Top eligible methods" not in RANKING_HEADING


def test_reports_carry_pending_heading(tiny_runs: dict[str, Path]) -> None:
    for stage in ("validation", "test"):
        d = tiny_runs[stage]
        html = (d / "report.html").read_text()
        md = (d / "summary.md").read_text()
        assert RANKING_HEADING in html and RANKING_NOTE in html
        assert f"## {RANKING_HEADING}" in md and RANKING_NOTE in md
        assert "Top eligible methods" not in html
