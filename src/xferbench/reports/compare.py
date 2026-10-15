"""Compare runs side by side; ranking across runs requires identical comparability keys."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, select_autoescape

from xferbench.util import atomic_write_text, read_json

KEYS = ("dataset_hash", "split_hash", "stage", "horizon_weeks", "population_hash", "metric_definitions")

TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline';">
<title>Xfer Benchmark comparison</title>
<style>body{background:#1b1c22;color:#ecebf4;font:15px/1.5 system-ui,sans-serif;margin:0}main{max-width:1100px;margin:auto;padding:16px}
h1{color:#a78bfa}h2{color:#a78bfa;border-left:4px solid #f472d0;padding-left:8px}.tw{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.86rem}th,td{padding:6px 8px;border-bottom:1px solid #3a3b46;text-align:left}
th{background:#2c2d37;color:#b3b0c2}td.n{text-align:right}.bad{color:#fca5a5}.ok{color:#86efac}code{background:#2c2d37;padding:1px 4px}</style>
</head><body><main><h1>Run comparison</h1>
{% if compatible %}<p class="ok">All runs share dataset, split, stage, horizon, eligible population and metric definitions: rows are directly comparable.</p>
{% else %}<p class="bad">Runs are NOT comparable ({{ mismatches|join('; ') }}). Values are shown side by side for inspection only and are not ranked.</p>{% endif %}
<h2>Runs</h2><div class="tw"><table><tr><th>Run</th><th>Stage</th><th>Dataset</th><th>Split</th><th>Population</th></tr>
{% for r in runs %}<tr><td><code>{{ r.run_id }}</code></td><td>{{ r.stage }}</td><td><code>{{ r.dataset_hash[:12] }}</code></td><td><code>{{ r.split_hash[:12] }}</code></td><td><code>{{ r.population_hash[:12] }}</code></td></tr>{% endfor %}</table></div>
<h2>Equal-scenario objective by variant</h2><div class="tw"><table><tr><th>Variant</th>{% for r in runs %}<th class="n">{{ r.run_id }}</th>{% endfor %}</tr>
{% for v in variants %}<tr><td><code>{{ v }}</code></td>{% for r in runs %}<td class="n">{{ fmt(r.objectives.get(v)) }}</td>{% endfor %}</tr>{% endfor %}</table></div>
</main></body></html>"""


class CompareError(Exception):
    pass


def _summary(run: Path) -> dict:
    m = read_json(run / "run_manifest.json")
    metrics = read_json(run / "metrics.json")
    objectives = {e["variant_id"]: e["objective"] for e in metrics["boards"].get("cold_c0", []) if e["rankable"]}
    return {
        "run_id": m["run_id"],
        "stage": m["stage"],
        "dataset_hash": m["dataset_hash"],
        "split_hash": m["split_hash"],
        "horizon_weeks": m["horizon_weeks"],
        "population_hash": m["population"]["hashes"].get("cold_c0", ""),
        "metric_definitions": m["metric_definitions"],
        "objectives": objectives,
    }


def compare_runs(runs: list[Path], out: Path, allow_incompatible: bool = False) -> dict:
    if len(runs) < 2:
        raise CompareError("compare needs at least two run directories")
    summaries = [_summary(r) for r in runs]
    mismatches = [k for k in KEYS if len({repr(s[k]) for s in summaries}) > 1]
    if mismatches and not allow_incompatible:
        raise CompareError(
            f"runs are not comparable: differing {mismatches}. Use --allow-incompatible to write an "
            "unranked side-by-side view."
        )
    variants = sorted({v for s in summaries for v in s["objectives"]})
    env = Environment(autoescape=select_autoescape(default_for_string=True, default=True))
    html = env.from_string(TEMPLATE).render(
        runs=summaries,
        variants=variants,
        compatible=not mismatches,
        mismatches=mismatches,
        fmt=lambda v: "N/A" if v is None else f"{v * 100:.1f}%",
    )
    atomic_write_text(out, html)
    return {"compatible": not mismatches, "mismatches": mismatches}
