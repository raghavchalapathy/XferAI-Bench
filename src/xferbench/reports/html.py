"""Self-contained HTML report and Markdown executive summary for one run directory."""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, PackageLoader, select_autoescape

from xferbench import __version__
from xferbench.reports.charts import grouped_hbar, line_chart, scatter
from xferbench.util import atomic_write_text, read_json

SCENARIOS = ("PAIR0-E", "PAIR0-N")
HORIZONS = ["h01-04", "h05-13", "h14-26", "h27-52"]

GLOSSARY = {
    "WMAPE": "Weighted mean absolute percentage error: sum(|forecast - actual|) / sum(actual) over the fixed "
    "eligible population. Lower is better. Undefined (N/A) when total actual is zero.",
    "Bias": "Signed bias: sum(forecast) / sum(actual) - 1. Positive = overforecast. Undefined when total actual is 0.",
    "Coverage": "Share of eligible target weeks with a valid (success or declared fallback) forecast. Methods below "
    "100% are unrankable; metrics are never computed on a convenient subset.",
    "Equal-scenario objective": "0.5 x WMAPE(PAIR0-E) + 0.5 x WMAPE(PAIR0-N). Both scenarios are always shown "
    "separately; the objective is not a pooled average.",
    "PAIR0-E": "Existing item at an established FPG; zero own-pair history; other items sell at the FPG.",
    "PAIR0-N": "Existing item at an entirely new FPG; no transactions at the FPG before origin.",
    "Fallback": "A declared, visible substitute path inside a recipe (e.g. B2 -> B1 when no comparable donor exists).",
    "Eligible weeks": "Measured target weeks (observed or stockout-censored). Missing weeks are excluded for all "
    "methods alike; never-offered weeks are not targets.",
}


