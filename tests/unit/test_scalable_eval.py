"""Parity: scalable_eval (Polars lazy, Spark local) == protected evaluator on synthetic data."""

from __future__ import annotations

import importlib.util
import shutil
from typing import Any

import pandas as pd
import pytest

from xferbench.domains.registry import get_domain
from xferbench.evaluation.evaluator import evaluate
from xferbench.scalable_eval.core import finalize, partial_sums_polars, partial_sums_spark

TOL = 1e-9


@pytest.fixture(scope="module")
def inputs(
    tiny: Any, tiny_split: Any, tiny_runs: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    domain = get_domain(tiny.metadata.domain_plugin)
    requests = domain.requests(tiny, tiny_split, "validation")
    targets = domain.targets(tiny, requests)
    fc = pd.read_parquet(tiny_runs["validation"] / "forecasts.parquet")
    return fc, targets, requests, tiny.metadata.cohorts.selection_weights


def _compare(ref: dict, got: dict[str, list[dict]], weights: dict) -> int:
    n = 0
    for board, rows in ref["boards"].items():
        mine = {r["variant_id"]: r for r in got[board]}
        assert set(mine) == {r["variant_id"] for r in rows}
        for r in rows:
            m = mine[r["variant_id"]]
            for s in weights:
                for k in ("WMAPE", "Bias", "coverage"):
                    a, b = r["scenarios"][s][k], m["scenarios"][s][k]
                    assert (a is None) == (b is None), (board, r["variant_id"], s, k)
                    if a is not None:
                        assert abs(a - b) <= TOL, (board, r["variant_id"], s, k, a, b)
            assert (r["objective"] is None) == (m["objective"] is None)
            if r["objective"] is not None:
                assert abs(r["objective"] - m["objective"]) <= TOL
                n += 1
    return n


def _cases(fc: pd.DataFrame) -> list[pd.DataFrame]:
    holed = fc.drop(fc[fc["variant_id"] == fc["variant_id"].iloc[0]].index[:5])  # incomplete coverage
    failed = fc.copy()
    failed.loc[failed.index[:3], "status"] = "failed"
    return [fc, holed, failed]


def test_polars_parity(inputs: tuple) -> None:
    fc, targets, requests, w = inputs
    for case in _cases(fc):
        ref = evaluate(case, targets, requests, w)
        got = finalize(*partial_sums_polars(case, targets, requests), w)
        assert _compare(ref, got, w) >= 0
    assert _compare(evaluate(fc, targets, requests, w), finalize(*partial_sums_polars(fc, targets, requests), w), w) > 0


@pytest.mark.skipif(
    importlib.util.find_spec("pyspark") is None or shutil.which("java") is None,
    reason="pyspark extra + Java needed for Spark-local parity",
)
def test_spark_local_parity(inputs: tuple) -> None:
    import os

    from pyspark.sql import SparkSession

    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")

    fc, targets, requests, w = inputs
    spark = (
        SparkSession.builder.master("local[2]")
        .appName("xferbench-parity")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    try:

        def sdf(df: pd.DataFrame) -> Any:
            import polars as pl

            p = pl.from_pandas(df)
            for c, t in p.schema.items():
                if t.is_temporal():
                    p = p.with_columns(pl.col(c).cast(pl.Utf8))
            return spark.createDataFrame(p.to_dicts())

        t_s, r_s = (
            sdf(targets[["request_id", "horizon_week", "actual", "measured"]]),
            sdf(requests[["request_id", "scenario", "board"]]),
        )
        for case in _cases(fc):
            cols = ["method_id", "variant_id", "request_id", "horizon_week", "point_units", "status"]
            got = finalize(*partial_sums_spark(sdf(case[cols]), t_s, r_s), w)
            _compare(evaluate(case, targets, requests, w), got, w)
    finally:
        spark.stop()
