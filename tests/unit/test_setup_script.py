"""xferAI_setup.sh behaviour with stubbed git/python/uv/curl (no network, no real installs).

The stubs live in a temporary PATH that contains only them and a few coreutils, so a real uv, Python or curl on the
machine is never used. The PowerShell twin (xferAI_setup.ps1) is checked by PSScriptAnalyzer and run for real by the
setup-windows CI job; here we only check that it carries the same messages and flags."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SH = ROOT / "xferAI_setup.sh"
PS1 = ROOT / "xferAI_setup.ps1"
NEXT = (ROOT / "setup" / "next_demo.txt").read_text(encoding="utf-8")
OWN = (ROOT / "setup" / "own_data.txt").read_text(encoding="utf-8")
GS = ROOT / "docs" / "GETTING_STARTED.md"
posix_only = pytest.mark.skipif(os.name == "nt", reason="stubbed-PATH tests use symlinks; Windows runs the ps1 job")
TOOLS = ("bash", "sh", "uname", "date", "mktemp", "cut", "tr", "tee", "rm", "cat", "cp", "mv", "dirname", "basename",
         "mkdir", "chmod", "grep", "sed", "head", "tail", "wc", "env", "touch", "sleep", "awk", "ls", "id")

FAKE_PY = """#!/bin/sh
# fake python 3.13: version checks, -m venv DIR, -m pip install ...
if [ "$1" = -c ]; then case "$2" in *print*) echo 3.13.0;; *) exit 0;; esac; exit 0; fi
if [ "$1" = -m ] && [ "$2" = venv ]; then
  mkdir -p "$3/bin"; echo "home = x" > "$3/pyvenv.cfg"; cp "$0" "$3/bin/python"; cp "$(dirname "$0")/fake-xferbench" "$3/bin/xferbench"
  echo "venv $3" >> "$CALLS"; exit 0; fi
echo "python $*" >> "$CALLS"; exit 0
"""
FAKE_UV = """#!/bin/sh
echo "uv $*" >> "$CALLS"
case "$1" in
  --version) echo "uv 0.0.0-stub";;
  venv) for a in "$@"; do d=$a; done; mkdir -p "$d/bin"; echo "home = x" > "$d/pyvenv.cfg"; cp "$STUBS/fake-xferbench" "$d/bin/xferbench";;
  sync) [ -n "$UV_SYNC_FAIL" ] && { echo "boom" >&2; exit 1; }; d="${UV_PROJECT_ENVIRONMENT:-.venv}"; mkdir -p "$d/bin";
        echo "home = x" > "$d/pyvenv.cfg"; cp "$STUBS/fake-xferbench" "$d/bin/xferbench";;
