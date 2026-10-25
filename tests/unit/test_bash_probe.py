"""Unit tests for the shared bash probe's Windows candidate resolution (pure; no Windows needed)."""

from __future__ import annotations

from tests._bash import _git_root_from_exec_path, _git_root_from_git_exe, candidates, is_wsl_stub


def _which(table: dict[str, str]):
    return lambda name: table.get(name)


def test_wsl_stub_skipped_and_program_files_git_tried() -> None:
    c = candidates({"ProgramFiles": r"C:\Program Files"}, _which({"bash": r"C:\Windows\System32\bash.exe"}),
                   lambda: None, nt=True)  # fmt: skip
    assert c == [r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"]


def test_git_exec_path_and_where_git_roots() -> None:
    c = candidates({}, _which({"git": r"D:\tools\PortableGit\cmd\git.exe"}),
                   lambda: "D:/tools/PortableGit/mingw64/libexec/git-core", nt=True)  # fmt: skip
    assert c == [r"D:\tools\PortableGit\bin\bash.exe", r"D:\tools\PortableGit\usr\bin\bash.exe"]


def test_dedup_case_insensitive_and_real_path_bash_first() -> None:
    c = candidates({"ProgramFiles": r"C:\Program Files", "ProgramW6432": r"C:\program files"},
                   _which({"bash": r"C:\Program Files\Git\usr\bin\bash.exe"}), lambda: None, nt=True)  # fmt: skip
    assert c[0] == r"C:\Program Files\Git\usr\bin\bash.exe" and len(c) == 2


def test_posix_uses_path_only() -> None:
    assert candidates({"ProgramFiles": "x"}, _which({"bash": "/bin/bash"}), lambda: "x", nt=False) == ["/bin/bash"]


def test_root_derivation_helpers() -> None:
    assert _git_root_from_exec_path("C:/Program Files/Git/mingw64/libexec/git-core") == r"C:\Program Files\Git"
    assert _git_root_from_exec_path("garbage") is None
    assert _git_root_from_git_exe(r"C:\Program Files\Git\mingw64\bin\git.exe") == r"C:\Program Files\Git"
    assert _git_root_from_git_exe(r"C:\Program Files\Git\bin\git.exe") == r"C:\Program Files\Git"
    assert is_wsl_stub(r"C:\Users\a\AppData\Local\Microsoft\WindowsApps\bash.exe")
