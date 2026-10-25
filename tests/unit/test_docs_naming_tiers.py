"""Owner request 2026-10-24: docs and Getting Started describe the exp<NN>_<dataset>_<method> naming and data tiers,
and no doc points at the old experiment ids or the old experiments/<id>/runs/<timestamp>/ output path."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = ("exp01_m5_lightgbm_analogs", "exp02_chronos_zero_shot", "repro_visuelle_gtm")
DOCS = [
    "README.md", "AGENTS.md", "DATASCIENTIST.md", "llms.txt", "THIRD_PARTY_NOTICES.md", "docs/GETTING_STARTED.md",
    "docs/DIY-GettingStarted.md", "experiments/README.md", "scripts/model_eval.sh", ".github/workflows/ci.yml",
    "harness/proposals/TEMPLATE.yaml.example",
]  # fmt: skip


def _text(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


def test_no_old_ids_or_run_paths() -> None:
    files = DOCS + [
        p.relative_to(ROOT).as_posix()  # "/" on every OS; str() gives "\\" on Windows and broke the exemption
        for p in (ROOT / "experiments").rglob("*")
        if p.is_file() and "runs" not in p.relative_to(ROOT).parts  # local (git-ignored) run outputs
    ]
    for f in files:
        t = _text(f)
        if f != "experiments/README.md":  # its Naming section records the renames on purpose
            assert not [o for o in OLD if o in t], f
        assert "/runs/<" not in t, f


def test_doc_list_uses_posix_paths_on_every_os() -> None:
    """Windows CI run 40162698138: str(relative_to) gave experiments\\README.md, so the exemption never matched."""
    from pathlib import PureWindowsPath

    assert PureWindowsPath("experiments", "README.md").as_posix() == "experiments/README.md"
    assert "experiments/README.md" in [
        p.relative_to(ROOT).as_posix() for p in (ROOT / "experiments").rglob("README.md")
    ]


def test_getting_started_documents_tiers_and_naming() -> None:
    gs = _text("docs/GETTING_STARTED.md")
    assert "## Data tiers (synthetic, sample, complete)" in gs
    for needle in (
        "--tier sample",
        "configs/sample.yaml",
        "eval/<id>__<tier>/",
        "exit 2",
        "LOCAL DATA",
        "exp<NN>_<dataset>_<method>",
    ):
        assert needle in gs, needle
    for f in ("README.md", "experiments/README.md", "AGENTS.md", "llms.txt"):
        assert "#data-tiers-synthetic-sample-complete" in _text(f) or "tier" in _text(f), f
    assert re.search(r"exp<NN>_<dataset>_<method>", _text("experiments/README.md"))


def test_anchor_matches_heading() -> None:
    gs = _text("docs/GETTING_STARTED.md")
    heading = next(line[3:] for line in gs.splitlines() if line.startswith("## Data tiers"))
    anchor = re.sub(r"[^a-z0-9 -]", "", heading.lower()).replace(" ", "-")
    assert anchor == "data-tiers-synthetic-sample-complete"
