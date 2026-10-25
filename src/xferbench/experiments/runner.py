"""Run one experiment from a YAML config: synthetic data -> validate -> splits -> validation run -> frozen
selection -> test run -> report, results.json, leaderboard.html and SUMMARY.md.

Methods whose optional extra or weights are absent are not run; they are listed as ``config_required`` with the
remedy. Nothing is downloaded. Scores come from the protected evaluator (0.5*WMAPE(PAIR0-E) + 0.5*WMAPE(PAIR0-N)).
"""

from __future__ import annotations

import html
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from xferbench.util import atomic_write_text, read_json, write_json

LABEL = "SYNTHETIC INTERFACE TEST - not a ranking. Synthetic data only checks the software, not which method is better."


NOT_DAY_ZERO = "NOT A DAY-ZERO RESULT."
BACKENDS = {"polars", "spark"}


class ExperimentError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExperimentConfig:
    id: str
    title: str
    papers: list[dict[str, str]]
    preset: str
    seed: int
    methods: list[str]
    optional_methods: list[str]
    not_day_zero: str | None = None
    backend: str = "polars"  # runtime.backend: polars | spark (config-only switch; same code)
    mode: str = "local"  # runtime.mode: local | cluster
    master: str = "local[2]"  # runtime.master: Spark master URL (cluster mode: e.g. yarn or spark://host:7077)

    @classmethod
    def load(cls, path: Path) -> ExperimentConfig:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data = raw.get("data", {})
        if data.get("flavour", "synthetic") != "synthetic":
            raise ExperimentError("public experiments run on synthetic data only (data.flavour: synthetic)")
        if not raw.get("methods"):
            raise ExperimentError(f"{path}: 'methods' must list at least one method id")
        not_day_zero = raw.get("not_day_zero")
        if any(m.startswith("FM.") for m in [*raw["methods"], *raw.get("optional_methods", [])]) and not not_day_zero:
            raise ExperimentError(f"{path}: zero-shot/foundation-model experiments must set 'not_day_zero: <reason>'")
        rt = raw.get("runtime", {}) or {}
        backend, mode = str(rt.get("backend", "polars")), str(rt.get("mode", "local"))
        if backend not in BACKENDS:
            raise ExperimentError(f"{path}: runtime.backend must be one of {sorted(BACKENDS)}, got {backend!r}")
        if mode not in ("local", "cluster"):
            raise ExperimentError(f"{path}: runtime.mode must be 'local' or 'cluster', got {mode!r}")
        if mode == "cluster" and backend != "spark":
            raise ExperimentError(f"{path}: runtime.mode 'cluster' requires runtime.backend 'spark'")
        return cls(
            backend=backend,
            mode=mode,
            master=str(rt.get("master", "local[2]" if mode == "local" else "yarn")),
            id=str(raw["id"]),
            title=str(raw.get("title", raw["id"])),
            papers=list(raw.get("papers", [])),
            preset=str(data.get("preset", "tiny")),
            seed=int(data.get("seed", 42)),
            methods=[str(m) for m in raw["methods"]],
            optional_methods=[str(m) for m in raw.get("optional_methods", [])],
            not_day_zero=str(not_day_zero) if not_day_zero else None,
        )


