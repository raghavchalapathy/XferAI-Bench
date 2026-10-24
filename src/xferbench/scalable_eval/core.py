"""Partial sums -> WMAPE / Bias / objective, matching ``xferbench.evaluation.evaluator`` semantics.

Semantics copied from the protected evaluator (read-only):
- population = targets with ``measured`` inner-joined to requests on request_id
- the population is LEFT-joined per variant_id to all its forecast rows; duplicate keys count as extra rows
- non-finite actuals on a fully covered block raise ValueError (as metrics.summarize)
- a row is valid when status in ("success", "fallback") and point_units is finite
- per (board, variant, scenario): metrics are defined only when every eligible week has a valid forecast and
  sum(actual) > 0; WMAPE = sum|F-A| / sum(A); Bias = sum(F)/sum(A) - 1
- objective = sum_s w_s * WMAPE_s, undefined if any scenario's WMAPE is undefined
"""

from __future__ import annotations

from typing import Any

import polars as pl

VALID_STATUSES = ("success", "fallback")
KEYS = ["request_id", "horizon_week"]
PARTIAL_COLS = [
    "board",
    "variant_id",
    "scenario",
    "n_matched_rows",
    "n_matched_keys",
    "n_valid",
    "abs_error_total",
    "actual_total",
    "forecast_total",
]


def _lazy(x: Any) -> pl.LazyFrame:
    if isinstance(x, pl.LazyFrame):
        return x
    if isinstance(x, pl.DataFrame):
        return x.lazy()
    return pl.from_pandas(x).lazy()  # convenience for the parity test / small in-memory inputs


def partial_sums_polars(forecasts: Any, targets: Any, requests: Any) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Return (population counts per board/scenario, partial sums per board/variant/scenario, variants).

    Mirrors the reference's per-variant LEFT join of the population to *all* forecast rows of that variant_id
    (any status, any method_id): a key with c>1 forecast rows contributes c joined rows (duplicates are counted,
    exactly as the reference counts them), a key with no row contributes one unmatched row. Lazy until collect;
    only aggregates are collected.
    """
    pop = (
        _lazy(targets)
        .filter(pl.col("measured"))
        .select([*KEYS, pl.col("actual").cast(pl.Float64)])
        .join(_lazy(requests).select(["request_id", "scenario", "board"]), on="request_id", how="inner")
    )
    counts = pop.group_by(["board", "scenario"]).agg(
        pl.len().alias("n_eligible"),
        pl.col("actual").sum().alias("pop_actual"),
        (pl.col("actual").is_null() | ~pl.col("actual").is_finite()).fill_null(True).sum().alias("n_bad_actual"),
    )
    fc = _lazy(forecasts).select(["method_id", "variant_id", *KEYS, pl.col("point_units").cast(pl.Float64), "status"])
    valid = (pl.col("status").is_in(VALID_STATUSES) & pl.col("point_units").is_finite()).fill_null(False)
    joined = pop.join(fc.drop("method_id"), on=KEYS, how="inner").with_columns(valid.alias("_valid"))
    vsel = pl.col("_valid")
    sums = (
        joined.group_by(["board", "variant_id", "scenario"])
        .agg(
            pl.len().alias("n_matched_rows"),
            pl.struct(KEYS).n_unique().alias("n_matched_keys"),
            vsel.sum().alias("n_valid"),
            (pl.col("point_units") - pl.col("actual")).abs().filter(vsel).sum().alias("abs_error_total"),
            pl.col("actual").filter(vsel).sum().alias("actual_total"),
            pl.col("point_units").filter(vsel).sum().alias("forecast_total"),
        )
        .select(PARTIAL_COLS)
    )
    variants = fc.select(["method_id", "variant_id"]).unique()
    return counts.collect(), sums.collect(), variants.collect()  # aggregates only


def partial_sums_spark(forecasts: Any, targets: Any, requests: Any) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Same as :func:`partial_sums_polars` on Spark DataFrames (native functions only, no toPandas).

    Only the aggregated rows (one per board/variant/scenario) are collected to the driver.
    """
    from pyspark.sql import functions as F

    pop = (
        targets.filter(F.col("measured"))
        .select(*KEYS, F.col("actual").cast("double").alias("actual"))
        .join(requests.select("request_id", "scenario", "board"), on="request_id", how="inner")
    )
    bad_actual = F.col("actual").isNull() | F.isnan("actual") | (F.abs("actual") == float("inf"))
    counts = pop.groupBy("board", "scenario").agg(
        F.count(F.lit(1)).alias("n_eligible"),
        F.sum("actual").alias("pop_actual"),
        F.sum(F.when(bad_actual, 1).otherwise(0)).alias("n_bad_actual"),
    )
    fc = forecasts.select(
        "method_id", "variant_id", *KEYS, F.col("point_units").cast("double").alias("point_units"), "status"
    )
    finite = F.col("point_units").isNotNull() & ~F.isnan("point_units") & (F.abs("point_units") != float("inf"))
    valid = F.coalesce(F.col("status").isin(*VALID_STATUSES) & finite, F.lit(False))
    joined = pop.join(fc.drop("method_id"), on=KEYS, how="inner").withColumn("_valid", valid)
    v = F.col("_valid")
    sums = (
        joined.groupBy("board", "variant_id", "scenario")
        .agg(
            F.count(F.lit(1)).alias("n_matched_rows"),
            F.countDistinct(*KEYS).alias("n_matched_keys"),
            F.sum(F.when(v, 1).otherwise(0)).alias("n_valid"),
            F.sum(F.when(v, F.abs(F.col("point_units") - F.col("actual")))).alias("abs_error_total"),
            F.sum(F.when(v, F.col("actual"))).alias("actual_total"),
            F.sum(F.when(v, F.col("point_units"))).alias("forecast_total"),
        )
        .select(*PARTIAL_COLS)
    )
    variants = fc.select("method_id", "variant_id").distinct()

    def small(df: Any, cols: list[str]) -> pl.DataFrame:
        rows = [r.asDict() for r in df.collect()]  # aggregates only (allow-listed in test_no_driver_collect)
        return pl.DataFrame(rows, schema=cols, orient="row") if rows else pl.DataFrame(schema=cols)

    return (
        small(counts, ["board", "scenario", "n_eligible", "pop_actual", "n_bad_actual"]),
        small(sums, PARTIAL_COLS),
        small(variants, ["method_id", "variant_id"]),
    )


