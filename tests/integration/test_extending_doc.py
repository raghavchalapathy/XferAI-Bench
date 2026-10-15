"""The external-method example in docs/EXTENDING.md runs as written."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from xferbench.methods.registry import unregister_method

DOC = Path(__file__).resolve().parents[2] / "docs" / "EXTENDING.md"


def test_extending_example_runs(tiny_runs: dict[str, Path], tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    code = re.search(r"```python\n(.*?)```", DOC.read_text(), re.S).group(1)  # type: ignore[union-attr]
    demo = tmp_path / "xb-demo"
    (demo / "data").mkdir(parents=True)
    (demo / "data" / "metadata.json").symlink_to(tiny_runs["metadata"])
    (demo / "splits.json").symlink_to(tiny_runs["splits"])
    monkeypatch.chdir(tmp_path)
    try:
        exec(compile(code, str(DOC), "exec"), {"__name__": "doc_example"})
    finally:
        unregister_method("EXT.half_b0")
    lb = pd.read_csv(tmp_path / "ext-run" / "leaderboard.csv")
    half = lb[(lb["variant_id"] == "EXT.half_b0") & (lb["scenario"] == "PAIR0-E")]["forecast_total"].iloc[0]
    full = lb[(lb["variant_id"] == "B0") & (lb["scenario"] == "PAIR0-E")]["forecast_total"].iloc[0]
    assert abs(half - full / 2) < 1e-6 * full
