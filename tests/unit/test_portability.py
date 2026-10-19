"""Windows portability guards: explicit text encodings and no symlinks (CI runs on windows-latest)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _py(sub: str) -> list[Path]:
    return sorted((ROOT / sub).rglob("*.py"))


def _missing_encoding(path: Path) -> list[str]:
    bad = []
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(n, ast.Call):
            continue
        kws = {k.arg for k in n.keywords}
        name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        if name in ("read_text", "write_text") and "encoding" not in kws:
            bad.append(f"{path.name}:{n.lineno} {name}")
        if name == "open" and "encoding" not in kws:
            pos = 1 if isinstance(n.func, ast.Name) else 0
            mode = n.args[pos] if len(n.args) > pos else next((k.value for k in n.keywords if k.arg == "mode"), None)
            if not (isinstance(mode, ast.Constant) and "b" in str(mode.value)):
                bad.append(f"{path.name}:{n.lineno} open")
        if name == "run" and "text" in kws and "encoding" not in kws:
            bad.append(f"{path.name}:{n.lineno} subprocess text=True without encoding")
    return bad


def test_text_io_has_explicit_encoding() -> None:
    bad = [b for p in _py("src") + _py("tests") for b in _missing_encoding(p)]
    assert bad == []


def test_tests_do_not_create_symlinks() -> None:
    hits = [
        p.name for p in _py("tests") if p.name != Path(__file__).name and "symlink_to(" in p.read_text(encoding="utf-8")
    ]
    assert hits == []
