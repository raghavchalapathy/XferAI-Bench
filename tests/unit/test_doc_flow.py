"""Doc-flow guards for the Guide review findings U4-01, U4-02 and U4-03."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests._bash import BASH_EXE, find_bash, is_wsl_stub

ROOT = Path(__file__).resolve().parents[2]
DIY = ROOT / "docs" / "DIY-GettingStarted.md"
BASH = re.compile(r"```bash\n(.*?)```", re.S)


def _section(text: str, start: str, end: str) -> str:
    return text[text.index(start) : text.index(end)]


def test_u4_01_framing_rules_and_setup_precede_part_1() -> None:
    t = DIY.read_text(encoding="utf-8")
    p1 = t.index("## Part 1.")
    for needle in ("written for an LLM coding assistant", "## Rules", "## Prerequisites", "### Step 3. Install"):
        assert t.index(needle) < p1, needle
    part2 = t[t.index("## Part 2.") :]
    assert not re.search(r"^## (?!Part)", part2, re.M), "Part 2 subsections must be ### or deeper"


def test_u4_02_steps_9_to_11_use_one_run_counter() -> None:
    t = DIY.read_text(encoding="utf-8")
    cmds = "".join(BASH.findall(_section(t, "#### Step 9.", "#### Reading results")))
    assert "RUN=1" in cmds
    assert not re.search(r"(val|test|selection)-1\b|selection\.json", cmds), "hard-coded run names"
    assert "test -d" not in cmds, "silent skip guard"
    for name in ("val-$RUN", "selection-$RUN.json", "test-$RUN", "test-$RUN-report.html"):
        assert name in cmds, name


@pytest.mark.skipif(BASH_EXE is None, reason="needs a real bash (not the WSL launcher stub)")
def test_u4_02_rerun_with_same_run_fails_loudly(tmp_path: Path) -> None:
    t = DIY.read_text(encoding="utf-8")
    script = "".join(BASH.findall(_section(t, "#### Step 9.", "#### Step 11.")))
    stub = (
        'xb() { out=""; while [ $# -gt 0 ]; do [ "$1" = --out ] && out=$2; shift; done; '
        'case $out in *.json) mkdir -p "$(dirname "$out")"; echo {} > "$out";; *) mkdir -p "$out";; esac; }\n'
    )
    assert BASH_EXE is not None
    script = stub + "set -e\n" + script.replace(".venv/bin/xferbench", "xb")
    first = subprocess.run(
        [BASH_EXE, "-c", script], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", check=False
    )
    assert first.returncode == 0, first.stderr
    assert (tmp_path / "runs/local/test-1").is_dir()
    second = subprocess.run(
        [BASH_EXE, "-c", script], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", check=False
    )
    assert second.returncode != 0 and "already exists" in second.stdout


@pytest.mark.skipif(shutil.which("git") is None or not (ROOT / ".git").exists(), reason="needs a git checkout")
def test_u4_03_readme_outputs_inside_repo_are_gitignored() -> None:
    outs = re.findall(r"--out\s+\.\/(\S+)", "".join(BASH.findall((ROOT / "README.md").read_text(encoding="utf-8"))))
    assert outs
    for o in outs:
        r = subprocess.run(["git", "check-ignore", "-q", o.rstrip("/") + "/x"], cwd=ROOT, check=False)
        assert r.returncode == 0, f"README writes untracked ./{o}"


@pytest.mark.parametrize(
    ("path", "stub"),
    [
        (r"C:\Windows\System32\bash.exe", True),
        (r"C:\Users\a\AppData\Local\Microsoft\WindowsApps\bash.exe", True),
        (r"C:\Program Files\Git\bin\bash.exe", False),
        ("/usr/bin/bash", False),
    ],
)
def test_wsl_launcher_stub_is_not_used_as_bash(path: str, stub: bool) -> None:
    assert is_wsl_stub(path) is stub


def test_find_bash_skips_stub_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _n: r"C:\Windows\System32\bash.exe")
    monkeypatch.setattr(os, "name", "posix")  # no Git fallback: the stub alone must give None (skip), not a run
    assert find_bash() is None


def test_doc_parsing_survives_crlf_checkout(tmp_path: Path) -> None:
    """core.autocrlf=true checkouts give CRLF; read_text() normalises newlines so the ```bash blocks still parse."""
    f = tmp_path / "doc.md"
    f.write_bytes(DIY.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    t = f.read_text(encoding="utf-8")
    assert "\r" not in t
    assert BASH.findall(_section(t, "#### Step 9.", "#### Step 11.")) == BASH.findall(
        _section(DIY.read_text(encoding="utf-8"), "#### Step 9.", "#### Step 11.")
    )