def finalize(
    counts: pl.DataFrame, sums: pl.DataFrame, variants: pl.DataFrame, weights: dict[str, float]
) -> dict[str, list[dict[str, Any]]]:
    """Combine partial sums into per-board rows {method_id, variant_id, scenarios{s: WMAPE, Bias, ...}, objective}."""
    cnt = {(r["board"], r["scenario"]): r["n_eligible"] for r in counts.iter_rows(named=True)}
    bad = {(r["board"], r["scenario"]): int(r.get("n_bad_actual") or 0) for r in counts.iter_rows(named=True)}
    part = {(r["board"], r["variant_id"], r["scenario"]): r for r in sums.iter_rows(named=True)}
    boards: dict[str, list[dict[str, Any]]] = {}
    for board in sorted({b for b, _ in cnt}):
        rows = []
        for v in variants.sort(["method_id", "variant_id"]).iter_rows(named=True):
            per_s: dict[str, dict[str, Any]] = {}
            for s in sorted(weights):
                n_pop = int(cnt.get((board, s), 0))
                p = part.get((board, v["variant_id"], s))
                n_valid = int(p["n_valid"]) if p else 0
                # reference left join: unmatched keys count once, duplicated keys count once per forecast row
                n = n_pop - int(p["n_matched_keys"]) + int(p["n_matched_rows"]) if p else n_pop
                if n and n_valid == n and bad.get((board, s), 0):
                    # same contract as the reference (metrics.summarize): non-finite actuals are an error
                    raise ValueError("metrics require finite forecasts and actuals on the fixed population")
                blk: dict[str, Any] = {"n_eligible": n, "n_forecast": n_valid, "coverage": (n_valid / n) if n else None}
                if n == 0 or n_valid < n or p is None or p["actual_total"] <= 0:
                    blk |= {"WMAPE": None, "Bias": None}
                else:
                    a = float(p["actual_total"])
                    blk |= {
                        "WMAPE": float(p["abs_error_total"]) / a,
                        "Bias": float(p["forecast_total"]) / a - 1.0,
                        "abs_error_total": float(p["abs_error_total"]),
                        "actual_total": a,
                    }
                per_s[s] = blk
            wm = [per_s[s]["WMAPE"] for s in weights]
            obj = None if any(m is None for m in wm) else float(sum(weights[s] * per_s[s]["WMAPE"] for s in weights))
            rows.append(
                {"method_id": v["method_id"], "variant_id": v["variant_id"], "scenarios": per_s, "objective": obj}
            )
        boards[str(board)] = rows
    return boards
