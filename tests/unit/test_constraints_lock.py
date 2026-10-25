"""constraints/core.txt (pip fallback) must pin exactly the core packages and versions locked in uv.lock.

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


def _locked_core() -> set[tuple[str, str]]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    by_name: dict[str, list[dict]] = {}
    for p in lock["package"]:
        by_name.setdefault(_norm(p["name"]), []).append(p)
    root = by_name["xfer-bench"][0]
    out: set[tuple[str, str]] = set()
    todo = [d["name"] for d in root.get("dependencies", [])]
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


def _constraints() -> set[tuple[str, str]]:
    pins = set()
    for line in (ROOT / "constraints/core.txt").read_text(encoding="utf-8").splitlines():
        line = line.split(";")[0].strip()
        if line and not line.startswith("#"):
            name, ver = line.split("==")
            pins.add((_norm(name), ver.strip()))
    return pins


def test_core_constraints_match_uv_lock() -> None:
    assert _constraints() == _locked_core(), "run scripts/export_constraints.sh after uv lock"


def test_lock_covers_pyproject_extras_used_by_docs() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    root = next(p for p in lock["package"] if p["name"] == "xfer-bench")
    assert {"dev", "lightgbm", "distributed"} <= set(root.get("optional-dependencies", {})), root.keys()
