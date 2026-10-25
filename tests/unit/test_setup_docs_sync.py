"""The setup scripts' messages, GETTING_STARTED and the real CLI stay in sync (runs on every OS, no network)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NEXT = (ROOT / "setup" / "next_demo.txt").read_text(encoding="utf-8")
OWN = (ROOT / "setup" / "own_data.txt").read_text(encoding="utf-8")
GS = (ROOT / "docs" / "GETTING_STARTED.md").read_text(encoding="utf-8")
SH = (ROOT / "xferAI_setup.sh").read_text(encoding="utf-8")
PS1 = (ROOT / "xferAI_setup.ps1").read_text(encoding="utf-8")


def _block(name: str) -> str:
    m = re.search(rf"<!-- BEGIN {name} -->\n```text\n(.*?)```\n<!-- END {name} -->", GS, re.S)
    assert m, name
    return m.group(1)


def test_getting_started_has_the_blocks_verbatim() -> None:
    assert _block("setup/next_demo.txt") == NEXT
    assert _block("setup/own_data.txt") == OWN


def test_getting_started_order_and_no_install_md() -> None:
    heads = [ln for ln in GS.splitlines() if ln.startswith("## ")]
    idx = {k: next(i for i, h in enumerate(heads) if h.startswith(k)) for k in ("## Step 0", "## Step 1", "## Step 2")}
    assert idx["## Step 0"] < idx["## Step 1"] < idx["## Step 2"]
    step0 = GS[GS.index("## Step 0") : GS.index("## Step 1")]
    assert "bash xferAI_setup.sh" in step0 and "pip" in step0 and "xferAI_setup.ps1" in step0
    assert not (ROOT / "INSTALL.md").exists() and not (ROOT / "docs" / "INSTALL.md").exists()


def test_both_scripts_print_the_shared_message_files_and_flags() -> None:
    for f in ("setup/next_demo.txt", "setup/own_data.txt"):
        assert f in SH and f.replace("/", "\\") in PS1
    pairs = {"--python": "$Python", "--no-install-uv": "$NoInstallUv", "--with-lightgbm": "$WithLightgbm",
             "--with-spark": "$WithSpark", "--no-demo": "$NoDemo", "--yes-own-data": "$YesOwnData",
             "--non-interactive": "$NonInteractive", "--dry-run": "$DryRun", "--quiet": "$Quiet",
             "--version": "$Version", "--help": "$Help"}  # fmt: skip
    for sh_flag, ps_param in pairs.items():
        assert sh_flag in SH and ps_param in PS1, sh_flag
    assert re.search(r'UV_VERSION="(\d+\.\d+\.\d+)"', SH).group(1) == re.search(r'\$UvVersion = "(\d+\.\d+\.\d+)"', PS1).group(1)  # type: ignore[union-attr]  # noqa: E501
    assert "Do you want to run on your own data? [y/N]" in SH and "Do you want to run on your own data? [y/N]" in PS1


def test_message_files_reference_real_files_and_commands() -> None:
    for rel in ("docs/GETTING_STARTED.md", "docs/REAL_DATA.md", "schemas/FIELD_DICTIONARY.md", "experiments/README.md"):
        assert rel in NEXT + OWN and (ROOT / rel).is_file(), rel
    assert (ROOT / "experiments" / "exp01_synthetic_lightgbm_analogs" / "configs" / "sample.yaml").is_file()
    for d in ("data/sample_data/input", "data/complete_data/input"):
        r = subprocess.run(["git", "check-ignore", "-q", f"{d}/x.csv"], cwd=ROOT, check=False) if shutil.which("git") else None
        assert r is None or r.returncode == 0, d


def test_bootstrap_scripts_are_thin_wrappers() -> None:
    sh = (ROOT / "bootstrap.sh").read_text(encoding="utf-8")
    ps = (ROOT / "bootstrap.ps1").read_text(encoding="utf-8")
    assert 'exec bash "$here/xferAI_setup.sh" "$@"' in sh and len(sh.splitlines()) < 12
    assert "xferAI_setup.ps1" in ps and "@args" in ps and len(ps.splitlines()) < 15


def _xb() -> list[str]:
    exe = Path(sys.executable).with_name("xferbench.exe" if os.name == "nt" else "xferbench")
    return [str(exe)] if exe.exists() else [sys.executable, "-m", "xferbench.cli.main"]


@pytest.mark.slow
def test_printed_demo_command_runs_offline_and_makes_the_named_files(tmp_path: Path) -> None:
    """Runs the exact `experiment run <id>` from setup/next_demo.txt in a copy of the repo; no network is used."""
    m = re.search(r"uv run xferbench (experiment run (\S+))", NEXT)
    assert m
    exp_id = m.group(2)
    for d in ("experiments", "configs", "data", "schemas"):
        if (ROOT / d).exists():
            shutil.copytree(ROOT / d, tmp_path / d, ignore=shutil.ignore_patterns("runs", "input", "metadata"))
    shutil.copy2(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    env = dict(os.environ, NO_PROXY="*", HTTPS_PROXY="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9")
    r = subprocess.run([*_xb(), *m.group(1).split()], cwd=tmp_path, env=env, capture_output=True, text=True,
                       encoding="utf-8", timeout=900, check=False)  # fmt: skip
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    out_rel = re.search(r"Output: (eval/\S+?)/", NEXT).group(1)  # type: ignore[union-attr]
    assert out_rel == f"eval/{exp_id}__synthetic"
    for name in re.search(r"Open: (.*?) in that output folder", NEXT).group(1).replace(" and ", ", ").split(", "):  # type: ignore[union-attr]  # noqa: E501
        assert (tmp_path / out_rel / name).is_file(), name
