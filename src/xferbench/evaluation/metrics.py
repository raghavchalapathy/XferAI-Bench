"""Point-forecast metrics on a fixed eligible population.

WMAPE = sum(|F-A|)/sum(A); Bias = sum(F)/sum(A) - 1. When sum(A) == 0 both are undefined: the value
is ``None`` with an explicit reason (never an epsilon).
"""

from __future__ import annotations

import numpy as np

ZERO_ACTUAL_REASON = "undefined: total actual units are zero"
EMPTY_REASON = "undefined: empty population"


def wmape(forecast: np.ndarray, actual: np.ndarray) -> tuple[float | None, str]:
    f, a = np.asarray(forecast, float), np.asarray(actual, float)
    if f.size == 0:
        return None, EMPTY_REASON
    denom = a.sum()
    if denom <= 0:
        return None, ZERO_ACTUAL_REASON
    return float(np.abs(f - a).sum() / denom), ""


def bias(forecast: np.ndarray, actual: np.ndarray) -> tuple[float | None, str]:
    f, a = np.asarray(forecast, float), np.asarray(actual, float)
    if f.size == 0:
        return None, EMPTY_REASON
    denom = a.sum()
    if denom <= 0:
        return None, ZERO_ACTUAL_REASON
    return float(f.sum() / denom - 1.0), ""


def mae(forecast: np.ndarray, actual: np.ndarray) -> float | None:
    f, a = np.asarray(forecast, float), np.asarray(actual, float)
    return float(np.abs(f - a).mean()) if f.size else None


def summarize(forecast: np.ndarray, actual: np.ndarray) -> dict:
    f, a = np.asarray(forecast, float), np.asarray(actual, float)
    if not (np.isfinite(f).all() and np.isfinite(a).all()):
        raise ValueError("metrics require finite forecasts and actuals on the fixed population")
    w, w_reason = wmape(f, a)
    b, b_reason = bias(f, a)
    return {
        "n_obs": int(f.size),
        "actual_total": float(a.sum()),
        "forecast_total": float(f.sum()),
        "abs_error_total": float(np.abs(f - a).sum()),
        "WMAPE": w,
        "WMAPE_reason": w_reason,
        "Bias": b,
        "Bias_reason": b_reason,
        "MAE": mae(f, a),
    }


def undefined_summary(n_obs: int, reason: str) -> dict:
    return {
        "n_obs": n_obs,
        "actual_total": None,
        "forecast_total": None,
        "abs_error_total": None,
        "WMAPE": None,
        "WMAPE_reason": reason,
        "Bias": None,
        "Bias_reason": reason,
        "MAE": None,
    }
