"""V3-1(3): the site builder (build_pages.py, kept outside this repo in the Lead's store at site/build_pages.py)
must never read bench run outputs: test-run/, validation-run/, _work/, run_manifest.json, metrics.json,
selection.json, leaderboard.csv or eval/<run>. Those files carry evaluator rank fields and are never published.

build_pages.py is not part of XferAI-Bench (it builds xferai.app from dist/assets/*.json). The real file is checked
when XFERAI_SITE_BUILD_PAGES points at it; otherwise that one test is skipped (listed in expected_skips.txt) and
the scanner itself is still tested on fixtures so the guard cannot rot.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

RUN_PATH_TOKENS = (
    "test-run",
    "validation-run",
    "_work",
    "run_manifest",
    "metrics.json",
    "selection.json",
    "leaderboard.csv",
    "methods_in_order",
)
_EVAL_DIR = re.compile(r"(^|[/\\'\"])eval[/\\]")
_LOCAL_BENCH = re.compile(r"/XferAI-Bench\b|XferAI-Bench/", re.IGNORECASE)  # a local checkout path
_URL = re.compile(r"https?://\S+")


def run_path_refs(source: str) -> list[str]:
    """Return every string literal (incl. f-string parts) in ``source`` that names a bench run path."""
    try:
        strings = [
            n.value for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
    except SyntaxError:  # e.g. PEP 701 f-strings (Python 3.12+) parsed on 3.11: fall back to every source line
        strings = source.splitlines()
    hits: list[str] = []
    for s in strings:
        low = s.lower()
        if any(t in low for t in RUN_PATH_TOKENS) or _EVAL_DIR.search(s) or (_LOCAL_BENCH.search(_URL.sub("", s))):
            hits.append(s[:120])
    return hits


@pytest.mark.parametrize(
    "src",
    [
        "p = Path('eval/exp01/test-run/metrics.json')",
        "x = open(root / 'validation-run' / 'leaderboard.csv')",
        "y = f'{d}/_work/selection.json'",
        "z = json.load(open('run_manifest.json'))",
        "w = Path('/workspace/XferAI-Bench') / 'results'",
    ],
)
def test_scanner_flags_run_paths(src: str) -> None:
    assert run_path_refs(src), src


def test_scanner_allows_site_assets() -> None:
    src = (
        "d = (DIST / 'assets' / 'benchmark.json').read_text()\n"
        "u = 'https://github.com/raghavchalapathy/XferAI-Bench/blob/main/docs/DIY-GettingStarted.md'\n"
    )
    assert run_path_refs(src) == []


def test_real_build_pages_reads_no_run_paths() -> None:
    p = os.environ.get("XFERAI_SITE_BUILD_PAGES")
    if not p or not Path(p).is_file():
        pytest.skip("XFERAI_SITE_BUILD_PAGES not set (build_pages.py lives outside this repo)")
    assert run_path_refs(Path(p).read_text(encoding="utf-8")) == []
