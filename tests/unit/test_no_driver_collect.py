"""F-5 / V2-5 lint guard: no driver materialisation (``.collect()``, ``.toPandas()``, ``.to_pandas()``) in package
code outside an explicit allow-list.

Allow-list key: (file, qualified function, method, receiver expression) with an exact call count, so a new
``.collect()`` inside an allow-listed function, or on a different receiver, fails. Also flagged everywhere:
an uncalled reference (``c = df.collect``), ``getattr(x, "collect")``, ``operator.methodcaller("collect")``,
``from m import to_pandas [as tp]``, and dynamic ``getattr(x, name)`` in the engines that touch big data.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "xferbench"
BANNED = {"collect", "toPandas", "to_pandas"}
DYNAMIC_SCOPES = ("scalable_eval/", "data_preparation/")  # dynamic getattr is refused here
Key = tuple[str, str, str, str]  # file, qualified function, kind/method, receiver
ALLOW: dict[Key, tuple[int, str]] = {
    ("scalable_eval/core.py", "partial_sums_polars", "collect", "counts"): (1, "aggregates only"),
    ("scalable_eval/core.py", "partial_sums_polars", "collect", "sums"): (1, "aggregates only"),
    ("scalable_eval/core.py", "partial_sums_polars", "collect", "variants"): (1, "aggregates only"),
    ("scalable_eval/core.py", "partial_sums_spark.small", "collect", "df"): (1, "Spark: one row per group"),
    ("data/io.py", "_to_pandas", "to_pandas", "table"): (1, "reference evaluator input boundary; small data"),
    ("data_preparation/data_cleaning/observations.py", "clean_observations", "collect", "lf"): (
        1,
        "terminal materialisation of the cleaned observation frame (pre-existing, Polars path)",
    ),
}


def scan(source: str, rel: str) -> Counter[Key]:
    hits: Counter[Key] = Counter()

    def visit(node: ast.AST, qual: list[str]) -> None:
        for ch in ast.iter_child_nodes(node):
            q = qual
            if isinstance(ch, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                q = [*qual, ch.name]
            name = ".".join(qual) or "<module>"
            if isinstance(ch, ast.Attribute) and ch.attr in BANNED:
                hits[(rel, name, ch.attr, ast.unparse(ch.value))] += 1
            elif isinstance(ch, ast.ImportFrom):
                for a in ch.names:
                    if a.name in BANNED:
                        hits[(rel, name, "import", f"{ch.module}.{a.name} as {a.asname or a.name}")] += 1
            elif isinstance(ch, ast.Call) and isinstance(ch.func, ast.Name | ast.Attribute):
                fn = ch.func.id if isinstance(ch.func, ast.Name) else ch.func.attr
                if fn in {"getattr", "methodcaller"}:
                    arg = ch.args[1] if fn == "getattr" and len(ch.args) > 1 else (ch.args[0] if ch.args else None)
                    if isinstance(arg, ast.Constant) and arg.value in BANNED:
                        hits[(rel, name, fn, str(arg.value))] += 1
                    elif fn == "getattr" and not isinstance(arg, ast.Constant) and rel.startswith(DYNAMIC_SCOPES):
                        hits[(rel, name, "dynamic-getattr", ast.unparse(arg) if arg else "")] += 1
            visit(ch, q)

    visit(ast.parse(source), [])
    return hits


def _all() -> Counter[Key]:
    total: Counter[Key] = Counter()
    for f in sorted(SRC.rglob("*.py")):
        total += scan(f.read_text(encoding="utf-8"), f.relative_to(SRC).as_posix())
    return total


def test_no_unlisted_driver_collect() -> None:
    bad = {k: n for k, n in _all().items() if k not in ALLOW or n != ALLOW[k][0]}
    assert not bad, f"driver materialisation outside the allow-list or over its count: {bad}"


def test_allowlist_is_not_stale() -> None:
    used = set(_all())
    assert set(ALLOW) <= used, f"stale allow-list entries: {set(ALLOW) - used}"


def test_guard_detects_bypasses() -> None:
    src = (
        "import operator\n"
        "from pyarrow import to_pandas as tp\n"
        "def partial_sums_polars(counts, other):\n"
        "    counts.collect(); other.collect()\n"
        "    c = counts.collect\n"
        "    getattr(counts, 'toPandas')()\n"
        "    operator.methodcaller('collect')(counts)\n"
        "    name = 'col' + 'lect'\n"
        "    getattr(counts, name)()\n"
    )
    hits = scan(src, "scalable_eval/core.py")
    rel = "scalable_eval/core.py"
    assert hits[(rel, "partial_sums_polars", "collect", "counts")] == 2  # second call on the same receiver
    assert (rel, "partial_sums_polars", "collect", "other") in hits
    assert (rel, "partial_sums_polars", "getattr", "toPandas") in hits
    assert (rel, "partial_sums_polars", "methodcaller", "collect") in hits
    assert (rel, "partial_sums_polars", "dynamic-getattr", "name") in hits
    assert any(k[2] == "import" for k in hits)
