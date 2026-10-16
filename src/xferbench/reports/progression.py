"""'Methods in order, each adding one idea': per-scenario WMAPE/Bias table and pairwise deltas.

Generic: the order and comparisons come from the domain plugin's optional ``method_order`` and
``method_comparisons`` attributes; a plugin without them gets no section.
"""

from __future__ import annotations

from typing import Any


def _best(entries: list[dict], method_id: str) -> dict | None:
    cand = [e for e in entries if e["method_id"] == method_id]
    if not cand:
        return None
    ok = [e for e in cand if e.get("objective") is not None]
    return min(ok, key=lambda e: (e["objective"], e["variant_id"])) if ok else cand[0]


def build(
    entries: list[dict],
    support: list[dict],
    scenarios: tuple[str, ...],
    order: tuple[tuple[str, str], ...],
    comparisons: tuple[tuple[str, str, str], ...],
    extra_rows: tuple[tuple[str, str], ...] = (),
) -> dict[str, Any] | None:
    if not order:
        return None
    sup = {s["method_id"]: s for s in support}
    steps = []
    by_id: dict[str, dict] = {}
    rows_in = [(m, i, False) for m, i in order] + [(m, i, True) for m, i in extra_rows]
    for mid, idea, extra in rows_in:
        e = _best(entries, mid)
        s = sup.get(mid, {})
        row: dict[str, Any] = {"method_id": mid, "idea": idea, "extra": extra}
        if e is not None:
            row |= {
                "ran": True,
                "variant_id": e["variant_id"],
                "metrics": {
                    sc: {"WMAPE": e["scenarios"][sc]["WMAPE"], "Bias": e["scenarios"][sc]["Bias"]} for sc in scenarios
                },
            }
            by_id[mid] = row
        else:
            row |= {
                "ran": False,
                "state": s.get("implementation_state", "not registered"),
                "execution_state": s.get("execution_state"),
                "reason": s.get("reason") or "not run",
                "remedy": s.get("remedy", ""),
            }
        steps.append(row)
    comps = []
    for cand, ref, note in comparisons:
        c, r = by_id.get(cand), by_id.get(ref)
        row = {"candidate": cand, "reference": ref, "note": note}
        if c is None or r is None:
            missing = cand if c is None else ref
            row["status"] = "N/A"
            row["reason"] = f"{missing} did not run"
        else:
            row["status"] = "ok"
            row["delta"] = {
                sc: {
                    m: (
                        None
                        if c["metrics"][sc][m] is None or r["metrics"][sc][m] is None
                        else c["metrics"][sc][m] - r["metrics"][sc][m]
                    )
                    for m in ("WMAPE", "Bias")
                }
                for sc in scenarios
            }
        comps.append(row)
    return {
        "title": "Methods in order, each adding one idea",
        "scenarios": list(scenarios),
        "steps": steps,
        "comparisons": comps,
        "delta_rule": "delta = candidate - reference (WMAPE: negative is better; Bias: closer to 0 is better)",
    }


def to_markdown(p: dict[str, Any]) -> str:
    def pct(v: float | None) -> str:
        return "N/A" if v is None else f"{v * 100:.1f}%"

    sc = p["scenarios"]
    lines = [
        f"## {p['title']}",
        "",
        "| Method | Idea | " + " | ".join(f"WMAPE {s} | Bias {s}" for s in sc) + " |",
        "|---|---|" + "---|---|" * len(sc),
    ]
    for r in p["steps"]:
        if r["ran"]:
            cells = " | ".join(f"{pct(r['metrics'][s]['WMAPE'])} | {pct(r['metrics'][s]['Bias'])}" for s in sc)
            lines.append(f"| {r['variant_id']} | {r['idea']} | {cells} |")
        else:
            lines.append(f"| {r['method_id']} | {r['idea']} | {r['state']}: {r['reason']} |" + " |" * (2 * len(sc) - 1))
    lines += ["", f"Comparisons ({p['delta_rule']}):", ""]
    for c in p["comparisons"]:
        if c["status"] != "ok":
            lines.append(f"- {c['candidate']} vs {c['reference']}: N/A ({c['reason']}; {c['note']})")
        else:
            d = "; ".join(f"{s}: dWMAPE {pct(c['delta'][s]['WMAPE'])}, dBias {pct(c['delta'][s]['Bias'])}" for s in sc)
            lines.append(f"- {c['candidate']} vs {c['reference']} ({c['note']}): {d}")
    return "\n".join(lines) + "\n"
