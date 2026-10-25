"""Check for the proposed ``polars_swap_parity`` rule (proposal only; not adopted).

A *swap* is a function whose docstring says it is a Polars version that replaces existing code (docstring matches
``SWAP_DOC``). Each swap must keep ``<name>_reference`` in the same class or module, and some test file under
``tests/`` must call ``<name>_reference`` (the parity test). Static AST scan; nothing is imported or executed.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SWAP_DOC = re.compile(r"\bpolars\b.*\breplaces\b", re.IGNORECASE | re.DOTALL)


def _scopes(tree: ast.Module) -> list[list[ast.stmt]]:
    return [tree.body] + [n.body for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]


def find_swap_violations(root: Path, src: str = "src", tests: str = "tests") -> list[str]:
    """Return one message per swap missing its ``*_reference`` or a parity test. Empty list means compliant."""
    test_text = "\n".join(p.read_text(encoding="utf-8") for p in sorted((root / tests).rglob("*.py")))
    out = []
    for py in sorted((root / src).rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for body in _scopes(tree):
            fns = {n.name: n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for name, fn in fns.items():
                doc = ast.get_docstring(fn) or ""
                if name.endswith("_reference") or not SWAP_DOC.search(doc):
                    continue
                rel = py.relative_to(root).as_posix()
                ref = f"{name}_reference"
                if ref not in fns:
                    out.append(f"{rel}:{fn.lineno}: swap {name} has no {ref}")
                elif not re.search(rf"\b{re.escape(ref)}\b", test_text):
                    out.append(f"{rel}:{fn.lineno}: swap {name} has no parity test calling {ref}")
    return out
