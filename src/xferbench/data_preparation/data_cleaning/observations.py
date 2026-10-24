"""Clean the observations table with Polars (lazy, streaming-friendly).

Simple, single-pass steps only (harness rule: try simple steps before multi-step aggregations):
1. cast keys to string and dates to ``Date``;
2. drop exact duplicate rows;
3. flag (do not silently fix) negative units and duplicate (item, location, week) keys.

The same logic has a native PySpark twin in :mod:`xferbench.data_preparation.spark` for complete data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl

KEY = ("item_id", "fpg_id", "week_start")
DATE_COLUMNS = ("week_start", "week_end", "known_at")


@dataclass(frozen=True)
class CleaningReport:
    rows_in: int
    rows_out: int
    exact_duplicates_dropped: int
    duplicate_keys: int
    negative_units: int

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


def _typed(lf: pl.LazyFrame, key: tuple[str, ...]) -> pl.LazyFrame:
    names = lf.collect_schema().names()
    casts = [pl.col(c).cast(pl.Utf8) for c in key if c in names and c not in DATE_COLUMNS]
    dates = [pl.col(c).cast(pl.Utf8).str.to_date(strict=True) for c in DATE_COLUMNS if c in names]
    return lf.with_columns(casts + dates)


def clean_observations(
    source: pl.DataFrame | pl.LazyFrame | str | Path,
    key: tuple[str, ...] = KEY,
    target: str = "units",
) -> tuple[pl.DataFrame, CleaningReport]:
    """Return the cleaned observations and a report. CSV/Parquet paths are scanned lazily."""
    if isinstance(source, (str, Path)):
        p = Path(source)
        lf = pl.scan_parquet(p) if p.suffix == ".parquet" else pl.scan_csv(p, infer_schema=False)
        lf = lf.with_columns(pl.col(target).cast(pl.Float64))
    else:
        lf = source.lazy()
    lf = _typed(lf, key)
    raw = lf.collect()
    out = raw.unique(maintain_order=True)
    dup_keys = out.height - out.select(list(key)).unique().height
    negative = out.filter(pl.col(target) < 0).height
    report = CleaningReport(
        rows_in=raw.height,
        rows_out=out.height,
        exact_duplicates_dropped=raw.height - out.height,
        duplicate_keys=dup_keys,
        negative_units=negative,
    )
    return out, report
