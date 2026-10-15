"""Join forecasts to evaluator-owned targets and compute boards, rankings and slices.

The eligible population is fixed per board BEFORE looking at any forecast: every measured target
week of every request on that board. A method missing any eligible forecast is unrankable on that
scenario; its metrics are not computed on a convenient subset.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from xferbench.calendar import horizon_bucket
from xferbench.evaluation.metrics import summarize, undefined_summary
from xferbench.util import hash_obj

VALID_STATUSES = ("success", "fallback")


def intermittency_bucket(zero_share: float, total: float) -> str:
    if total == 0:
        return "all_zero_actual"
    if zero_share >= 0.9:
        return "zero>=90%"
    if zero_share >= 0.7:
        return "zero70-90%"
    return "zero<70%"


def population(targets: pd.DataFrame, requests: pd.DataFrame) -> pd.DataFrame:
    meta_cols = ["request_id", "scenario", "board", "ranked", "category", "region", "fixture_kind"]
    pop = targets[targets["measured"]].merge(requests[meta_cols], on="request_id", how="inner")
    pop["horizon_bucket"] = horizon_bucket(pop["horizon_week"])
    per_launch = pop.groupby("request_id")["actual"].agg(total="sum", zero_share=lambda s: float((s == 0).mean()))
    pop["intermittency"] = pop["request_id"].map(
        {rid: intermittency_bucket(r.zero_share, r.total) for rid, r in per_launch.iterrows()}
    )
    return pop


def population_hashes(pop: pd.DataFrame) -> dict[str, str]:
    out = {}
    for board, grp in pop.groupby("board"):
        keys = sorted(f"{r}|{h}" for r, h in zip(grp["request_id"], grp["horizon_week"], strict=True))
        out[str(board)] = hash_obj(keys)
    return out


def _block(rows: pd.DataFrame) -> dict:
    n = len(rows)
    valid = rows["status"].isin(VALID_STATUSES) & np.isfinite(rows["point_units"].astype(float))
    n_valid = int(valid.sum())
    out = {
        "n_eligible": n,
        "n_forecast": n_valid,
        "coverage": (n_valid / n) if n else None,
        "n_failed": int(rows["status"].isin(["failed", "skipped"]).sum() + rows["status"].isna().sum()),
        "n_fallback": int((rows["status"] == "fallback").sum()),
        "n_launches": int(rows["request_id"].nunique()),
    }
    if n == 0:
        out.update(undefined_summary(0, "undefined: empty population"))
    elif n_valid < n:
        out.update(undefined_summary(n, f"undefined: incomplete coverage ({n_valid}/{n} eligible weeks)"))
    else:
        out.update(summarize(rows["point_units"].to_numpy(float), rows["actual"].to_numpy(float)))
    launch_tot = rows.groupby("request_id").agg(a=("actual", "sum"), f=("point_units", "sum"))
    zero = launch_tot[launch_tot["a"] == 0]
    out["n_all_zero_launches"] = len(zero)
    out["all_zero_launch_forecast_units"] = float(zero["f"].sum()) if n_valid == n else None
    return out


def evaluate(
    forecasts: pd.DataFrame, targets: pd.DataFrame, requests: pd.DataFrame, scenario_weights: dict[str, float]
) -> dict:
    pop = population(targets, requests)
    fc = forecasts[["variant_id", "method_id", "request_id", "horizon_week", "point_units", "status", "reason"]]
    variants = forecasts[["method_id", "variant_id"]].drop_duplicates().sort_values(["method_id", "variant_id"])
    boards: dict[str, list[dict]] = {}
    slices: list[dict] = []
    for board, bpop in pop.groupby("board"):
        rows_out = []
        for v in variants.itertuples(index=False):
            vf = fc[fc["variant_id"] == v.variant_id]
            joined = bpop.merge(vf, on=["request_id", "horizon_week"], how="left")
            per_s = {}
            for s in sorted(scenario_weights):
                per_s[s] = _block(joined[joined["scenario"] == s])
            obj, obj_reason = equal_weight_objective(per_s, scenario_weights)
            rows_out.append(
                {
                    "method_id": v.method_id,
                    "variant_id": v.variant_id,
                    "board": board,
                    "ranked_board": bool(bpop["ranked"].all()),
                    "scenarios": per_s,
                    "objective": obj,
                    "objective_reason": obj_reason,
                    "rankable": obj is not None and all(b["coverage"] == 1.0 for b in per_s.values()),
                    "status_counts": vf["status"].value_counts().to_dict(),
                }
            )
            if board == "cold_c0":
                for dim in ("horizon_bucket", "category", "region", "intermittency", "availability"):
                    for (s, val), grp in joined.groupby(["scenario", dim]):
                        slices.append(
                            {
                                "variant_id": v.variant_id,
                                "method_id": v.method_id,
                                "board": board,
                                "scenario": s,
                                "dimension": dim,
                                "value": str(val),
                                **_block(grp),
                            }
                        )
        _rank(rows_out, list(scenario_weights))
        boards[str(board)] = rows_out
    fixtures = _fixture_status(pop, fc, requests)
    return {
        "population": {
            "hashes": population_hashes(pop),
            "eligible_weeks": {str(b): len(g) for b, g in pop.groupby("board")},
            "launches": {str(b): int(g["request_id"].nunique()) for b, g in pop.groupby("board")},
            "unmeasured_target_weeks": int((~targets["measured"]).sum()),
            "definition": "measured target weeks (observed or observed_censored) of every request on the board",
        },
        "boards": boards,
        "slices": slices,
        "edge_fixture_status": fixtures,
        "scenario_weights": scenario_weights,
    }


def equal_weight_objective(per_s: dict[str, dict], weights: dict[str, float]) -> tuple[float | None, str]:
    vals = []
    for s, w in weights.items():
        m = per_s.get(s, {}).get("WMAPE")
        if m is None:
            return None, f"{s} WMAPE {per_s.get(s, {}).get('WMAPE_reason') or 'missing'}"
        vals.append(w * m)
    return float(sum(vals)), ""


def _rank(rows: list[dict], scenarios: list[str]) -> None:
    for key in [*scenarios, "objective"]:

        def val(r: dict, key: str = key) -> float | None:
            return r["objective"] if key == "objective" else r["scenarios"][key]["WMAPE"]

        eligible = [r for r in rows if r["ranked_board"] and r["rankable"] and val(r) is not None]
        eligible.sort(key=lambda r: (val(r), r["variant_id"]))
        for i, r in enumerate(eligible, 1):
            r.setdefault("rank", {})[key] = i
        for r in rows:
            r.setdefault("rank", {}).setdefault(key, None)


def _fixture_status(pop: pd.DataFrame, fc: pd.DataFrame, requests: pd.DataFrame) -> list[dict]:
    fx = requests[~requests["ranked"]]
    if fx.empty:
        return []
    joined = fx[["request_id", "scenario", "fixture_kind"]].merge(fc, on="request_id", how="left")
    out = []
    for (kind, vid), grp in joined.groupby(["fixture_kind", "variant_id"], dropna=False):
        reasons = sorted({r for r in grp["reason"].dropna() if r})
        out.append(
            {
                "fixture_kind": kind,
                "variant_id": vid,
                "statuses": grp["status"].value_counts().to_dict(),
                "reasons": reasons[:5],
            }
        )
    return out


def leaderboard_frame(result: dict, resources: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for board, entries in result["boards"].items():
        for e in entries:
            res = resources.get(e["variant_id"], {})
            for s, m in [*e["scenarios"].items(), ("equal_weight", None)]:
                row = {"board": board, "method_id": e["method_id"], "variant_id": e["variant_id"], "scenario": s}
                if m is None:
                    row.update(
                        {
                            "WMAPE": e["objective"],
                            "WMAPE_reason": e["objective_reason"],
                            "rank": e["rank"].get("objective"),
                        }
                    )
                else:
                    row.update(
                        {
                            k: m.get(k)
                            for k in (
                                "WMAPE",
                                "WMAPE_reason",
                                "Bias",
                                "MAE",
                                "actual_total",
                                "forecast_total",
                                "n_obs",
                                "n_launches",
                                "coverage",
                                "n_failed",
                                "n_fallback",
                                "n_all_zero_launches",
                                "all_zero_launch_forecast_units",
                            )
                        }
                    )
                    row["rank"] = e["rank"].get(s)
                row["rankable"] = e["rankable"] and e["ranked_board"]
                row["fit_seconds"] = res.get("fit_seconds")
                row["predict_seconds"] = res.get("predict_seconds")
                row["peak_python_mib"] = res.get("peak_python_mib")
                rows.append(row)
    return pd.DataFrame(rows)
