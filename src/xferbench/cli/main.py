"""``xferbench`` command-line interface. Every command uses the same contracts as the Python API."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any, NoReturn

import typer

from xferbench import __version__

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Xfer Benchmark: local benchmark for zero-history item-location weekly forecasting.",
)
synth_app = typer.Typer(no_args_is_help=True, help="Synthetic data.")
metadata_app = typer.Typer(no_args_is_help=True, help="Metadata tools.")
app.add_typer(synth_app, name="synth")
app.add_typer(metadata_app, name="metadata")
harness_app = typer.Typer(no_args_is_help=True, help="Self-improving harness: lessons, proposals, triggers.")
app.add_typer(harness_app, name="harness")

DOCTOR_PROFILES = {
    "core": ["numpy", "pandas", "pyarrow", "pydantic", "typer", "jinja2"],
    "dev": ["pytest", "ruff", "mypy", "build"],
    "boosting": ["lightgbm", "xgboost", "catboost"],
    "neural": ["torch", "gluonts", "neuralforecast", "pytorch_forecasting"],
    "foundation": ["chronos"],
    "intermittent": ["statsforecast"],
    "services": ["nixtla"],
    "distributed": ["pyspark"],
}
TESTED_PYTHON = ("3.11", "3.12", "3.13")


def _fail(msg: str, code: int = 1) -> NoReturn:
    typer.secho(msg, fg=typer.colors.RED, err=True)
    raise typer.Exit(code)


def _resolve_exp_id(exp_id: str) -> str:
    """Map a deprecated experiment id to its new name, telling the CLI user on stderr (always visible)."""
    from xferbench.experiments.workspace import DEPRECATED_ALIASES

    new = DEPRECATED_ALIASES.get(exp_id)
    if new is None:
        return exp_id
    typer.secho(
        f"warning: experiment id {exp_id!r} is deprecated and will be removed; use {new!r}",
        fg=typer.colors.YELLOW,
        err=True,
    )
    return new


def _version_cb(value: bool) -> None:
    if value:
        typer.echo(f"xferbench {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", callback=_version_cb, is_eager=True, help="Show version and exit."
    ),
) -> None:
    """Run `xferbench demo --preset tiny --out ./first-run` for a complete offline example."""


@synth_app.command("generate")
def synth_generate(
    preset: str = typer.Option("tiny", help="tiny | small | stress (stress is large; explicit only)."),
    seed: int = typer.Option(42, help="Random seed (recorded)."),
    format: str = typer.Option("parquet", "--format", help="parquet | csv | both"),
    out: Path = typer.Option(..., help="Output directory (must be empty or absent)."),
) -> None:
    """Generate deterministic synthetic retail data, metadata and a data story."""
    from xferbench.synth.generator import generate
    from xferbench.synth.presets import get_preset

    fmts = {"parquet": ("parquet",), "csv": ("csv",), "both": ("parquet", "csv")}.get(format)
    if fmts is None:
        _fail("--format must be parquet, csv or both", 2)
    _check_out(out)
    if out.exists() and any(out.iterdir()):
        _fail(f"{out} is not empty; choose a new --out")
    try:
        cfg = get_preset(preset, seed)
    except KeyError as exc:
        _fail(str(exc), 2)
    res = generate(cfg, out, fmts)
    rep = res["report"]
    typer.echo(f"Generated preset '{preset}' seed {seed} in {out}")
    for fmt, p in res["metadata"].items():
        typer.echo(f"  metadata ({fmt}): {p}")
    typer.echo(
        f"  dataset hash: {rep['dataset_hash'][fmts[0]]}  csv/parquet equivalent: {rep['csv_parquet_equivalent']}"
    )
    cal = rep["calibration"]
    typer.echo(
        f"  training-period zero fraction: expected {cal['expected_zero_fraction_calibration']:.3f}, "
        f"realized {cal['realized_zero_fraction_calibration']:.3f}"
    )
    typer.echo(f"  data story: {out / 'DATA_STORY.md'}")


@app.command("validate")
def validate_cmd(
    metadata: Path = typer.Option(..., help="Path to metadata.json"),
    out: Path | None = typer.Option(None, help="Write data_quality.json here."),
) -> None:
    """Validate metadata and data against the canonical contract; nonzero exit on errors."""
    from xferbench.contracts.metadata import load_metadata
    from xferbench.data.io import load_dataset
    from xferbench.data.issues import DataError
    from xferbench.domains.registry import get_domain
    from xferbench.util import write_json

    if out:
        _check_out(out)
    try:
        md = load_metadata(metadata)
    except Exception as exc:
        _fail(f"metadata invalid: {exc}")
    try:
        ds = load_dataset(md, metadata.resolve().parent)
    except DataError as exc:
        for i in exc.issues:
            typer.echo(str(i), err=True)
        _fail("data failed to load into the canonical contract")
    domain = get_domain(md.domain_plugin)
    issues = domain.validate(ds)
    for i in issues:
        typer.echo(str(i))
    n_err = sum(i.severity == "error" for i in issues)
    if out:
        write_json(
            out,
            {
                "dataset_hash": ds.content_hash,
                "issues": [i.to_dict() for i in issues],
                "error_count": n_err,
                "profile": domain.data_profile(ds, None),
            },
        )
    typer.echo(
        f"dataset {md.dataset.id} {md.dataset.version} hash {ds.content_hash}: {n_err} errors, "
        f"{sum(i.severity == 'warning' for i in issues)} warnings"
    )
    if n_err:
        raise typer.Exit(1)


@app.command("split")
def split_cmd(metadata: Path = typer.Option(...), out: Path = typer.Option(...)) -> None:
    """Build frozen chronological cohorts with computed label availability and leakage checks."""
    from xferbench.data.io import load_from_metadata_path
    from xferbench.domains.registry import get_domain
    from xferbench.util import write_json

    _check_out(out)
    ds = load_from_metadata_path(metadata)
    split = get_domain(ds.metadata.domain_plugin).build_splits(ds)
    write_json(out, split.model_dump(mode="json"))
    for s, st in split.stages.items():
        typer.echo(f"{s:>10}: {st.counts} fit_cutoff={st.fit_cutoff} fit_launches={len(st.fit_launch_ids)}")
    failed = split.failed_checks
    typer.echo(f"split hash {split.split_hash}; {len(split.checks)} checks, {len(failed)} failed")
    for c in failed[:20]:
        typer.secho(f"  FAILED {c.check} [{c.stage} {c.launch_id or ''}]: {c.detail}", fg=typer.colors.RED)
    if failed:
        raise typer.Exit(1)


@app.command("list-methods")
def list_methods(
    all_: bool = typer.Option(False, "--all", help="Include every registry entry (default: implemented only)."),
    format: str = typer.Option("table", "--format", help="table | json | markdown"),
) -> None:
    """Show the versioned method registry with implementation, execution and eligibility states."""
    from xferbench.models.registry import REGISTRY_VERSION, all_entries, assess

    reps = [assess(e) for e in all_entries()]
    if not all_:
        reps = [r for r in reps if r.implementation_state in ("implemented", "experimental")]
    if format == "json":
        typer.echo(
            json.dumps(
                {"registry_version": REGISTRY_VERSION, "entries": [r.model_dump(mode="json") for r in reps]}, indent=2
            )
        )
        return
    if format == "markdown":
        typer.echo(method_support_markdown(reps, REGISTRY_VERSION))
        return
    typer.echo(f"registry {REGISTRY_VERSION}")
    typer.echo(f"{'method':<20} {'implementation':<16} {'eligibility':<20} {'extra':<12} board / reason")
    for r in reps:
        typer.echo(
            f"{r.method_id:<20} {r.implementation_state:<16} {(r.eligibility_state or 'checked at run'):<20} "
            f"{(r.optional_extra or 'core'):<12} {r.board}{' - ' + r.reason if r.reason else ''}"
        )


def method_support_markdown(reps: list, registry_version: str) -> str:
    lines = [
        "# Method support",
        "",
        f"Generated by `xferbench list-methods --all --format markdown` (registry {registry_version}).",
        "",
        "Registration is not implementation. Three states are tracked separately: `implementation_state` "
        "(implemented / experimental / unimplemented / config_required), `execution_state` (set per run: "
        "success / not_run / not_installed / failed) and `eligibility_state` (compatible / unsupported_history / "
        "missing_features / license_blocked / service_required; for implemented recipes it is checked against "
        "your dataset at run time). Only executed runs produce scores.",
        "",
        "| Method | Name | Board | Identity | Implementation | Eligibility | Extra | Point statistic | Code license "
        "| Weights | Reason / remedy |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in reps:
        why = f"{r.reason} - {r.remedy}" if r.reason else ""
        lines.append(
            f"| `{r.method_id}` | {r.display_name} | {r.board} | {r.identity} | {r.implementation_state} | "
            f"{r.eligibility_state or 'checked at run'} | {r.optional_extra or 'core'} | {r.point_statistic} | "
            f"{r.rights.code_license} | {r.rights.weights} | {why} |"
        )
    return "\n".join(lines) + "\n"


@app.command("doctor")
def doctor(profile: str = typer.Option("core", help=f"One of {sorted(DOCTOR_PROFILES)}")) -> None:
    """Check the environment for a dependency profile without installing anything."""
    import importlib.util
    import platform
    from importlib.metadata import PackageNotFoundError, version

    if profile not in DOCTOR_PROFILES:
        _fail(f"unknown profile '{profile}'; choose from {sorted(DOCTOR_PROFILES)}", 2)
    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    typer.echo(f"xferbench {__version__} on Python {sys.version.split()[0]} ({platform.platform()})")
    typer.echo(f"python {py}: {'tested' if py in TESTED_PYTHON else 'NOT in the tested matrix ' + str(TESTED_PYTHON)}")
    typer.echo(f"virtual environment: {'yes' if sys.prefix != sys.base_prefix else 'NO (not recommended)'}")
    missing = []
    for mod in DOCTOR_PROFILES[profile]:
        if importlib.util.find_spec(mod) is None:
            missing.append(mod)
            typer.echo(f"  [missing] {mod}")
        else:
            dist = {"pytorch_forecasting": "pytorch-forecasting", "chronos": "chronos-forecasting"}.get(mod, mod)
            try:
                v = version(dist)
            except PackageNotFoundError:
                v = "unknown"
            typer.echo(f"  [ok] {mod} {v}")
    typer.echo("network: no network calls are made by xferbench by default")
    if missing:
        typer.echo(
            f"profile '{profile}' incomplete. Install into THIS virtual environment, e.g.\n"
            f'  python -m pip install "<path-to>/xfer_bench-{__version__}-py3-none-any.whl[{profile}]"\n'
            f"Optional extras beyond core are declared but not yet tested (see PROGRESS.md)."
        )
        raise typer.Exit(1)
    typer.echo(f"profile '{profile}' satisfied")


def _check_out(out: Path) -> None:
    """V3-1/V2-1: every command writing run output (run, steps, demo, select, report, compare, fit, forecast,
    synth generate, split, validate --out) refuses an --out inside a git work tree unless git ignores it (outside a repo is fine)."""
    from xferbench.data.classes import DataClassError, check_local_output

    try:
        check_local_output(out)
    except DataClassError:
        _fail(
            f"--out {out} is inside a git work tree and is not ignored by git; run outputs must never be "
            "committable. Use a path under work/ or runs/local/ (gitignored) or outside the repository.",
            2,
        )


def _resolve_data(
    benchmark: str | None, local_data: Path | None, metadata: Path | None, out: Path, data_dir: Path | None
) -> Any:
    import warnings

    from xferbench.data.classes import DataClassError, resolve_source

    _check_out(out)  # before any data is materialised under --out
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            src = resolve_source(benchmark=benchmark, local_data=local_data, metadata=metadata, data_dir=data_dir)
        for w in caught:
            typer.secho(f"warning: {w.message}", fg=typer.colors.YELLOW, err=True)
    except DataClassError as exc:
        _fail(str(exc), 2)
    return src


@app.command("run")
def run_cmd(
    splits: Path = typer.Option(...),
    stage: str = typer.Option(..., help="validation | test"),
    out: Path = typer.Option(...),
    metadata: Path | None = typer.Option(
        None, help="Legacy: path to metadata.json. Outside benchmarks/ it is treated as LOCAL data (warning)."
    ),
    local_data: Path | None = typer.Option(
        None, "--local-data", help="Your own data: path to metadata.json. Results are labeled local."
    ),
    benchmark: str | None = typer.Option(
        None, "--benchmark", help="Benchmark data: id@version (see `xferbench benchmarks`) or BENCHMARK.json path."
    ),
    benchmark_data: Path | None = typer.Option(
        None, "--benchmark-data", help="Directory holding (or receiving) the materialized benchmark data."
    ),
    profile: str = typer.Option("core", help="core | all"),
    methods: str | None = typer.Option(None, help="Comma-separated method IDs (explicit; no substitution)."),
    selection: Path | None = typer.Option(None, help="Frozen selection.json (required for --stage test)."),
    max_seconds: float | None = typer.Option(None, help="Run budget; unfinished requests are marked skipped."),
    no_report: bool = typer.Option(False, "--no-report", help="Skip report.html."),
    tier: str | None = typer.Option(
        None,
        "--tier",
        help="Data tier: synthetic | sample | complete (default: synthetic data -> synthetic, else complete).",
    ),
    allow_research_only: bool = typer.Option(
        False,
        "--allow-research-only",
        help="Opt in to research-only / non-commercial methods (Moirai, TabPFN, POP, TimesFM 3). "
        "Outputs are labeled internal research only.",
    ),
) -> None:
    """Fit and forecast every compatible method on the frozen stage population, then evaluate."""
    from xferbench.orchestration.runner import BenchmarkRunner, RunConfig, RunError

    if stage not in ("validation", "test"):
        _fail("--stage must be validation or test", 2)
    if benchmark is not None and benchmark_data is None:
        _fail("--benchmark needs --benchmark-data DIR", 2)
    src = _resolve_data(benchmark, local_data, metadata, out, benchmark_data)
    cfg = RunConfig(
        metadata_path=src.metadata_path,
        splits_path=splits,
        stage=stage,  # type: ignore[arg-type]
        out=out,
        profile=profile,
        methods=[m.strip() for m in methods.split(",")] if methods else None,
        selection_path=selection,
        max_seconds=max_seconds,
        write_report=not no_report,
        data_label=src.label(),
        allow_research_only=allow_research_only,
        tier=tier,
    )
    if allow_research_only:
        typer.secho("warning: research-only methods enabled; outputs are INTERNAL RESEARCH ONLY", fg="yellow", err=True)
    try:
        res = BenchmarkRunner(cfg, progress=lambda m: typer.echo(f"  {m}")).run()
    except RunError as exc:
        _fail(str(exc), exc.exit_code)
    _print_board(res.out)
    typer.echo(
        f"run {res.manifest['run_id']} status {res.status}; data class {src.data_class}; tier {res.manifest['tier']}; "
        f"outputs in {res.out}"
    )
    if res.exit_code:
        raise typer.Exit(res.exit_code)


@app.command("benchmarks")
def benchmarks_cmd() -> None:
    """List built-in benchmark datasets (versioned, hashed)."""
    from xferbench.data.classes import list_benchmarks

    for b in list_benchmarks():
        typer.echo(b)


def _print_board(run_dir: Path) -> None:
    from xferbench.util import read_json

    metrics = read_json(run_dir / "metrics.json")
    rows = metrics["boards"].get("cold_c0", [])

    def p(v: float | None) -> str:
        return "   N/A" if v is None else f"{v * 100:6.1f}%"

    from xferbench.reports.html import RANKING_HEADING, RANKING_NOTE

    typer.echo(RANKING_HEADING)
    typer.echo(RANKING_NOTE)
    typer.echo(
        f"{'rank':>4} {'variant':<34} {'WMAPE E':>8} {'WMAPE N':>8} {'Bias E':>8} {'Bias N':>8} {'objective':>9}"
    )
    for e in sorted(rows, key=lambda e: (e["rank"]["objective"] is None, e["rank"]["objective"] or 0)):
        s = e["scenarios"]
        typer.echo(
            f"{e['rank']['objective'] or '-':>4} {e['variant_id'][:34]:<34} {p(s['PAIR0-E']['WMAPE']):>8} "
            f"{p(s['PAIR0-N']['WMAPE']):>8} {p(s['PAIR0-E']['Bias']):>8} {p(s['PAIR0-N']['Bias']):>8} "
            f"{p(e['objective']):>9}"
        )


@app.command("select")
def select_cmd(
    validation_run: Path = typer.Option(...), policy: Path | None = typer.Option(None), out: Path = typer.Option(...)
) -> None:
    """Apply a preregistered policy to validation results and freeze selection.json."""
    from xferbench.contracts.selection import SelectionPolicy
    from xferbench.evaluation.selection import SelectionError, select
    from xferbench.util import read_json, write_json

    _check_out(out)
    pol = SelectionPolicy.model_validate(read_json(policy)) if policy else SelectionPolicy()
    try:
        sel = select(validation_run, pol)
    except SelectionError as exc:
        _fail(str(exc))
    vman = validation_run / "run_manifest.json"
    synthetic = bool(read_json(vman).get("synthetic")) if vman.exists() else False
    # V2-1: synthetic selections never carry a recommendation field (interface test, not a ranking)
    write_json(out, sel.model_dump(mode="json", exclude={"recommended", "recommended_reason"} if synthetic else None))
    for f in sel.families:
        typer.echo(f"  {f.method_id:<14} {'selected ' + f.variant_id if f.eligible else 'not selected: ' + f.reason}")
    for r in sel.rejected_variants:
        typer.echo(f"  rejected {r['variant_id']}: {r['reason']}")
    if synthetic:
        typer.echo(f"synthetic interface test: frozen per-family variants; wrote {out}")
    else:
        typer.echo(f"selected on validation: {sel.recommended} ({sel.recommended_reason}); wrote {out}")


@app.command("report")
def report_cmd(run: Path = typer.Option(...), out: Path = typer.Option(...)) -> None:
    """Render the self-contained HTML report (and summary.md) for a run directory."""
    from xferbench.reports.html import write_run_report

    _check_out(out)
    if not (run / "run_manifest.json").exists():
        _fail(f"{run} is not a run directory")
    write_run_report(run, out)
    typer.echo(f"wrote {out}")


@app.command("compare")
def compare_cmd(
    runs: list[Path] = typer.Option(..., help="Two or more run directories."),
    out: Path = typer.Option(...),
    allow_incompatible: bool = typer.Option(
        False, "--allow-incompatible", help="Write an unranked view for mismatched runs."
    ),
) -> None:
    """Compare runs; refuses to rank runs with different data, split, stage, population or metrics."""
    from xferbench.data.tiers import TierMixError
    from xferbench.reports.compare import CompareError, compare_runs

    _check_out(out)
    try:
        res = compare_runs(runs, out, allow_incompatible)
    except TierMixError as exc:  # never overridable, not even with --allow-incompatible
        _fail(str(exc), 2)
    except CompareError as exc:
        _fail(str(exc), 3)
    typer.echo(f"wrote {out} (compatible={res['compatible']}; tier {res['tier']})")


@app.command("init")
def init_cmd(domain: str = typer.Option("retail"), path: Path = typer.Option(...)) -> None:
    """Create a benchmark project folder with metadata and selection-policy templates."""
    from xferbench.contracts.selection import SelectionPolicy
    from xferbench.scaffold import metadata_template
    from xferbench.util import atomic_write_text, write_json

    if domain != "retail":
        _fail("only the 'retail' domain is built in", 2)
    if path.exists() and any(path.iterdir()):
        _fail(f"{path} is not empty")
    (path / "data").mkdir(parents=True, exist_ok=True)
    write_json(path / "metadata.json", metadata_template())
    write_json(path / "selection-policy.json", SelectionPolicy().model_dump(mode="json"))
    atomic_write_text(
        path / "README.txt",
        (
            "Xfer Benchmark project\n\nOutputs go under ./work/ (gitignored); never commit them.\n\n"
            "1. Put your CSV/Parquet tables in ./data (or run: xferbench metadata wizard --data ./data --out ./metadata.json)\n"
            "2. Edit metadata.json: paths, column mappings, time semantics, cohorts, rights.\n"
            "3. xferbench validate --metadata ./metadata.json\n"
            "4. xferbench split --metadata ./metadata.json --out ./work/splits.json\n"
            "5. xferbench run --metadata ./metadata.json --splits ./work/splits.json --profile core --stage validation "
            "--out ./work/validation-run\n"
            "6. xferbench select --validation-run ./work/validation-run --policy ./selection-policy.json --out ./work/selection.json\n"
            "7. xferbench run --metadata ./metadata.json --splits ./work/splits.json --stage test --selection ./work/selection.json "
            "--out ./work/test-run\n"
        ),
    )
    typer.echo(f"initialized {path}")


@metadata_app.command("wizard")
def wizard_cmd(
    data: Path = typer.Option(..., help="Folder containing your CSV/Parquet files."), out: Path = typer.Option(...)
) -> None:
    """Interactively map your files and columns to the canonical tables (asks; never guesses silently)."""
    from xferbench.data.wizard import run_wizard

    code = run_wizard(data, out)
    raise typer.Exit(code)


@app.command("schemas")
def schemas_cmd(out: Path = typer.Option(Path("schemas"), help="Directory for exported JSON schemas.")) -> None:
    """Export JSON schemas for metadata, selection policy and canonical tables."""
    from xferbench.scaffold import export_schemas

    for p in export_schemas(out):
        typer.echo(f"wrote {p}")


def _demo_label(preset: str, seed: int, content_hash: str) -> dict[str, Any]:
    """Demo data is benchmark data: built-in manifest when one matches preset+seed, else an unversioned label."""
    from xferbench.data.classes import DataClassError, load_benchmark_manifest

    try:
        man, _ = load_benchmark_manifest(f"synthetic-{preset}@1.1.0")
    except DataClassError:
        man = None
    if man and man["source"].get("seed") == seed:
        if man["dataset_hash"] and man["dataset_hash"] != content_hash:
            _fail(f"generated data hash {content_hash} != benchmark manifest {man['dataset_hash']}", 2)
        return {
            "data_class": "benchmark",
            "benchmark_id": man["benchmark_id"],
            "benchmark_version": man["version"],
            "benchmark_kind": "synthetic",
        }
    return {
        "data_class": "benchmark",
        "benchmark_id": f"synthetic-{preset}-seed{seed}",
        "benchmark_version": "unversioned",
        "benchmark_kind": "synthetic",
    }


@app.command("steps")
def steps_cmd(
    out: Path = typer.Option(..., help="Output directory (must be empty or absent)."),
    benchmark: str | None = typer.Option(None, "--benchmark", help="Benchmark data id@version or BENCHMARK.json."),
    local_data: Path | None = typer.Option(None, "--local-data", help="Your own data: path to metadata.json."),
    metadata: Path | None = typer.Option(None, help="Legacy metadata path (outside benchmarks/ = local, warning)."),
) -> None:
    """Methods in order, each adding one idea: run the domain's method sequence on validation, freeze each
    method's variant on validation, score the frozen variants on test, and report per-scenario WMAPE/Bias
    and the pairwise comparisons. Methods that need a recipe or a missing extra are listed with their reason."""
    from xferbench.contracts.selection import SelectionPolicy
    from xferbench.data.io import load_from_metadata_path
    from xferbench.domains.registry import get_domain
    from xferbench.evaluation.selection import select
    from xferbench.models.registry import assess, get_entry
    from xferbench.orchestration.runner import BenchmarkRunner, RunConfig, RunError
    from xferbench.util import write_json

    if out.exists() and any(out.iterdir()):
        _fail(f"{out} is not empty; choose a new --out", 2)
    src = _resolve_data(benchmark, local_data, metadata, out, out / "data")
    label = src.label()
    ds = load_from_metadata_path(src.metadata_path)
    domain = get_domain(ds.metadata.domain_plugin)
    order = [m for m, _ in getattr(domain, "method_order", ())] + [
        m for m, _ in getattr(domain, "method_extra_rows", ())
    ]
    if not order:
        _fail(f"domain plugin '{domain.id}' declares no method_order", 2)
    runnable, skipped = [], []
    for mid in order:
        try:
            rep = assess(get_entry(mid), ds)
        except KeyError:
            skipped.append((mid, "not registered"))
            continue
        ok = (
            rep.implementation_state in ("implemented", "experimental")
            and rep.execution_state != "not_installed"
            and rep.eligibility_state == "compatible"
        )
        (runnable.append(mid) if ok else skipped.append((mid, f"{rep.implementation_state}: {rep.reason}")))
    typer.echo(f"data class {src.data_class}; methods to run: {', '.join(runnable)}")
    for mid, why in skipped:
        typer.echo(f"  not run: {mid} ({why})")
    split = domain.build_splits(ds)
    write_json(out / "splits.json", split.model_dump(mode="json"))
    if split.failed_checks:
        _fail("split checks failed")
    policy = SelectionPolicy(max_abs_bias=1e9, min_coverage=1e-9)
    write_json(out / "selection-policy.json", policy.model_dump(mode="json"))
    try:
        val = BenchmarkRunner(
            RunConfig(
                src.metadata_path,
                out / "splits.json",
                "validation",
                out / "validation-run",
                methods=runnable,
                data_label=label,
            )
        ).run()
        sel = select(val.out, policy)
        write_json(out / "selection.json", sel.model_dump(mode="json"))
        test = BenchmarkRunner(
            RunConfig(
                src.metadata_path,
                out / "splits.json",
                "test",
                out / "test-run",
                selection_path=out / "selection.json",
                data_label=label,
            )
        ).run()
    except RunError as exc:
        _fail(str(exc), exc.exit_code)
    _print_board(test.out)
    summary = (test.out / "summary.md").read_text(encoding="utf-8")
    i = summary.find("## Methods in order")
    typer.echo(summary[i:] if i >= 0 else "")
    typer.echo(f"report: {test.out / 'report.html'}")


@app.command("demo")
def demo_cmd(preset: str = typer.Option("tiny"), seed: int = typer.Option(42), out: Path = typer.Option(...)) -> None:
    """Complete offline demo: generate -> validate -> split -> validation run -> select -> test run -> report."""
    from xferbench.contracts.selection import SelectionPolicy
    from xferbench.data.io import load_from_metadata_path
    from xferbench.domains.registry import get_domain
    from xferbench.evaluation.selection import select
    from xferbench.orchestration.runner import BenchmarkRunner, RunConfig, RunError
    from xferbench.synth.generator import generate
    from xferbench.synth.presets import get_preset
    from xferbench.util import atomic_write_text, write_json

    if out.exists() and any(out.iterdir()):
        _fail(f"{out} is not empty; choose a new --out")
    _check_out(out)
    if preset == "stress":
        _fail("the demo does not run the stress preset; use `synth generate --preset stress` explicitly", 2)
    data = out / "data"
    typer.echo(f"[1/7] generating synthetic '{preset}' data (seed {seed}) -> {data}")
    generate(get_preset(preset, seed), data, ("parquet", "csv"))
    md_path = data / "metadata.json"
    typer.echo("[2/7] validating data")
    ds = load_from_metadata_path(md_path)
    domain = get_domain(ds.metadata.domain_plugin)
    issues = domain.validate(ds)
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        _fail("\n".join(str(e) for e in errors))
    typer.echo(f"      {len(issues)} notes, 0 errors; dataset hash {ds.content_hash[:16]}")
    label = _demo_label(preset, seed, ds.content_hash)
    typer.echo(f"      data class: benchmark {label['benchmark_id']}@{label['benchmark_version']}")
    typer.echo("[3/7] building frozen splits")
    split = domain.build_splits(ds)
    write_json(out / "splits.json", split.model_dump(mode="json"))
    if split.failed_checks:
        _fail("split checks failed")
    typer.echo(f"      {len(split.checks)} checks passed; split hash {split.split_hash[:16]}")
    policy = SelectionPolicy()
    write_json(out / "selection-policy.json", policy.model_dump(mode="json"))
    try:
        typer.echo("[4/7] validation run (profile core)")
        val = BenchmarkRunner(
            RunConfig(
                md_path, out / "splits.json", "validation", out / "validation-run", profile="core", data_label=label
            )
        ).run()
        _print_board(val.out)
        typer.echo("[5/7] freezing selection on validation only")
        sel = select(val.out, policy)
        write_json(out / "selection.json", sel.model_dump(mode="json"))
        typer.echo(f"      selected on validation (synthetic interface test, not a ranking): {sel.recommended}")
        typer.echo("[6/7] test run with frozen selection")
        test = BenchmarkRunner(
            RunConfig(
                md_path,
                out / "splits.json",
                "test",
                out / "test-run",
                selection_path=out / "selection.json",
                data_label=label,
            )
        ).run()
        _print_board(test.out)
    except RunError as exc:
        _fail(str(exc), exc.exit_code)
    typer.echo("[7/7] report")
    shutil.copyfile(test.out / "report.html", out / "report.html")
    atomic_write_text(
        out / "README.txt",
        (
            f"Xfer Benchmark demo ({preset}, seed {seed})\n\n"
            f"data + metadata:      {data}/ (metadata.json = Parquet, metadata.csv.json = CSV)\n"
            f"data story:           {data / 'DATA_STORY.md'}\n"
            f"splits:               {out / 'splits.json'}\n"
            f"validation run:       {out / 'validation-run'}/\n"
            f"frozen selection:     {out / 'selection.json'}\n"
            f"test run:             {out / 'test-run'}/\n"
            f"HTML report:          {out / 'report.html'}\n\n"
            "Synthetic results demonstrate software behavior, not real-world model superiority.\n"
        ),
    )
    typer.echo(f"done. Open {out / 'report.html'}")


experiment_app = typer.Typer(
    help="Experiment workspaces (experiments/<id>/): new, list, run, run-all. Synthetic runs are interface tests, "
    "not rankings. Legacy form `xferbench experiment --config C --out O` still works."
)
app.add_typer(experiment_app, name="experiment")


@experiment_app.callback(invoke_without_command=True)
def experiment_cmd(
    ctx: typer.Context,
    config: Path | None = typer.Option(None, help="(legacy) experiments/<name>/config.yaml"),
    out: Path | None = typer.Option(None, help="(legacy) empty output directory (e.g. eval/<name>)."),
    log_lesson: str | None = typer.Option(
        None, "--log-lesson", help="Append a lesson to harness/lessons.jsonl; value = what changed."
    ),
    harness_dir: Path = typer.Option(Path("harness"), "--harness-dir"),
    tier: str | None = typer.Option(
        None,
        "--tier",
        help="Data tier: synthetic | sample | complete (default: the config's tier key, else synthetic).",
    ),
) -> None:
    """Run a config-driven synthetic experiment (interface test, not a ranking); nothing is downloaded."""
    if ctx.invoked_subcommand is not None:
        return
    if config is None or out is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(2)
    from xferbench.experiments.runner import ExperimentError, run_experiment

    try:
        res = run_experiment(config, out, progress=typer.echo, tier=tier)
    except ExperimentError as exc:
        _fail(str(exc), 2)
    _after_experiment(res, out, log_lesson, harness_dir)


def _after_experiment(res: dict[str, Any], out: Path, log_lesson: str | None, harness_dir: Path) -> None:
    for s in res["not_run"]:
        typer.echo(f"  not run: {s['method_id']} ({s['status']}): {s['reason']}")
    if log_lesson:
        from xferbench.harness.core import HarnessError, append_lesson, lesson_from_experiment

        try:
            lesson = lesson_from_experiment(out, Path.cwd(), res["experiment"], log_lesson)
            append_lesson(harness_dir, Path.cwd(), lesson)
        except (HarnessError, ValueError) as exc:
            _fail(f"lesson not logged: {exc}", 2)
        typer.echo(f"lesson appended to {harness_dir / 'lessons.jsonl'}")
    typer.echo(f"data tier: {res.get('tier', 'synthetic')}")
    typer.echo(f"done. Open {out / 'leaderboard.html'} and {out / 'report.html'}")


@experiment_app.command("new")
def experiment_new_cmd(
    name: str = typer.Argument(..., help="New experiment id (lowercase letters, digits, '_')."),
    from_id: str | None = typer.Option(None, "--from", help="Copy config (and extra files) from this experiment."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing experiment folder."),
) -> None:
    """Scaffold experiments/<name>/ with config.yaml and README.md."""
    from xferbench.experiments.runner import ExperimentError
    from xferbench.experiments.workspace import new_experiment

    if from_id:
        from_id = _resolve_exp_id(from_id)
    try:
        dest = new_experiment(name, Path.cwd(), from_id, force)
    except ExperimentError as exc:
        _fail(str(exc), 2)
    typer.echo(f"created {dest}/ (config.yaml, README.md). Edit them, then: xferbench experiment run {name}")


_ALLOW_RO_HELP = "Include research-only / licence-gated reproductions (excluded by default)."


@experiment_app.command("list")
def experiment_list_cmd(
    allow_research_only: bool = typer.Option(False, "--allow-research-only", help=_ALLOW_RO_HELP),
) -> None:
    """List experiments with the data and models each one uses."""
    from xferbench.experiments.workspace import list_experiments

    infos = list_experiments(Path.cwd(), allow_research_only=allow_research_only)
    if not infos:
        typer.echo("no experiments/*/config.yaml found (run from the repository root)")
    for i in infos:
        flag = f" | NAME: {i.name_problem}" if i.name_problem else ""
        if i.error:
            typer.echo(f"{i.id}: INVALID CONFIG - {i.error}{flag}")
            continue
        if i.kind == "reproduction":
            typer.echo(f"{i.id}: RESEARCH ONLY, licence-gated reproduction | data {i.preset} (not included){flag}")
            continue
        opt = f" | optional: {', '.join(i.optional_methods)}" if i.optional_methods else ""
        ndz = " | NOT A DAY-ZERO RESULT" if not i.day_zero else ""
        typer.echo(f"{i.id}: data synthetic/{i.preset} | models: {', '.join(i.methods)}{opt}{ndz}{flag}")


@experiment_app.command("run")
def experiment_run_cmd(
    exp_id: str = typer.Argument(..., help="Experiment id (folder under experiments/)."),
    log_lesson: str | None = typer.Option(None, "--log-lesson"),
    harness_dir: Path = typer.Option(Path("harness"), "--harness-dir"),
    allow_research_only: bool = typer.Option(False, "--allow-research-only", help=_ALLOW_RO_HELP),
    tier: str | None = typer.Option(
        None,
        "--tier",
        help="Data tier: synthetic | sample | complete (default: the config's tier key, else synthetic).",
    ),
    out: Path | None = typer.Option(None, "--out", help="Output folder (default eval/<id>__<tier>/, git-ignored)."),
) -> None:
    """Run one experiment into eval/<id>__<tier>/ (git-ignored). The tier is printed and written to every output."""
    from xferbench.experiments.runner import ExperimentError
    from xferbench.experiments.workspace import run_one
    from xferbench.repro.visuelle import ReproError

    exp_id = _resolve_exp_id(exp_id)
    try:
        res = run_one(
            exp_id, Path.cwd(), progress=typer.echo, allow_research_only=allow_research_only, tier=tier, out=out
        )
    except ExperimentError as exc:
        _fail(str(exc), 2)
    except ReproError as exc:
        _fail(f"{exc} (report written under eval/{exp_id}__<tier>/)", 3)
    if res.get("usage_tag") == "research_only":  # pragma: no cover - needs licensed data + local GTM
        typer.echo(f"RESEARCH ONLY report: {Path(res['_out']) / 'report.md'}")
        return
    _after_experiment(res, Path(res["_out"]), log_lesson, harness_dir)


@experiment_app.command("run-all")
def experiment_run_all_cmd(
    only: list[str] = typer.Option([], "--only", help="Restrict to these ids (repeatable)."),
    allow_research_only: bool = typer.Option(False, "--allow-research-only", help=_ALLOW_RO_HELP),
    tier: str | None = typer.Option(
        None,
        "--tier",
        help="Data tier: synthetic | sample | complete (default: the config's tier key, else synthetic).",
    ),
) -> None:
    """Run every experiment at one data tier, continue past failures, print a status table (no rankings).
    Exit 1 if any failed; exit 2 if rows of different tiers would be mixed."""
    from xferbench.data.tiers import TierMixError
    from xferbench.experiments.workspace import run_all, summary_table

    try:
        rows = run_all(
            Path.cwd(), only or None, progress=typer.echo, allow_research_only=allow_research_only, tier=tier
        )
    except TierMixError as exc:
        _fail(f"{exc} Pass --tier or --only to select one tier.", 2)
    try:
        typer.echo(summary_table(rows))
    except TierMixError as exc:
        _fail(str(exc), 2)
    if any(r["status"] != "ok" for r in rows):
        raise typer.Exit(1)


@app.command("fit")
def fit_cmd(
    metadata: Path = typer.Option(..., help="metadata.json of the training data."),
    splits: Path = typer.Option(..., help="splits.json for that data."),
    method: str = typer.Option(..., help="Method id, e.g. B3 or M4.lightgbm."),
    out: Path = typer.Option(..., help="New, empty model directory (artifact.json + manifest.json)."),
    selection: Path | None = typer.Option(None, help="Frozen selection.json: fit exactly the selected variant."),
    stage: str = typer.Option("test", help="Fit on the labels available at this stage's fit cutoff."),
    seed: int = typer.Option(42),
    json_logs: bool = typer.Option(True, "--json-logs/--plain-logs"),
) -> None:
    """Fit one method variant and save a versioned artifact with a manifest (production path)."""
    from xferbench import api

    _check_out(out)
    api.configure_logging(json_logs=json_logs)
    try:
        model = api.fit(metadata, splits, method, selection_path=selection, stage=stage, seed=seed)
        api.save(model, out)
    except api.ApiError as exc:
        _fail(str(exc), exc.exit_code)
    typer.echo(f"saved {out / 'artifact.json'} and {out / 'manifest.json'} ({model.artifact.variant_id})")


@app.command("forecast")
def forecast_cmd(
    model: Path = typer.Option(..., help="Model directory written by `xferbench fit`."),
    metadata: Path = typer.Option(..., help="metadata.json of the data holding the new launches."),
    splits: Path = typer.Option(..., help="splits.json naming the new launches (stage below)."),
    out: Path = typer.Option(..., help="Output parquet file for the forecasts."),
    stage: str = typer.Option("test", help="Stage whose launches are forecast."),
    json_logs: bool = typer.Option(True, "--json-logs/--plain-logs"),
) -> None:
    """Forecast new launches from a frozen artifact. No actuals needed; the evaluator is never called.
    Exit codes: 0 ok, 1 error, 2 usage, 3 method rejected, 5 artifact mismatch, 6 input schema mismatch."""
    from xferbench import api
    from xferbench.util import atomic_write_parquet, write_json

    _check_out(out)
    api.configure_logging(json_logs=json_logs)
    if out.exists():
        _fail(f"{out} exists; forecasts are append-only (choose a new --out)", 2)
    try:
        m = api.load(model)
        fc = api.predict(m, metadata, splits, stage)
    except api.ApiError as exc:
        _fail(str(exc), exc.exit_code)
    atomic_write_parquet(out, fc)
    write_json(
        out.with_suffix(".manifest.json"),
        {
            "model_manifest": m.manifest,
            "rows": len(fc),
            "metadata": str(metadata),
            "stage": stage,
            "libraries": api.library_versions(),
        },
    )
    typer.echo(f"wrote {len(fc)} forecast rows to {out}")


@harness_app.command("triggers")
def harness_triggers_cmd(harness_dir: Path = typer.Option(Path("harness"), "--harness-dir")) -> None:
    """List due revisit triggers (new paper, regression, failed run, stale review). Exit 1 if any are due."""
    from xferbench.harness.core import due_triggers

    due = due_triggers(harness_dir)
    for d in due:
        typer.echo(f"  {d['trigger']}: {d['detail']}")
    typer.echo(f"{len(due)} trigger(s) due")
    if due:
        raise typer.Exit(1)


@harness_app.command("check")
def harness_check_cmd(
    proposal: Path = typer.Option(...), harness_dir: Path = typer.Option(Path("harness"), "--harness-dir")
) -> None:
    """Check a proposal against the guardrails without adopting it."""
    from xferbench.harness.core import HarnessError, check_proposal, load_proposal

    try:
        check_proposal(load_proposal(proposal), Path.cwd(), harness_dir)
    except HarnessError as exc:
        _fail(str(exc), 2)
    typer.echo("proposal passes guardrails and has an approved review")


@harness_app.command("apply")
def harness_apply_cmd(
    proposal: Path = typer.Option(...), harness_dir: Path = typer.Option(Path("harness"), "--harness-dir")
) -> None:
    """Adopt an approved proposal: bump BEST_PRACTICES version and log it in CHANGELOG.md."""
    from xferbench.harness.core import HarnessError, apply_proposal

    try:
        dest = apply_proposal(proposal, Path.cwd(), harness_dir)
    except HarnessError as exc:
        _fail(str(exc), 2)
    typer.echo(f"adopted; wrote {dest}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
