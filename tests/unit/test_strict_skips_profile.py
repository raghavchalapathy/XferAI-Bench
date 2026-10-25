"""Ruling (a): XFERBENCH_STRICT_SKIPS rejects unknown profiles with a clear error."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _pytest(profile: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "XFERBENCH_STRICT_SKIPS": profile}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/unit/test_doc_links.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_unknown_profile_rejected() -> None:
    r = _pytest("1")
    assert r.returncode == 4, r.stdout[-1000:]
    assert "XFERBENCH_STRICT_SKIPS='1' is not a known profile; use one of core, spark" in r.stdout


def test_core_profile_accepted() -> None:
    assert _pytest("core").returncode == 0
