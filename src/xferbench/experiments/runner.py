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
LOCAL_LABEL = (
    "LOCAL DATA ({tier} tier) - results on your own data. Not a benchmark result and not a ranking; "
    "rows are listed alphabetically."
)


def label_for(tier: str) -> str:
    return LABEL if tier == "synthetic" else LOCAL_LABEL.format(tier=tier)


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_tiered(path: Path, tier: str | None = None) -> tuple[dict[str, Any], str]:
    """Base config.yaml plus the optional overlay configs/<tier>.yaml (deep-merged). Tier: argument, else the
    config's ``tier`` key, else 'synthetic'. Switching tiers is config-only: same experiment, same code."""
    from xferbench.data.tiers import TIERS

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tier = tier or str(raw.get("tier", "synthetic"))
    if tier not in TIERS:
        raise ExperimentError(f"{path}: data tier must be one of {list(TIERS)}, got {tier!r}")
    overlay = path.parent / "configs" / f"{tier}.yaml"
    if overlay.is_file():
        over = yaml.safe_load(overlay.read_text(encoding="utf-8")) or {}
        if "id" in over and over["id"] != raw.get("id"):
            raise ExperimentError(f"{overlay}: a tier overlay may not change the experiment id")
        raw = _deep_merge(raw, over)
    raw["tier"] = tier
    return raw, tier


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
    tier: str = "synthetic"  # data tier: synthetic | sample | complete (configs/<tier>.yaml overlay)
    metadata: Path | None = None  # sample/complete tiers: metadata.json of your own (local) data

    @classmethod
    def load(cls, path: Path, tier: str | None = None) -> ExperimentConfig:
        raw, tier = load_tiered(path, tier)
        data = raw.get("data", {}) or {}
        metadata: Path | None = None
        if tier == "synthetic":
            if data.get("flavour", "synthetic") != "synthetic":
                raise ExperimentError("tier 'synthetic' runs on generated data only (data.flavour: synthetic)")
        else:
            if not data.get("metadata"):
                raise ExperimentError(
                    f"{path}: tier {tier!r} needs data.metadata: path to the metadata.json of your own data "
                    f"(set it in {path.parent / 'configs' / (tier + '.yaml')}; keep the data under local/, never in git)"
                )
            metadata = Path(str(data["metadata"]))
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
            tier=tier,
            metadata=metadata,
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


def _rows(run_dir: Path, tier: str = "synthetic") -> list[dict[str, Any]]:
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
                "tier": tier,
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
    from xferbench.data.tiers import TIER_TEXT

    e = html.escape
    data_line = (
        f"Data: synthetic preset <code>{e(cfg.preset)}</code>, seed {cfg.seed}."
        if cfg.tier == "synthetic"
        else f"Data: your own data (<code>{e(cfg.metadata.name if cfg.metadata else '')}</code>), data class local."
    )
    body = "".join(
        f"<tr><td>{e(r['tier'])}</td><td>{e(r['variant_id'])}</td><td>{_pct(r['wmape_e'])}</td>"
        f"<td>{_pct(r['wmape_n'])}</td><td>{_pct(r['bias_e'])}</td><td>{_pct(r['bias_n'])}</td>"
        f"<td>{_pct(r['objective'])}</td></tr>"
        for r in rows
    )
    skip = "".join(
        f"<li><b>{e(s['method_id'])}</b>: {e(s['status'])} - {e(s['reason'])}. Fix: {e(s['remedy'])}</li>"
        for s in skipped
    )
    ndz = f'<p class="label"><b>{e(NOT_DAY_ZERO)}</b> {e(cfg.not_day_zero)}</p>' if cfg.not_day_zero else ""
    papers = "".join(
        f'<li>{e(p.get("citation", ""))} <a href="{e(p.get("url", ""))}">{e(p.get("url", ""))}</a></li>'
        for p in cfg.papers
    )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>{e(cfg.title)} - leaderboard</title>
