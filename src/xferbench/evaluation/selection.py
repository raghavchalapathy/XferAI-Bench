"""Apply a preregistered selection policy to VALIDATION results and freeze the choice."""

from __future__ import annotations

from pathlib import Path

from xferbench.contracts.selection import SelectedVariant, Selection, SelectionPolicy
from xferbench.util import hash_obj, read_json, sha256_file, utc_now_iso


class SelectionError(Exception):
    pass


def _check(entry: dict, policy: SelectionPolicy, seconds: float | None) -> tuple[bool, str]:
    for s in policy.scenario_weights:
        m = entry["scenarios"].get(s)
        if m is None:
            return False, f"{s}: no results"
        if m["coverage"] is None or m["coverage"] < policy.min_coverage:
            return False, f"{s}: coverage {m['coverage']} below required {policy.min_coverage:.0%}"
        if m["WMAPE"] is None:
            return False, f"{s}: WMAPE {m['WMAPE_reason']} (rule: {policy.undefined_metric_rule})"
        if m["Bias"] is None or abs(m["Bias"]) > policy.max_abs_bias:
            shown = "undefined" if m["Bias"] is None else f"{m['Bias']:+.1%}"
            return False, f"{s}: Bias {shown} outside symmetric limit +/-{policy.max_abs_bias:.0%}"
    if policy.max_total_seconds is not None and seconds is not None and seconds > policy.max_total_seconds:
        return False, f"resource: {seconds:.2f}s > {policy.max_total_seconds}s"
    return True, ""


def select(validation_run: Path, policy: SelectionPolicy) -> Selection:
    manifest_path = validation_run / "run_manifest.json"
    if not manifest_path.exists():
        raise SelectionError(f"{validation_run} is not a run directory (run_manifest.json missing)")
    manifest = read_json(manifest_path)
    if manifest.get("stage") != "validation":
        raise SelectionError(f"selection must use a validation run; got stage '{manifest.get('stage')}'")
    if manifest.get("status") not in ("complete",):
        raise SelectionError(f"validation run status is '{manifest.get('status')}'; selection needs a complete run")
    metrics = read_json(validation_run / "metrics.json")
    resources = read_json(validation_run / "resources.json")["variants"]
    entries = metrics["boards"].get(policy.board, [])
    if not entries:
        raise SelectionError(f"no results on board '{policy.board}'")
    if policy.scenario_weights != metrics["scenario_weights"]:
        raise SelectionError("policy scenario weights differ from the run's declared selection weights")

    configs = {v["variant_id"]: v["config"] for v in manifest["variants"]}
    by_method: dict[str, list[tuple[float, dict]]] = {}
    rejected = []
    for e in entries:
        res = resources.get(e["variant_id"], {})
        seconds = (res.get("fit_seconds") or 0) + (res.get("predict_seconds") or 0)
        ok, why = _check(e, policy, seconds)
        if not ok:
            rejected.append({"variant_id": e["variant_id"], "reason": why})
            by_method.setdefault(e["method_id"], [])
            continue
        weighted = sum(w * e["scenarios"][s]["WMAPE"] for s, w in policy.scenario_weights.items())
        by_method.setdefault(e["method_id"], []).append((weighted, e))

    families = []
    for method_id in sorted(by_method):
        cands = sorted(by_method[method_id], key=lambda t: (t[0], t[1]["variant_id"]))
        if not cands:
            mine = [
                r
                for r in rejected
                if any(e["variant_id"] == r["variant_id"] and e["method_id"] == method_id for e in entries)
            ]
            detail = "; ".join(f"{r['variant_id']}: {r['reason']}" for r in mine)
            families.append(
                SelectedVariant(
                    method_id=method_id,
                    variant_id="",
                    config={},
                    objective=None,
                    per_scenario={},
                    eligible=False,
                    reason=f"no variant satisfied the policy ({detail})",
                )
            )
            continue
        obj, e = cands[0]
        families.append(
            SelectedVariant(
                method_id=method_id,
                variant_id=e["variant_id"],
                config=configs.get(e["variant_id"], {}),
                objective=obj,
                eligible=True,
                reason="lowest equal-scenario validation WMAPE within constraints",
                per_scenario={
                    s: {k: e["scenarios"][s][k] for k in ("WMAPE", "Bias", "coverage")} for s in policy.scenario_weights
                },
            )
        )
    eligible = [f for f in families if f.eligible]
    best = min(eligible, key=lambda f: (f.objective, f.variant_id)) if eligible else None
    return Selection(
        created_at=utc_now_iso(),
        policy=policy,
        policy_hash=hash_obj(policy.model_dump(mode="json")),
        validation_run_id=manifest["run_id"],
        validation_manifest_hash=sha256_file(manifest_path),
        dataset_hash=manifest["dataset_hash"],
        split_hash=manifest["split_hash"],
        selection_cutoff=manifest["selection_cutoff"],
        families=families,
        recommended=best.variant_id if best else None,
        recommended_reason="lowest equal-scenario validation objective among eligible variants"
        if best
        else "no variant satisfied the policy in both scenarios",
        rejected_variants=rejected,
    )
