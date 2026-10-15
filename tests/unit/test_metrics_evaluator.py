from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from xferbench.evaluation.evaluator import equal_weight_objective, evaluate
from xferbench.evaluation.metrics import ZERO_ACTUAL_REASON, bias, summarize, wmape
from xferbench.orchestration.runner import validate_batch

W = {"PAIR0-E": 0.5, "PAIR0-N": 0.5}


def test_wmape_and_bias_by_hand() -> None:
    f, a = np.array([1.0, 2.0, 3.0]), np.array([2.0, 2.0, 2.0])
    assert wmape(f, a) == (pytest.approx(2 / 6), "")
    assert bias(f, a) == (pytest.approx(0.0), "")
    s = summarize(np.array([3.0, 3.0]), np.array([1.0, 1.0]))
    assert s["WMAPE"] == pytest.approx(2.0) and s["Bias"] == pytest.approx(2.0) and s["MAE"] == pytest.approx(2.0)


def test_zero_denominator_is_undefined_not_epsilon() -> None:
    assert wmape(np.array([1.0]), np.array([0.0])) == (None, ZERO_ACTUAL_REASON)
    assert bias(np.array([0.0]), np.array([0.0])) == (None, ZERO_ACTUAL_REASON)


def test_metrics_reject_non_finite() -> None:
    with pytest.raises(ValueError):
        summarize(np.array([np.nan]), np.array([1.0]))


def test_equal_weight_objective() -> None:
    obj, _ = equal_weight_objective({"PAIR0-E": {"WMAPE": 0.4}, "PAIR0-N": {"WMAPE": 1.0}}, W)
    assert obj == pytest.approx(0.7)
    obj, why = equal_weight_objective({"PAIR0-E": {"WMAPE": 0.4}, "PAIR0-N": {"WMAPE": None, "WMAPE_reason": "x"}}, W)
    assert obj is None and "PAIR0-N" in why


def _requests() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "request_id": ["e1", "n1"],
            "scenario": ["PAIR0-E", "PAIR0-N"],
            "board": "cold_c0",
            "ranked": True,
            "category": "c",
            "region": "r",
            "fixture_kind": None,
        }
    )


def _targets() -> pd.DataFrame:
    rows = []
    for rid in ("e1", "n1"):
        for h in (1, 2, 3):
            rows.append(
                {"request_id": rid, "horizon_week": h, "actual": 2.0, "measured": h != 3, "availability": "in_stock"}
            )
    return pd.DataFrame(rows)


def _fc(variant: str, values: dict[str, list[float | None]]) -> pd.DataFrame:
    rows = []
    for rid, vals in values.items():
        for h, v in enumerate(vals, 1):
            rows.append(
                {
                    "variant_id": variant,
                    "method_id": variant,
                    "request_id": rid,
                    "horizon_week": h,
                    "point_units": np.nan if v is None else v,
                    "status": "failed" if v is None else "success",
                    "reason": "",
                }
            )
    return pd.DataFrame(rows)


def test_fixed_population_and_unrankable_coverage() -> None:
    good = _fc("good", {"e1": [2, 3, 100], "n1": [1, 2, 100]})
    gappy = _fc("gappy", {"e1": [2, None, 2], "n1": [2, 2, 2]})
    res = evaluate(pd.concat([good, gappy]), _targets(), _requests(), W)
    assert res["population"]["eligible_weeks"]["cold_c0"] == 4
    rows = {r["variant_id"]: r for r in res["boards"]["cold_c0"]}
    g = rows["good"]
    # week 3 is unmeasured, so its 100-unit forecast is not scored for anyone
    assert g["scenarios"]["PAIR0-E"]["WMAPE"] == pytest.approx(1 / 4)
    assert g["scenarios"]["PAIR0-N"]["WMAPE"] == pytest.approx(1 / 4)
    assert g["objective"] == pytest.approx(0.25) and g["rank"]["objective"] == 1
    bad = rows["gappy"]
    assert bad["scenarios"]["PAIR0-E"]["coverage"] == pytest.approx(0.5)
    assert bad["scenarios"]["PAIR0-E"]["WMAPE"] is None
    assert not bad["rankable"] and bad["rank"]["objective"] is None


def test_all_zero_scenario_is_undefined() -> None:
    t = _targets()
    t.loc[t["request_id"] == "n1", "actual"] = 0.0
    res = evaluate(_fc("v", {"e1": [2, 2, 2], "n1": [1, 1, 1]}), t, _requests(), W)
    row = res["boards"]["cold_c0"][0]
    assert row["scenarios"]["PAIR0-N"]["WMAPE"] is None
    assert row["scenarios"]["PAIR0-N"]["all_zero_launch_forecast_units"] == pytest.approx(2.0)
    assert row["objective"] is None


def _batch(n: int, rid: str = "r1", status: str = "success", value: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame(
        {"request_id": rid, "horizon_week": range(1, n + 1), "point_units": value, "status": status, "reason": ""}
    )


def _req() -> pd.DataFrame:
    return pd.DataFrame({"request_id": ["r1"], "origin": [pd.Timestamp("2025-01-06")]})


def test_forecast_contract_exactly_52_rows() -> None:
    ok, problems = validate_batch(_batch(52), _req(), 52)
    assert not problems and len(ok) == 52 and set(ok["status"]) == {"success"}
    bad, problems = validate_batch(_batch(51), _req(), 52)
    assert problems and len(bad) == 52 and set(bad["status"]) == {"failed"}
    assert bad["point_units"].isna().all()
    assert "contract_violation" in bad["reason"].iloc[0]


@pytest.mark.parametrize("value,status", [(-1.0, "success"), (np.inf, "fallback"), (1.0, "failed")])
def test_forecast_contract_values(value: float, status: str) -> None:
    out, problems = validate_batch(_batch(52, status=status, value=value), _req(), 52)
    assert problems and set(out["status"]) == {"failed"}


def test_missing_request_becomes_failed_rows() -> None:
    out, problems = validate_batch(_batch(0), _req(), 52)
    assert problems and len(out) == 52 and set(out["status"]) == {"failed"}
