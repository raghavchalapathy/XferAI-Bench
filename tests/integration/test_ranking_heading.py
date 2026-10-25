"""Report ranking heading must say real benchmark rankings are pending (synthetic runs test the interface)."""

from __future__ import annotations

from pathlib import Path

from xferbench.reports.html import RANKING_HEADING, RANKING_NOTE, SYNTHETIC_BANNED, SYNTHETIC_HEADING, SYNTHETIC_NOTE


def test_heading_text() -> None:
    assert "real benchmark rankings pending" in RANKING_HEADING
    assert "only test the interface" in RANKING_NOTE
    assert "Top eligible methods" not in RANKING_HEADING


def test_reports_carry_pending_heading(tiny_runs: dict[str, Path]) -> None:
    for stage in ("validation", "test"):
        d = tiny_runs[stage]
        html = (d / "report.html").read_text(encoding="utf-8")
        md = (d / "summary.md").read_text(encoding="utf-8")
        # tiny_runs are synthetic: V2-1 swaps in the not-a-ranking heading
        assert SYNTHETIC_HEADING in html and SYNTHETIC_NOTE in html
        assert f"## {SYNTHETIC_HEADING}" in md and SYNTHETIC_NOTE in md
        for word in SYNTHETIC_BANNED:  # V2-1 Reviewer probe
            assert word not in html.lower() and word not in md.lower(), (stage, word)
        assert "Ranked by" not in html and ">Rank<" not in html
        assert "Top eligible methods" not in html
