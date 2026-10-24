"""Runs the Reviewer's adversarial parity script (adv.py, verbatim) and checks every case matches the protected
evaluator: no MISMATCH, error cases raise in both, and the final NaN-actual call raises ValueError (F-2)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ADV = Path(__file__).with_name("adv.py")


def _run(env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **env_extra}
    return subprocess.run(
        [sys.executable, str(ADV)], capture_output=True, text=True, encoding="utf-8", env=env, timeout=900
    )


def _check(res: subprocess.CompletedProcess[str], engines: list[str]) -> None:
    out = res.stdout
    assert "MISMATCH" not in out, out
    lines = {ln.split(" ", 1)[0]: ln for ln in out.splitlines() if " {" in ln}
    for case in ("normal", "duplicate_forecast_row", "random_1e5", "failed_status", "two_methods_same_variant_id"):
        for eng in engines:
            assert f"'{eng}': ('OK'" in lines[case], lines[case]
    assert "'polars': ('OK'" in lines["dup_masks_missing"], lines["dup_masks_missing"]  # F-1
    for eng in engines:
        assert f"'{eng}': 'ERR ValueError" in lines["nan_actual"], lines["nan_actual"]  # F-2
    # the script's last line calls finalize() on a NaN actual without try/except: it must raise like the reference
    assert res.returncode != 0 and "ValueError: metrics require finite" in res.stderr, res.stderr[-2000:]


def test_reviewer_adversarial_polars() -> None:
    _check(_run({"SPARK": ""}), ["polars"])


def test_reviewer_adversarial_spark() -> None:
    pytest.importorskip("pyspark")
    if shutil.which("java") is None and not os.environ.get("JAVA_HOME"):
        pytest.skip("Java not available")
    _check(_run({"SPARK": "1", "SPARK_LOCAL_IP": "127.0.0.1"}), ["polars", "spark"])