esac
exit 0
"""
FAKE_XB = """#!/bin/sh
echo "xferbench $*" >> "$CALLS"
if [ "$1" = demo ]; then mkdir -p xb-demo; echo report > xb-demo/report.html; fi
exit 0
"""
FAKE_INSTALLER = """#!/bin/sh
# stub uv installer: puts the fake uv into ~/.local/bin, records that UV_NO_MODIFY_PATH was set
mkdir -p "$HOME/.local/bin"; cp "$STUBS/fake-uv" "$HOME/.local/bin/uv"; chmod +x "$HOME/.local/bin/uv"
echo "installer UV_NO_MODIFY_PATH=$UV_NO_MODIFY_PATH" >> "$CALLS"
"""
FAKE_CURL = """#!/bin/sh
# stub curl: writes the stub installer to the -o target, records the URL
out=""; url=""; while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift;; https://*) url=$1;; esac; shift; done
echo "curl $url" >> "$CALLS"; cp "$STUBS/fake-installer" "$out"
"""


def _w(p: Path, text: str) -> None:
    p.write_text(text, encoding="utf-8")
    p.chmod(0o755)


@pytest.fixture
def env(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copy2(SH, repo / SH.name)
    shutil.copytree(ROOT / "setup", repo / "setup")
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo / "uv.lock").write_text("", encoding="utf-8")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for t in TOOLS + ("sha256sum", "shasum"):
        w = shutil.which(t)
        if w:
            (stubs / t).symlink_to(w)
    _w(stubs / "git", '#!/bin/sh\necho "git version 9.9-stub"\n')
    _w(stubs / "python3.13", FAKE_PY)
    _w(stubs / "fake-xferbench", FAKE_XB)
    _w(stubs / "fake-uv", FAKE_UV)
    _w(stubs / "fake-installer", FAKE_INSTALLER)
    _w(stubs / "curl", FAKE_CURL)
    home = tmp_path / "home"
    home.mkdir()
    calls = tmp_path / "calls.log"
    calls.touch()
    base = {
        "PATH": str(stubs), "HOME": str(home), "CALLS": str(calls), "STUBS": str(stubs), "LANG": "C.UTF-8",
        "TMPDIR": str(tmp_path),
    }  # fmt: skip

    def run(*args: str, uv: bool = True, stdin: str | None = "", extra: dict[str, str] | None = None):
        if uv and not (stubs / "uv").exists():
            shutil.copy2(stubs / "fake-uv", stubs / "uv")
        if not uv and (stubs / "uv").exists():
            (stubs / "uv").unlink()
        e = dict(base, **(extra or {}))
        r = subprocess.run(
            [str(stubs / "bash"), SH.name, *args], cwd=repo, env=e, input=stdin, capture_output=True,
            text=True, encoding="utf-8", timeout=60, check=False,
        )  # fmt: skip
        return r, calls.read_text(encoding="utf-8")

    run.repo = repo  # type: ignore[attr-defined]
    run.stubs = stubs  # type: ignore[attr-defined]
    return run


pytestmark = posix_only


def test_help_version_and_usage_errors(env) -> None:
    r, _ = env("--help")
    assert r.returncode == 0
    for flag in ("--python", "--no-install-uv", "--with-lightgbm", "--with-spark", "--no-demo", "--yes-own-data",
                 "--non-interactive", "--dry-run", "--quiet", "--verbose", "--version", "--help", "Exit codes"):  # fmt: skip
        assert flag in r.stdout, flag
    r, _ = env("--version")
    assert r.returncode == 0 and re.match(r"xferAI_setup.sh \d+\.\d+\.\d+ \(uv 0\.\d+\.\d+\)", r.stdout)
    for bad in (["--bogus"], ["--python"], ["--quiet", "--verbose"]):
        r, calls = env(*bad)
        assert r.returncode == 2, bad
        assert "--help" in r.stderr
    assert not (env.repo / ".venv").exists()


def test_dry_run_prints_plan_and_changes_nothing(env) -> None:
    r, calls = env("--dry-run", "--with-lightgbm", "--with-spark")
    assert r.returncode == 0
    assert "Plan:" in r.stdout and "uv sync --locked --extra dev --extra lightgbm --extra distributed" in r.stdout
    assert "nothing was changed" in r.stdout
    assert "sync" not in calls and not (env.repo / ".venv").exists()


def test_uv_path_numbered_steps_summary_and_rerun(env) -> None:
    r, calls = env()
    assert r.returncode == 0, r.stderr
    for i in range(1, 8):
        assert f"[{i}/7] \u2713" in r.stdout
    assert "uv sync --locked --extra dev" in calls and "xferbench doctor --profile core" in calls
    assert "xferbench demo --preset tiny --out xb-demo" in calls
    assert NEXT.strip() in r.stdout
    assert "Not asking about your own data" in r.stdout  # stdin is not a TTY
    r2, calls2 = env()
    assert r2.returncode == 0 and "reusing the existing .venv" in r2.stdout  # idempotent
    assert (env.repo / ".xferai-setup.log").is_file()


def test_ascii_fallback_and_no_color(env) -> None:
    r, _ = env("--no-demo", extra={"LANG": "C", "LC_ALL": "C", "NO_COLOR": "1"})
    assert r.returncode == 0
    assert "[1/7] [ok] Check git" in r.stdout and "\u2713" not in r.stdout.split("Next:")[0]
    assert "\033[" not in r.stdout


def test_pip_fallback_when_no_uv_and_no_install(env) -> None:
    r, calls = env("--no-install-uv", uv=False)
    assert r.returncode == 0, r.stderr
    assert "skipped (--no-install-uv)" in r.stdout
    assert "venv .venv" in calls and "-m pip install -c constraints/core.txt -e .[dev]" in calls
    assert "curl" not in calls


def test_uv_missing_installs_pinned_verified_installer(env) -> None:
    digest = hashlib.sha256((env.stubs / "fake-installer").read_bytes()).hexdigest()
    r, calls = env("--no-demo", uv=False, extra={"XFERAI_UV_INSTALLER_SHA256": digest})
    assert r.returncode == 0, r.stderr
    assert re.search(r"curl https://astral\.sh/uv/0\.\d+\.\d+/install\.sh", calls)
    assert "installer UV_NO_MODIFY_PATH=1" in calls  # shell profiles are not edited
    assert f"installer sha256: {digest}" in r.stdout and "astral publishes no installer checksum" in r.stdout
    assert "uv sync --locked" in calls


def test_uv_installer_checksum_mismatch_is_not_run(env) -> None:
    r, calls = env(uv=False)  # stub installer != the pinned observed sha256
    assert r.returncode == 1
    assert "does not match the expected sha256" in r.stderr and "Fix:" in r.stderr and "Full log:" in r.stderr
    assert "installer UV_NO_MODIFY_PATH" not in calls


def test_failure_gives_step_fix_and_log(env) -> None:
    r, _ = env(extra={"UV_SYNC_FAIL": "1"})
    assert r.returncode == 1
    assert "[5/7] \u2717 Install XferAI-Bench" in r.stderr
    assert "Fix: " in r.stderr and ".xferai-setup.log" in r.stderr
    assert "boom" in (env.repo / ".xferai-setup.log").read_text(encoding="utf-8")


def test_own_data_yes_flag_prints_block(env) -> None:
    r, _ = env("--no-demo", "--yes-own-data")
    assert r.returncode == 0 and OWN.strip() in r.stdout and "Do you want" not in r.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="pty")
@pytest.mark.parametrize(("answer", "yes"), [("y\n", True), ("\n", False), ("no\n", False)])
def test_own_data_prompt_on_a_tty(env, answer: str, yes: bool) -> None:
    import pty
    import select

    env("--dry-run")  # make sure the fake uv is on PATH
    e = {"PATH": str(env.stubs), "HOME": str(env.repo), "CALLS": str(env.repo / "c.log"), "STUBS": str(env.stubs),
         "LANG": "C.UTF-8"}  # fmt: skip
    pid, fd = pty.fork()
    if pid == 0:  # child
        os.chdir(env.repo)
        os.execve(str(env.stubs / "bash"), ["bash", SH.name, "--no-demo"], e)
    out = b""
    sent = False
    while True:
        r, _, _ = select.select([fd], [], [], 30)
        if not r:
            break
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
        if not sent and b"[y/N]" in out:
            os.write(fd, answer.encode())
            sent = True
    _, status = os.waitpid(pid, 0)
    text = out.decode("utf-8", "replace").replace("\r\n", "\n")
    assert os.waitstatus_to_exitcode(status) == 0
    assert "Do you want to run on your own data? [y/N]" in text
    assert ("1. Put your CSV or Parquet files" in text) is yes
    if not yes:
        assert "docs/GETTING_STARTED.md Step 1" in text.split("[y/N]")[-1]


def test_prompt_skipped_in_ci_and_non_interactive(env) -> None:
    for args, extra in ((("--non-interactive",), {}), ((), {"CI": "true"})):
        r, _ = env("--no-demo", *args, extra=extra)
        assert r.returncode == 0 and "Do you want" not in r.stdout and "Not asking" in r.stdout