<style>body{{font-family:system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem}}
table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:right}}
td:nth-child(-n+2),th:nth-child(-n+2){{text-align:left}}.label{{background:#fff3cd;padding:.6rem;border:1px solid #e0c060}}</style>
<h1>{e(cfg.title)}</h1><p class="label"><b>{e(label_for(cfg.tier))}</b> Rows are listed alphabetically, not by score.</p>{ndz}
<p id="tier">Data tier: <b>{e(cfg.tier)}</b> ({e(TIER_TEXT[cfg.tier])}).</p>
<p>Test stage, board cold_c0. Objective = 0.5 x WMAPE(PAIR0-E) + 0.5 x WMAPE(PAIR0-N), from the protected evaluator.
{data_line}</p>
<table><tr><th>tier</th><th>variant</th><th>WMAPE E</th><th>WMAPE N</th><th>Bias E</th><th>Bias N</th><th>objective</th></tr>{body}</table>
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


def run_experiment(config_path: Path, out: Path, progress: Any = print, tier: str | None = None) -> dict[str, Any]:
    from xferbench.contracts.selection import SelectionPolicy
    from xferbench.data.io import load_from_metadata_path
    from xferbench.domains.registry import get_domain
    from xferbench.evaluation.selection import select
    from xferbench.orchestration.runner import BenchmarkRunner, RunConfig
    from xferbench.synth.generator import generate
    from xferbench.synth.presets import get_preset

    cfg = ExperimentConfig.load(config_path, tier)
    if out.exists() and any(out.iterdir()):
        raise ExperimentError(f"{out} is not empty; choose a new --out")
    check_output_dir(out)
    runnable, skipped = _availability(cfg.methods + cfg.optional_methods)
    if not runnable:
        raise ExperimentError("no runnable method; install the extras listed in the config")
    if cfg.tier == "synthetic":
        label: dict[str, Any] = {
            "data_class": "benchmark",
            "benchmark_id": f"synthetic-{cfg.preset}-seed{cfg.seed}",
            "benchmark_version": "unversioned",
            "benchmark_kind": "synthetic",
        }
        data = out / "data"
        progress(f"[1/6] tier synthetic: synthetic data '{cfg.preset}' seed {cfg.seed} -> {data}")
        generate(get_preset(cfg.preset, cfg.seed), data, ("parquet",))
        md = data / "metadata.json"
    else:
        assert cfg.metadata is not None
        md = cfg.metadata
        if not md.is_file():
            raise ExperimentError(f"tier {cfg.tier!r}: data.metadata {md} not found")
        label = {"data_class": "local", "benchmark_id": None, "benchmark_version": None, "benchmark_kind": None}
        progress(f"[1/6] tier {cfg.tier}: your own data {md} (data class local)")
        out.mkdir(parents=True, exist_ok=True)
    ds = load_from_metadata_path(md)
    from xferbench.data.tiers import TierError, resolve_tier

    try:
        resolve_tier(cfg.tier, bool(ds.metadata.dataset.synthetic))
    except TierError as exc:
        raise ExperimentError(str(exc)) from exc
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
        RunConfig(
            md, out / "splits.json", "validation", out / "validation-run", methods=runnable, data_label=label,
            tier=cfg.tier,
        )
    ).run()  # fmt: skip
    progress("[4/6] frozen selection (validation only)")
    sel = select(val.out, SelectionPolicy())
    work = out / WORK_DIR  # private working path: needed to freeze the test run; never published
    sel_path = work / "selection.json"
    write_json(
        sel_path,
        {
            "data_class": "synthetic" if cfg.tier == "synthetic" else "local",
            "tier": cfg.tier,
            "label": SELECTION_LABEL
            if cfg.tier == "synthetic"
            else SELECTION_LABEL.replace("synthetic interface test", f"{cfg.tier} tier"),
            "not_a_ranking": True,
            "publish": False,
            "selection": sel.model_dump(mode="json"),
        },
    )
    progress("[5/6] test run with the frozen selection")
    test = BenchmarkRunner(
        RunConfig(
            md, out / "splits.json", "test", out / "test-run", selection_path=sel_path, data_label=label, tier=cfg.tier
        )
    ).run()
    progress("[6/6] report, results.json, leaderboard.html, SUMMARY.md")
    rows = _rows(test.out, cfg.tier)
    parity = _scalable_parity(ds, split, test.out, cfg)
    shutil.copyfile(test.out / "report.html", out / "report.html")
    results = {
        "experiment": cfg.id,
        "label": label_for(cfg.tier),
        "tier": cfg.tier,
        "objective": "0.5*WMAPE(PAIR0-E) + 0.5*WMAPE(PAIR0-N)",
        "data": {"flavour": "synthetic", "preset": cfg.preset, "seed": cfg.seed, "dataset_hash": ds.content_hash}
        if cfg.tier == "synthetic"
        else {"data_class": "local", "metadata": md.name, "dataset_hash": ds.content_hash},
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
    from xferbench.data.tiers import TIER_TEXT

    lines = [
        f"# {cfg.title}",
        "",
        f"**{label_for(cfg.tier)}**",
        "",
        f"Data tier: **{cfg.tier}** ({TIER_TEXT[cfg.tier]}).",
        "",
    ]
    if cfg.not_day_zero:
        lines += [f"**{NOT_DAY_ZERO}** {cfg.not_day_zero}", ""]
    lines += ["Rows are listed alphabetically by variant, not by score.", ""]
    lines += ["| tier | variant | WMAPE E | WMAPE N | objective |", "|---|---|---|---|---|"]
    lines += [
        f"| {r['tier']} | {r['variant_id']} | {_pct(r['wmape_e'])} | {_pct(r['wmape_n'])} | {_pct(r['objective'])} |"
        for r in rows
    ]
    lines += ["", "Not run (config_required): " + (", ".join(s["method_id"] for s in skipped) or "none"), ""]
    lines += [f"- {s['method_id']}: {s['reason']}. Fix: {s['remedy']}" for s in skipped if s.get("remedy")]
    if any(s.get("remedy") for s in skipped):
        lines.append("")
    atomic_write_text(out / "SUMMARY.md", "\n".join(lines))
    return results
