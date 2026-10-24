"""Optional PySpark twin of the Polars cleaning step, for complete data on a cluster.

Install with ``pip install -e ".[distributed]"``. Native DataFrame operations only: no ``toPandas``,
no UDFs, no multi-step aggregations (harness rule; ask the user before adding one).
"""

from __future__ import annotations

from typing import Any


def clean_observations_spark(sdf: Any, key: tuple[str, ...] = ("item_id", "fpg_id", "week_start")) -> Any:
    """Cast dates and drop exact duplicates using native Spark operations. Returns a Spark DataFrame."""
    try:
        from pyspark.sql import functions as F
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError('PySpark is optional: pip install -e ".[distributed]"') from exc
    for c in ("week_start", "week_end", "known_at"):
        if c in sdf.columns:
            sdf = sdf.withColumn(c, F.to_date(F.col(c)))
    return sdf.dropDuplicates()
