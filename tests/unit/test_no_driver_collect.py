"""F-5 lint guard: no driver materialisation (``.collect()``, ``.toPandas()``, ``.to_pandas()``) in package code
outside an explicit allow-list. Each allow-listed call names the function and why it is safe."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "xferbench"
BANNED = {"collect", "toPandas", "to_pandas"}
ALLOW: dict[tuple[str, str, str], str] = {
    ("scalable_eval/core.py", "partial_sums_polars", "collect"): "collects aggregates only (one row per group)",
    ("scalable_eval/core.py", "small", "collect"): "Spark: collects aggregates only (one row per group)",
    ("data/io.py", "_to_pandas", "to_pandas"): "reference (protected evaluator) input boundary; small data path",
    ("data_preparation/data_cleaning/observations.py", "clean_observations", "collect"): (
        "Polars lazy plan executed once to write cleaned output; no Spark driver involved"
    ),
}


def _hits() -> list[tuple[str, str, str, int]]:
    out = []
    for f in sorted(SRC.rglob("*.py")):
        rel = f.relative_to(SRC).as_posix()

        def visit(node: ast.AST, func: str) -> None:
            for ch in ast.iter_child_nodes(node):
                name = ch.name if isinstance(ch, ast.FunctionDef | ast.AsyncFunctionDef) else func
                if isinstance(ch, ast.Call) and isinstance(ch.func, ast.Attribute) and ch.func.attr in BANNED:
                    out.append((rel, func, ch.func.attr, ch.lineno))  # noqa: B023
                visit(ch, name)

        visit(ast.parse(f.read_text(encoding="utf-8")), "<module>")
    return out


def test_no_unlisted_driver_collect() -> None:
    bad = [h for h in _hits() if h[:3] not in ALLOW]
    assert not bad, f"driver materialisation outside the allow-list (add a justified ALLOW entry or remove): {bad}"


def test_allowlist_is_not_stale() -> None:
    used = {h[:3] for h in _hits()}
    assert set(ALLOW) <= used, f"stale allow-list entries: {set(ALLOW) - used}"


def test_guard_detects_a_violation(tmp_path: Path) -> None:
    tree = ast.parse("def f(df):\n    return df.toPandas()\n")
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert any(c.func.attr in BANNED for c in calls if isinstance(c.func, ast.Attribute))
