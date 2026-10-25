"""Ruling (c): the proposed polars_swap_parity check flags swaps without *_reference or a parity test."""

from __future__ import annotations

from pathlib import Path

from xferbench.harness.swaps import find_swap_violations

ROOT = Path(__file__).resolve().parents[2]
SWAP = '''
class D:
    def f(self, x):
        """Polars join; replaces a pandas loop."""
        return x
'''
REF = '''
    def f_reference(self, x):
        """Original pandas loop."""
        return x
'''


def _repo(tmp: Path, src: str, test: str) -> Path:
    (tmp / "src").mkdir()
    (tmp / "tests").mkdir()
    (tmp / "src/m.py").write_text(src, encoding="utf-8")
    (tmp / "tests/test_m.py").write_text(test, encoding="utf-8")
    return tmp


def test_positive_repo_swaps_compliant() -> None:
    assert find_swap_violations(ROOT) == []


def test_negative_swap_without_reference_flagged(tmp_path: Path) -> None:
    bad = find_swap_violations(_repo(tmp_path, SWAP, "def test_x():\n    pass\n"))
    assert len(bad) == 1 and "has no f_reference" in bad[0]


def test_negative_swap_without_parity_test_flagged(tmp_path: Path) -> None:
    bad = find_swap_violations(_repo(tmp_path, SWAP + REF, "def test_x():\n    pass\n"))
    assert len(bad) == 1 and "no parity test calling f_reference" in bad[0]


def test_compliant_swap_passes(tmp_path: Path) -> None:
    assert find_swap_violations(_repo(tmp_path, SWAP + REF, "def test_p(d):\n    d.f_reference(1)\n")) == []
