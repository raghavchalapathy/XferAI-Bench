"""Polars data_preparation: cleaning reports issues without silent fixes; export round-trips."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from xferbench.data_preparation.data_cleaning import clean_observations
from xferbench.data_preparation.export_data import export_table

ROOT = Path(__file__).resolve().parents[2]


def _frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "item_id": ["1", "1", "1", "2"],
            "fpg_id": ["F1", "F1", "F1", "F1"],
            "week_start": ["2024-01-01", "2024-01-01", "2024-01-01", "2024-01-08"],
            "units": [1.0, 1.0, 2.0, -1.0],
        }
    )


def test_clean_drops_exact_duplicates_and_flags_issues() -> None:
    out, rep = clean_observations(_frame())
    assert rep.rows_in == 4 and rep.rows_out == 3
    assert rep.exact_duplicates_dropped == 1
    assert rep.duplicate_keys == 1  # same key, different units: flagged, not fixed
    assert rep.negative_units == 1
    assert out.schema["week_start"] == pl.Date


def test_clean_reads_the_shipped_sample_csv() -> None:
    out, rep = clean_observations(ROOT / "examples/retail_synthetic/sample/observations.csv")
    assert rep.rows_in == out.height + rep.exact_duplicates_dropped
    assert out.schema["units"] == pl.Float64


def test_export_roundtrip(tmp_path: Path) -> None:
    out, _ = clean_observations(_frame())
    for name in ("o.csv", "o.parquet"):
        p = export_table(out, tmp_path / name, sort_by=["item_id", "week_start"])
        back = pl.read_parquet(p) if p.suffix == ".parquet" else pl.read_csv(p, schema_overrides={"item_id": pl.Utf8})
        assert back.height == out.height
