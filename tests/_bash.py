"""Find a real POSIX bash for tests that run shell scripts (shared by every test module that needs one).

On Windows, ``shutil.which("bash")`` often returns C:\\Windows\\System32\\bash.exe, the WSL launcher, which is not a
POSIX shell (CI runs 40162698138 and 40166524733). Git for Windows ships a real bash; we try, in order: PATH (unless it
is the WSL stub), <ProgramFiles>\\Git\\bin\\bash.exe and usr\\bin\\bash.exe, and the Git install root derived from
``git --exec-path`` and from the ``git`` executable on PATH. Each candidate must answer ``echo ok``."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Iterable
from pathlib import PureWindowsPath


def is_wsl_stub(path: str) -> bool:
    p = path.replace("/", "\\").lower()
    return "\\windows\\system32\\" in p or "\\windowsapps\\" in p


def _git_root_from_exec_path(exec_path: str) -> str | None:
    # e.g. C:/Program Files/Git/mingw64/libexec/git-core -> C:/Program Files/Git
    parts = PureWindowsPath(exec_path.strip()).parts
    low = [x.lower() for x in parts]
    for marker in ("mingw64", "mingw32", "clangarm64", "usr"):
        if marker in low:
            return str(PureWindowsPath(*parts[: low.index(marker)]))
    return None


def _git_root_from_git_exe(git_exe: str) -> str | None:
    # C:\Program Files\Git\cmd\git.exe, ...\Git\bin\git.exe or ...\Git\mingw64\bin\git.exe -> ...\Git
    p = PureWindowsPath(git_exe)
    for anc in p.parents:
        if anc.name.lower() in ("cmd", "bin") and anc.parent.name.lower() not in ("mingw64", "mingw32", "usr"):
            return str(anc.parent)
        if anc.name.lower() in ("mingw64", "mingw32", "usr"):
            return str(anc.parent)
    return None


def candidates(
    environ: dict[str, str], which: Callable[[str], str | None], git_exec_path: Callable[[], str | None], nt: bool
) -> list[str]:
    """Ordered, de-duplicated bash candidates (pure; unit-tested with fakes)."""
    out: list[str] = []
    first = which("bash")
    if first and not is_wsl_stub(first):
        out.append(first)
    if nt:
        roots: list[str] = []
        for env in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LOCALAPPDATA"):
            if environ.get(env):
                sub = ("Programs", "Git") if env == "LOCALAPPDATA" else ("Git",)
                roots.append(str(PureWindowsPath(environ[env], *sub)))
        ep = git_exec_path()
        if ep and (r := _git_root_from_exec_path(ep)):
            roots.append(r)
        g = which("git")
        if g and (r := _git_root_from_git_exe(g)):
            roots.append(r)
        for root in roots:
            for rel in (("bin", "bash.exe"), ("usr", "bin", "bash.exe")):
                out.append(str(PureWindowsPath(root, *rel)))
    seen: set[str] = set()
    return [c for c in out if not (c.lower() in seen or seen.add(c.lower()))]  # type: ignore[func-returns-value]


def _git_exec_path() -> str | None:
    g = shutil.which("git")
    if not g:
        return None
    try:
        r = subprocess.run(
            [g, "--exec-path"], capture_output=True, text=True, encoding="utf-8", timeout=30, check=False
        )
    except OSError:
        return None
    return r.stdout.strip() or None


def probe(cands: Iterable[str]) -> str | None:
    for c in cands:
        if not os.path.isfile(c):
            continue
        try:
            r = subprocess.run(
                [c, "-c", "echo ok"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, check=False,
            )  # fmt: skip
        except OSError:
            continue
        if r.returncode == 0 and r.stdout.strip() == "ok":
            return c
    return None


def find_bash() -> str | None:
    return probe(candidates(dict(os.environ), shutil.which, _git_exec_path, os.name == "nt"))


BASH_EXE = find_bash()