def _availability(method_ids: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    from xferbench.models.registry import assess, get_entry

    runnable, skipped = [], []
    for mid in method_ids:
        rep = assess(get_entry(mid))
        if rep.execution_state == "not_installed" or rep.implementation_state not in ("implemented", "experimental"):
            skipped.append({"method_id": mid, "status": "config_required", "reason": rep.reason, "remedy": rep.remedy})
        else:
            runnable.append(mid)
    return runnable, skipped


def _rows(run_dir: Path) -> list[dict[str, Any]]:
    rows = read_json(run_dir / "metrics.json")["boards"].get("cold_c0", [])
    out = []
    for e in rows:
        s = e["scenarios"]
        out.append(
            {
                "variant_id": e["variant_id"],
                "method_id": e["method_id"],
                "wmape_e": s["PAIR0-E"]["WMAPE"],
                "wmape_n": s["PAIR0-N"]["WMAPE"],
                "bias_e": s["PAIR0-E"]["Bias"],
                "bias_n": s["PAIR0-N"]["Bias"],
                "objective": e["objective"],
            }
        )
    # synthetic: no ordering by score and no numbering (F-4); rows are listed alphabetically by variant id
    return sorted(out, key=lambda r: str(r["variant_id"]))


def _pct(v: float | None) -> str:
    return "N/A" if v is None else f"{v * 100:.1f}%"


WORK_DIR = "_work"
SELECTION_LABEL = (
    "synthetic interface test, not a ranking: private working file used only to freeze the test run; do not publish"
)


def leaderboard_html(cfg: ExperimentConfig, rows: list[dict[str, Any]], skipped: list[dict[str, str]]) -> str:
    e = html.escape
    body = "".join(
        f"<tr><td>{e(r['variant_id'])}</td><td>{_pct(r['wmape_e'])}</td>"
        f"<td>{_pct(r['wmape_n'])}</td><td>{_pct(r['bias_e'])}</td><td>{_pct(r['bias_n'])}</td>"
        f"<td>{_pct(r['objective'])}</td></tr>"
        for r in rows
    )
    skip = "".join(
        f"<li><b>{e(s['method_id'])}</b>: {e(s['status'])} - {e(s['reason'])}. {e(s['remedy'])}</li>" for s in skipped
    )
    ndz = f'<p class="label"><b>{e(NOT_DAY_ZERO)}</b> {e(cfg.not_day_zero)}</p>' if cfg.not_day_zero else ""
    papers = "".join(
        f'<li>{e(p.get("citation", ""))} <a href="{e(p.get("url", ""))}">{e(p.get("url", ""))}</a></li>'
        for p in cfg.papers
    )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>{e(cfg.title)} - leaderboard</title>
<style>body{{font-family:system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem}}
table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:right}}
td:nth-child(1),th:nth-child(1){{text-align:left}}.label{{background:#fff3cd;padding:.6rem;border:1px solid #e0c060}}</style>
<h1>{e(cfg.title)}</h1><p class="label"><b>{e(LABEL)}</b> Rows are listed alphabetically, not by score.</p>{ndz}
<p>Test stage, board cold_c0. Objective = 0.5 x WMAPE(PAIR0-E) + 0.5 x WMAPE(PAIR0-N), from the protected evaluator.
Data: synthetic preset <code>{e(cfg.preset)}</code>, seed {cfg.seed}.</p>
<table><tr><th>variant</th><th>WMAPE E</th><th>WMAPE N</th><th>Bias E</th><th>Bias N</th><th>objective</th></tr>{body}</table>
<h2>Not run (config_required)</h2><ul>{skip or "<li>none</li>"}</ul><h2>Papers</h2><ul>{papers}</ul></html>
"""


def _scalable_parity(ds: Any, split: Any, run_dir: Path, cfg: ExperimentConfig | None = None) -> dict[str, Any]:
    """Cross-check the scalable partial-sum objective (Polars lazy or Spark, per runtime.backend) against the
    protected evaluator's metrics.json."""
    import polars as pl

    from xferbench.domains.registry import get_domain
    from xferbench.scalable_eval.core import finalize, partial_sums_polars, partial_sums_spark

    backend = cfg.backend if cfg else "polars"
    domain = get_domain(ds.metadata.domain_plugin)
    requests = domain.requests(ds, split, "test")
    targets = domain.targets(ds, requests)
    w = ds.metadata.cohorts.selection_weights
    if backend == "spark":
        from pyspark.sql import SparkSession

        assert cfg is not None
        spark = (
            SparkSession.builder.master(cfg.master)
            .appName(f"xferbench-{cfg.id}")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )
        try:
            fc_s = spark.read.parquet(str(run_dir / "forecasts.parquet"))
            got = finalize(
                *partial_sums_spark(
                    fc_s,
                    spark.createDataFrame(targets),
                    spark.createDataFrame(requests[["request_id", "scenario", "board"]]),
                ),
                w,
            )
        finally:
            if cfg.mode == "local":
                spark.stop()
    else:
        got = finalize(*partial_sums_polars(pl.scan_parquet(run_dir / "forecasts.parquet"), targets, requests), w)
    ref = read_json(run_dir / "metrics.json")["boards"]
    worst = 0.0
    for board, rows in ref.items():
        mine = {r["variant_id"]: r["objective"] for r in got.get(board, [])}
        for r in rows:
            a, b = r["objective"], mine.get(r["variant_id"])
            if (a is None) != (b is None):
                return {"engine": backend, "match": False, "max_abs_diff": None}
            if a is not None and b is not None:
                worst = max(worst, abs(a - b))
    return {"engine": backend, "match": worst <= 1e-9, "max_abs_diff": worst}


def check_output_dir(out: Path) -> None:
    """V3-1: refuse an --out inside a git work tree unless git ignores it (outside any repo is fine)."""
    from xferbench.data.classes import DataClassError, check_local_output

    try:
        check_local_output(out)
    except DataClassError as e:
        raise ExperimentError(
            f"--out {out} is inside a git work tree and is not ignored by git; experiment outputs "
            "(test-run/, validation-run/, run_manifest.json) must never be committable. "
            "Use eval/<id> (gitignored) or a path outside the repository."
        ) from e


def run_experiment(config_path: Path, out: Path, progress: Any = print) -> dict[str, Any]:
    from xferbench.contracts.selection import SelectionPolicy
    from xferbench.data.io import load_from_metadata_path
    from xferbench.domains.registry import get_domain
    from xferbench.evaluation.selection import select
    from xferbench.orchestration.runner import BenchmarkRunner, RunConfig
    from xferbench.synth.generator import generate
    from xferbench.synth.presets import get_preset

    cfg = ExperimentConfig.load(config_path)
    if out.exists() and any(out.iterdir()):
        raise ExperimentError(f"{out} is not empty; choose a new --out")
    check_output_dir(out)
    runnable, skipped = _availability(cfg.methods + cfg.optional_methods)
    if not runnable:
        raise ExperimentError("no runnable method; install the extras listed in the config")
    label = {
        "data_class": "benchmark",
        "benchmark_id": f"synthetic-{cfg.preset}-seed{cfg.seed}",
        "benchmark_version": "unversioned",
        "benchmark_kind": "synthetic",
    }
    data = out / "data"
    progress(f"[1/6] synthetic data '{cfg.preset}' seed {cfg.seed} -> {data}")
    generate(get_preset(cfg.preset, cfg.seed), data, ("parquet",))
    md = data / "metadata.json"
    ds = load_from_metadata_path(md)
    domain = get_domain(ds.metadata.domain_plugin)
    errors = [i for i in domain.validate(ds) if i.severity == "error"]
    if errors:
        raise ExperimentError("\n".join(str(e) for e in errors))
    progress("[2/6] frozen splits")
    split = domain.build_splits(ds)
    if split.failed_checks:
        raise ExperimentError("split checks failed")
    write_json(out / "splits.json", split.model_dump(mode="json"))
    progress(f"[3/6] validation run: {', '.join(runnable)}")
    val = BenchmarkRunner(
        RunConfig(md, out / "splits.json", "validation", out / "validation-run", methods=runnable, data_label=label)
    ).run()
    progress("[4/6] frozen selection (validation only)")
    sel = select(val.out, SelectionPolicy())
    work = out / WORK_DIR  # private working path: needed to freeze the test run; never published
    sel_path = work / "selection.json"
    write_json(
        sel_path,
        {
            "data_class": "synthetic",
            "label": SELECTION_LABEL,
            "not_a_ranking": True,
            "publish": False,
            "selection": sel.model_dump(mode="json"),
        },
    )
    progress("[5/6] test run with the frozen selection")
    test = BenchmarkRunner(
        RunConfig(md, out / "splits.json", "test", out / "test-run", selection_path=sel_path, data_label=label)
    ).run()
    progress("[6/6] report, results.json, leaderboard.html, SUMMARY.md")
    rows = _rows(test.out)
    parity = _scalable_parity(ds, split, test.out, cfg)
    shutil.copyfile(test.out / "report.html", out / "report.html")
    results = {
        "experiment": cfg.id,
        "label": LABEL,
        "objective": "0.5*WMAPE(PAIR0-E) + 0.5*WMAPE(PAIR0-N)",
        "data": {"flavour": "synthetic", "preset": cfg.preset, "seed": cfg.seed, "dataset_hash": ds.content_hash},
        "split_hash": split.split_hash,
        "runtime": {"backend": cfg.backend, "mode": cfg.mode},
        "day_zero_result": cfg.not_day_zero is None,
        "not_day_zero": cfg.not_day_zero,
        "row_order": "alphabetical by variant_id (not a ranking)",
        "test_rows": rows,
        "not_run": skipped,
        "scalable_eval_parity": parity,
        "papers": cfg.papers,
    }
    write_json(out / "results.json", results)
    atomic_write_text(out / "leaderboard.html", leaderboard_html(cfg, rows, skipped))
    lines = [f"# {cfg.title}", "", f"**{LABEL}**", ""]
    if cfg.not_day_zero:
        lines += [f"**{NOT_DAY_ZERO}** {cfg.not_day_zero}", ""]
    lines += ["Rows are listed alphabetically by variant, not by score.", ""]
    lines += ["| variant | WMAPE E | WMAPE N | objective |", "|---|---|---|---|"]
    lines += [
        f"| {r['variant_id']} | {_pct(r['wmape_e'])} | {_pct(r['wmape_n'])} | {_pct(r['objective'])} |" for r in rows
    ]
    lines += ["", "Not run (config_required): " + (", ".join(s["method_id"] for s in skipped) or "none"), ""]
    atomic_write_text(out / "SUMMARY.md", "\n".join(lines))
    return results
