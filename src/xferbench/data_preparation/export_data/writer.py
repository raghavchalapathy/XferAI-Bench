"""Write a Polars frame as CSV or Parquet, with ISO dates and a stable row order."""

from __future__ import annotations

from pathlib import Path

import polars as pl


def export_table(df: pl.DataFrame, path: str | Path, sort_by: list[str] | None = None) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if sort_by:
        df = df.sort(sort_by)
    if out.suffix == ".parquet":
        df.write_parquet(out)
    elif out.suffix == ".csv":
        df.write_csv(out, date_format="%Y-%m-%d")
    else:
        raise ValueError(f"unsupported export format: {out.suffix} (use .csv or .parquet)")
    return out
