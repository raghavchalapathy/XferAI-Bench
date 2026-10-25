"""constraints/core.txt and constraints/extras.txt (pip fallback) must pin exactly the packages and versions locked in uv.lock.

Regenerate with scripts/export_constraints.sh. Parses uv.lock directly, so the check needs no uv binary.
constraints/minimum.txt is intentionally different (declared lower bounds) and is not checked here.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _locked_core(extras: tuple[str, ...] = ()) -> set[tuple[str, str]]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    by_name: dict[str, list[dict]] = {}
    for p in lock["package"]:
        by_name.setdefault(_norm(p["name"]), []).append(p)
    root = by_name["xfer-bench"][0]
    out: set[tuple[str, str]] = set()
    todo = [d["name"] for d in root.get("dependencies", [])]
    todo += [d["name"] for e in extras for d in root.get("optional-dependencies", {})[e]]
    seen: set[str] = set()
    while todo:
        n = _norm(todo.pop())
        if n in seen:
            continue
        seen.add(n)
        for p in by_name[n]:
            out.add((n, p["version"]))
            todo += [d["name"] for d in p.get("dependencies", [])]
    return out


def _constraints(name: str = "core.txt") -> set[tuple[str, str]]:
    pins = set()
    for line in (ROOT / "constraints" / name).read_text(encoding="utf-8").splitlines():
        line = line.split(";")[0].strip()
        if line and not line.startswith("#"):
            name, ver = line.split("==")
            pins.add((_norm(name), ver.strip()))
    return pins


def test_core_constraints_match_uv_lock() -> None:
    assert _constraints() == _locked_core(), "run scripts/export_constraints.sh after uv lock"


def test_extras_constraints_match_uv_lock() -> None:
    """constraints/extras.txt pins what the lightgbm and distributed extras add (the setup scripts' pip mode uses it)."""
    extras = _constraints("extras.txt")
    assert ("lightgbm", "4.7.0") in extras or any(n == "lightgbm" for n, _ in extras)
    assert extras == _locked_core(("lightgbm", "distributed")) - _locked_core(), "run scripts/export_constraints.sh"


def test_lock_covers_pyproject_extras_used_by_docs() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    root = next(p for p in lock["package"] if p["name"] == "xfer-bench")
    assert {"dev", "lightgbm", "distributed"} <= set(root.get("optional-dependencies", {})), root.keys()
