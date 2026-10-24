"""V2-6: the strict-skip gate flags any skip not listed for the CI profile."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.conftest import unexpected_skips

ROOT = Path(__file__).resolve().parents[2]
SPEC = (ROOT / "tests/expected_skips.txt").read_text(encoding="utf-8")


def test_spark_profile_allows_no_skips() -> None:
    sk = ["tests/unit/test_scalable_eval.py::test_spark_local_parity"]
    assert unexpected_skips("spark", sk, SPEC) == sk


def test_core_profile_allows_listed_skips_only() -> None:
    ok = ["tests/leakage/test_m4_lightgbm.py::test_x", "tests/unit/test_scalable_eval.py::test_spark_local_parity"]
    assert unexpected_skips("core", ok, SPEC) == []
    assert unexpected_skips("core", ["tests/unit/test_cli.py::test_new"], SPEC) == ["tests/unit/test_cli.py::test_new"]


def test_session_fails_on_unexpected_skip(tmp_path: Path) -> None:
    t = ROOT / "tests/unit/_tmp_skip_probe_test.py"
    t.write_text("import pytest\n\ndef test_probe():\n    pytest.skip('probe')\n", encoding="utf-8")
    try:
        env = {**os.environ, "XFERBENCH_STRICT_SKIPS": "spark"}
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(t)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert r.returncode == 1 and "unexpected skips" in r.stdout, r.stdout
        env["XFERBENCH_STRICT_SKIPS"] = ""
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(t)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert r.returncode == 0, r.stdout
    finally:
        t.unlink()