def _env() -> Environment:
    env = Environment(
        loader=PackageLoader("xferbench.reports", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["pct"] = lambda v: "N/A" if v is None or pd.isna(v) else f"{v * 100:.1f}%"
    env.filters["num"] = lambda v, d=2: "N/A" if v is None or pd.isna(v) else f"{v:,.{d}f}"
    env.filters["short"] = lambda h: (h or "")[:12]
    return env


def _csv_data_uri(df: pd.DataFrame) -> str:
    return "data:text/csv;charset=utf-8," + urllib.parse.quote(df.to_csv(index=False))


def _best_per_family(entries: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for e in entries:
        cur = best.get(e["method_id"])
        key = (e["objective"] is None, e["objective"] if e["objective"] is not None else 0, e["variant_id"])
        if cur is None or key < (cur["objective"] is None, cur["objective"] or 0, cur["variant_id"]):
            best[e["method_id"]] = e
    return sorted(best.values(), key=lambda e: (e["objective"] is None, e["objective"] or 0, e["variant_id"]))


def build_context(run_dir: Path) -> dict[str, Any]:
    manifest = read_json(run_dir / "run_manifest.json")
    metrics = read_json(run_dir / "metrics.json")
    support = read_json(run_dir / "method_support.json")["entries"]
    resources = read_json(run_dir / "resources.json")
    dq = read_json(run_dir / "data_quality.json")
    lb = pd.read_csv(run_dir / "leaderboard.csv")
    slices = pd.read_csv(run_dir / "slices.csv") if (run_dir / "slices.csv").stat().st_size > 1 else pd.DataFrame()
    failures = (
        pd.read_csv(run_dir / "failures.csv") if (run_dir / "failures.csv").stat().st_size > 1 else pd.DataFrame()
    )

    main = metrics["boards"].get("cold_c0", [])
    ranked = sorted([e for e in main if e["rankable"]], key=lambda e: (e["objective"], e["variant_id"]))
    unrankable = [e for e in main if not e["rankable"]]
    fam = _best_per_family(main)
    labels = [e["variant_id"] for e in ranked + unrankable]
    rows = ranked + unrankable
    wmape_chart = grouped_hbar(
        "WMAPE by scenario (lower is better)",
        labels,
        {s: [e["scenarios"][s]["WMAPE"] for e in rows] for s in SCENARIOS},
    )
    bias_chart = grouped_hbar(
        "Signed Bias by scenario (0 = unbiased)",
        labels,
        {s: [e["scenarios"][s]["Bias"] for e in rows] for s in SCENARIOS},
        diverging=True,
    )
    hz_series: dict[str, list[float | None]] = {}
    if len(slices):
        hz = slices[(slices["dimension"] == "horizon_bucket")]
        for e in fam[:4]:
            for s in SCENARIOS:
                sub = hz[(hz["variant_id"] == e["variant_id"]) & (hz["scenario"] == s)].set_index("value")
                hz_series[f"{e['variant_id']} {s}"] = [
                    None if (h not in sub.index or pd.isna(sub.loc[h, "WMAPE"])) else float(sub.loc[h, "WMAPE"])
                    for h in HORIZONS
                ]
    horizon_chart = line_chart("WMAPE by horizon bucket (best variant per family, top 4)", HORIZONS, hz_series)
    res = resources["variants"]
    pts = [
        (
            e["variant_id"],
            (res[e["variant_id"]]["fit_seconds"] + res[e["variant_id"]]["predict_seconds"]),
            e["objective"],
        )
        for e in ranked
        if e["variant_id"] in res
    ]
    resource_chart = scatter(
        "Equal-scenario WMAPE vs measured fit+predict time", pts, "fit + predict seconds (log)", "equal-scenario WMAPE"
    )

    def slice_table(dim: str) -> list[dict]:
        if not len(slices):
            return []
        keep = {e["variant_id"] for e in fam}
        sub = slices[(slices["dimension"] == dim) & slices["variant_id"].isin(keep)]
        return sub.sort_values(["variant_id", "scenario", "value"]).to_dict("records")

    excluded = [s for s in support if s["execution_state"] != "success"]
    stage_profile = [p for p in dq["profile"].get("target_zero_fractions", []) if p["stage"] == manifest["stage"]]
    sel = None
    if manifest["stage"] == "test" and manifest.get("selection"):
        sel = manifest["selection"]
    return {
        "m": manifest,
        "metrics": metrics,
        "ranked": ranked,
        "unrankable": unrankable,
        "families": fam,
        "wmape_chart": wmape_chart,
        "bias_chart": bias_chart,
        "horizon_chart": horizon_chart,
        "resource_chart": resource_chart,
        "resources": res,
        "process": resources,
        "category": slice_table("category"),
        "region": slice_table("region"),
        "intermittency": slice_table("intermittency"),
        "availability": slice_table("availability"),
        "horizon": slice_table("horizon_bucket"),
        "excluded": excluded,
        "support": support,
        "fixtures": metrics.get("edge_fixture_status", []),
        "fixture_board": metrics["boards"].get("edge_fixtures", []),
        "failures": failures.to_dict("records") if len(failures) else [],
        "dq": dq,
        "dq_counts": {
            sev: sum(1 for i in dq["issues"] if i["severity"] == sev) for sev in ("error", "warning", "info")
        },
        "stage_profile": stage_profile,
        "selection": sel,
        "glossary": GLOSSARY,
        "version": __version__,
        "lb_uri": _csv_data_uri(lb),
        "slices_uri": _csv_data_uri(slices) if len(slices) else None,
        "support_uri": _csv_data_uri(pd.DataFrame([{k: v for k, v in s.items() if k != "rights"} for s in support])),
        "scenarios": SCENARIOS,
    }


def write_run_report(run_dir: Path, out: Path) -> Path:
    ctx = build_context(run_dir)
    html = _env().get_template("report.html.j2").render(**ctx)
    atomic_write_text(out, html)
    atomic_write_text(run_dir / "summary.md", executive_summary(ctx))
    return out


def _p(v: float | None) -> str:
    return "N/A" if v is None else f"{v * 100:.1f}%"


def executive_summary(ctx: dict[str, Any]) -> str:
    m = ctx["m"]
    lines = [
        f"# Xfer Benchmark - {m['stage']} run `{m['run_id']}`",
        "",
        f"Dataset `{m['dataset_id']}` {m['dataset_version']} (hash {m['dataset_hash'][:12]}), split "
        f"{m['split_hash'][:12]}, status **{m['status']}**.",
        "",
    ]
    if m.get("synthetic"):
        lines += [
            "> Synthetic data: these results demonstrate software behavior, not real-world model superiority.",
            "",
        ]
    lines += [
        f"Population (cold_c0 board): {m['population']['launches'].get('cold_c0', 0)} launches, "
        f"{m['population']['eligible_weeks'].get('cold_c0', 0)} eligible weeks.",
        "",
        "| Rank | Variant | WMAPE E | WMAPE N | Bias E | Bias N | Objective |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in ctx["ranked"]:
        s = e["scenarios"]
        lines.append(
            f"| {e['rank']['objective']} | {e['variant_id']} | {_p(s['PAIR0-E']['WMAPE'])} | "
            f"{_p(s['PAIR0-N']['WMAPE'])} | {_p(s['PAIR0-E']['Bias'])} | {_p(s['PAIR0-N']['Bias'])} | "
            f"{_p(e['objective'])} |"
        )
    for e in ctx["unrankable"]:
        lines.append(f"| - | {e['variant_id']} (unrankable: {e['objective_reason']}) | | | | | |")
    lines += ["", f"Methods not executed: {len(ctx['excluded'])} registry entries (see report for reasons).", ""]
    if ctx["selection"]:
        lines += [
            f"Frozen selection from validation run `{ctx['selection']['validation_run_id']}`; "
            f"recommended: `{ctx['selection']['recommended']}`.",
            "",
        ]
    lines += ["Limitations: " + " ".join(m["limitations"]), ""]
    return "\n".join(lines)
