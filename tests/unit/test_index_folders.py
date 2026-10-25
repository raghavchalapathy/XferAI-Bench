"""Open question 1 (decision v4): top-level models/, harness/, data_preparation/ stay README index folders.

All importable code lives in src/xferbench (one installable package). A .py file at those top-level
folders would shadow or duplicate the package, so this test fails if one appears.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX_FOLDERS = ("models", "harness", "data_preparation")


def test_index_folders_hold_no_python() -> None:
    for name in INDEX_FOLDERS:
        d = ROOT / name
        assert (d / "README.md").is_file(), f"{name}/README.md missing"
        assert not list(d.rglob("*.py")), f"{name}/ must stay an index folder; code goes in src/xferbench/{name}"
        assert (ROOT / "src" / "xferbench" / name / "__init__.py").is_file()
