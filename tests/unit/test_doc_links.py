"""Relative links in the top-level docs, docs/ and llms.txt point at files that exist."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def _docs() -> list[Path]:
    top = [ROOT / n for n in ("README.md", "AGENTS.md", "CONTRIBUTING.md", "llms.txt")]
    return [p for p in top if p.exists()] + sorted((ROOT / "docs").glob("*.md"))


def test_relative_doc_links_resolve() -> None:
    broken = []
    for doc in _docs():
        for target in LINK.findall(doc.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("mailto:"):
                continue
            if not (doc.parent / target).exists():
                broken.append(f"{doc.relative_to(ROOT)} -> {target}")
    assert broken == []


def test_agent_entry_points_link_the_diy_guide() -> None:
    for name in ("README.md", "AGENTS.md", "llms.txt"):
        assert "docs/DIY-GettingStarted.md" in (ROOT / name).read_text(encoding="utf-8"), name
