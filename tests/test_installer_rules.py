"""Conformance check for proposal installer-ux-20261025 (v2). Offline, read-only.

XB_REPO     checkout with the installer (usability-v4-setup / usability-v4.1), default "."
XB_HARNESS  harness/ dir holding the CURRENT BEST_PRACTICES (v2 from harness-polars-asof-parity), default $XB_REPO/harness
Every clause in the proposal's rules maps to a check here (see README.md, "Rule -> check").
"""

from __future__ import annotations

import os
import pathlib
import re

import pytest
import yaml

REPO = pathlib.Path(
    os.environ.get("XB_REPO", pathlib.Path(__file__).resolve().parent.parent)
).resolve()  # adopted: repo root
HARNESS = pathlib.Path(os.environ.get("XB_HARNESS", REPO / "harness")).resolve()
HERE = pathlib.Path(
    os.environ.get("XB_PROPOSAL_DIR", REPO / "harness" / "proposals")
).resolve()  # adopted: proposal lives here
PROPOSAL = HERE / "installer-ux-20261025.yaml"
SH = (REPO / "xferAI_setup.sh").read_text(encoding="utf-8")
PS = (REPO / "xferAI_setup.ps1").read_text(encoding="utf-8")
TESTS = (REPO / "tests/unit/test_setup_script.py").read_text(encoding="utf-8")
CI = yaml.safe_load((REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8"))


def code(s: str) -> str:
    return "\n".join(ln for ln in s.splitlines() if not ln.lstrip().startswith("#"))


def steps():
    for name, job in CI["jobs"].items():
        for st in job.get("steps", []):
            yield name, job, st


# Adopted 2026-10-25 (BEST_PRACTICES v3, Reviewer H-A1): the pre-apply checks "schema/no clash with v2"
# and "v3 diff matches apply" were dropped here; they ran green before apply (see review evidence).


# ---- installer_safety
def test_no_sudo():
    assert not re.search(r"\bsudo\b", code(SH)) and not re.search(r"\bsudo\b", code(PS))


def test_strict_mode_and_dry_run():
    assert "set -Eeuo pipefail" in SH and re.search(r"trap .*ERR", SH) and "--dry-run" in SH
    assert re.search(r"ErrorActionPreference\s*=\s*[\"']Stop", PS) and "DryRun" in PS


def test_uv_installer_pinned_and_observed_hash():  # I-1
    v = re.search(r'^UV_VERSION="([0-9.]+)"', SH, re.M)
    h = re.search(r'^UV_INSTALLER_SHA256_OBSERVED="([0-9a-f]{64})"', SH, re.M)
    pv = re.search(r'^\$UvVersion = "([0-9.]+)"', PS, re.M)
    ph = re.search(r'^\$UvInstallerSha256Observed = "([0-9a-f]{64})"', PS, re.M)
    assert v and h and pv and ph and v.group(1) == pv.group(1) == "0.13.5"
    assert h.group(1) == "1c6e7f025499664633ac2dce43a210800510e9ef0625c52e034a8afdf8bf177a"
    assert ph.group(1) == "84b66aa3018e9d800886543380d967bb3fb9652cfb251cfa5f3c73f4e62f59f2"
    assert "observed" in SH and "observed" in PS and "UV_NO_MODIFY_PATH" in SH and "UV_NO_MODIFY_PATH" in PS


# ---- installer_ux / installer_env
@pytest.mark.parametrize(
    "pat",
    [
        r"--help",
        r"--version",
        r"--quiet",
        r"--verbose",
        r"--non-interactive",
        r"NO_COLOR",
        r"Fix:",
        r"exit 2",
        r"\[ok\]",
        r"-t 0|-t 1",
        r"elapsed",
    ],
)
def test_sh_ux(pat):
    assert re.search(pat, SH), pat


@pytest.mark.parametrize("pat", [r"NO_COLOR", r"Fix:", r"exit 2", r"NonInteractive", r"Stopwatch|Elapsed"])
def test_ps1_ux(pat):
    assert re.search(pat, PS, re.I), pat


def test_proxy_and_index_not_hardcoded():
    for s in (code(SH), code(PS)):
        assert "--index-url" not in s and "--proxy" not in s
    assert "--no-install-uv" in SH


# ---- installer_checks: test-suite enforcement
def test_every_help_flag_is_exercised_by_setup_tests():
    help_block = SH[SH.index("Options:") : SH.index("USAGE\n}")]
    flags = sorted(set(re.findall(r"^\s+(?:-h, )?(--[a-z-]+)", help_block, re.M)))
    assert len(flags) >= 10
    missing = [f for f in flags if f not in TESTS]
    assert not missing, missing


def test_setup_tests_have_pty_prompt_and_stubbed_fallbacks():
    assert re.search(r"def test_\w*prompt\w*tty", TESTS) and "pty.fork()" in TESTS
    for t in (
        "test_uv_missing_installs_pinned_verified_installer",
        "test_uv_installer_checksum_mismatch_is_not_run",
        "test_pip_fallback_when_no_uv_and_no_install",
        "test_lightgbm_install_failure_warns_and_continues",
    ):
        assert f"def {t}(" in TESTS, t


# ---- installer_checks: ci.yml enforcement
def test_ci_shellcheck_info_on_both_scripts():
    runs = [st.get("run", "") for _, _, st in steps() if "shellcheck" in st.get("run", "")]
    assert any("--severity=info" in r and "xferAI_setup.sh" in r and "bootstrap.sh" in r for r in runs), runs


def test_ci_psscriptanalyzer_per_file_and_fails_on_findings():
    runs = [st.get("run", "") for _, _, st in steps() if "Invoke-ScriptAnalyzer" in st.get("run", "")]
    assert runs
    r = runs[0]
    assert re.search(r"ForEach-Object\s*\{\s*Invoke-ScriptAnalyzer -Path \$_", r) or "foreach" in r.lower()
    assert "xferAI_setup.ps1" in r and "bootstrap.ps1" in r and re.search(r"if \(\$r\) \{ exit 1 \}", r)


def test_ci_fresh_and_rerun_on_three_oses():
    def ok(job: dict) -> bool:
        oses = set(job.get("strategy", {}).get("matrix", {}).get("os", []))
        runs = [st.get("run", "") for st in job.get("steps", [])]
        return {"ubuntu-latest", "macos-latest", "windows-latest"} <= oses and all(
            sum(s in r for r in runs) >= 2 for s in ("bash xferAI_setup.sh", "xferAI_setup.ps1")
        )  # fresh run + rerun of each script in one 3-OS matrix job

    assert any(ok(job) for job in CI["jobs"].values())


def test_ci_runs_the_setup_tests():
    assert any("pytest" in st.get("run", "") for _, _, st in steps())


def test_ci_pins_actions_to_sha():
    uses = [st["uses"] for _, _, st in steps() if "uses" in st]
    bad = [u for u in uses if not re.search(r"@[0-9a-f]{40}$", u)]
    assert uses and not bad, bad
