"""Scalable equivalent of the protected evaluator's headline metrics (REVIEWER FLAG: not the reference).

The protected evaluator (``xferbench.evaluation``) stays the reference and is unchanged. This package computes the
same WMAPE(E), WMAPE(N), Bias and 0.5/0.5 objective as lazy partial sums (Polars) or distributed aggregations
(Spark), so only one small row per (board, variant, scenario) is ever collected. Parity is tested in
``tests/unit/test_scalable_eval.py``.
"""

from xferbench.scalable_eval.core import finalize, partial_sums_polars

__all__ = ["finalize", "partial_sums_polars"]
