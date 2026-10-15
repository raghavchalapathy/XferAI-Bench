"""``xferbench`` command-line interface. Every command uses the same contracts as the Python API."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import NoReturn

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
    from xferbench.methods.registry import REGISTRY_VERSION, all_entries, assess

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


@app.command("run")
def run_cmd(
    metadata: Path = typer.Option(...),
    splits: Path = typer.Option(...),
    stage: str = typer.Option(..., help="validation | test"),
    out: Path = typer.Option(...),
    profile: str = typer.Option("core", help="core | all"),
    methods: str | None = typer.Option(None, help="Comma-separated method IDs (explicit; no substitution)."),
    selection: Path | None = typer.Option(None, help="Frozen selection.json (required for --stage test)."),
    max_seconds: float | None = typer.Option(None, help="Run budget; unfinished requests are marked skipped."),
    no_report: bool = typer.Option(False, "--no-report", help="Skip report.html."),
) -> None:
    """Fit and forecast every compatible method on the frozen stage population, then evaluate."""
    from xferbench.orchestration.runner import BenchmarkRunner, RunConfig, RunError

    if stage not in ("validation", "test"):
        _fail("--stage must be validation or test", 2)
    cfg = RunConfig(
        metadata_path=metadata,
        splits_path=splits,
        stage=stage,  # type: ignore[arg-type]
        out=out,
        profile=profile,
        methods=[m.strip() for m in methods.split(",")] if methods else None,
        selection_path=selection,
        max_seconds=max_seconds,
        write_report=not no_report,
    )
    try:
        res = BenchmarkRunner(cfg, progress=lambda m: typer.echo(f"  {m}")).run()
    except RunError as exc:
        _fail(str(exc), exc.exit_code)
    _print_board(res.out)
    typer.echo(f"run {res.manifest['run_id']} status {res.status}; outputs in {res.out}")
    if res.exit_code:
        raise typer.Exit(res.exit_code)


def _print_board(run_dir: Path) -> None:
    from xferbench.util import read_json

    metrics = read_json(run_dir / "metrics.json")
    rows = metrics["boards"].get("cold_c0", [])

    def p(v: float | None) -> str:
        return "   N/A" if v is None else f"{v * 100:6.1f}%"

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

    pol = SelectionPolicy.model_validate(read_json(policy)) if policy else SelectionPolicy()
    try:
        sel = select(validation_run, pol)
    except SelectionError as exc:
        _fail(str(exc))
    write_json(out, sel.model_dump(mode="json"))
    for f in sel.families:
        typer.echo(f"  {f.method_id:<14} {'selected ' + f.variant_id if f.eligible else 'not selected: ' + f.reason}")
    for r in sel.rejected_variants:
        typer.echo(f"  rejected {r['variant_id']}: {r['reason']}")
    typer.echo(f"recommended: {sel.recommended} ({sel.recommended_reason}); wrote {out}")


@app.command("report")
def report_cmd(run: Path = typer.Option(...), out: Path = typer.Option(...)) -> None:
    """Render the self-contained HTML report (and summary.md) for a run directory."""
    from xferbench.reports.html import write_run_report

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
    from xferbench.reports.compare import CompareError, compare_runs

    try:
        res = compare_runs(runs, out, allow_incompatible)
    except CompareError as exc:
        _fail(str(exc), 3)
    typer.echo(f"wrote {out} (compatible={res['compatible']})")


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
            "Xfer Benchmark project\n\n"
            "1. Put your CSV/Parquet tables in ./data (or run: xferbench metadata wizard --data ./data --out ./metadata.json)\n"
            "2. Edit metadata.json: paths, column mappings, time semantics, cohorts, rights.\n"
            "3. xferbench validate --metadata ./metadata.json\n"
            "4. xferbench split --metadata ./metadata.json --out ./splits.json\n"
            "5. xferbench run --metadata ./metadata.json --splits ./splits.json --profile core --stage validation "
            "--out ./validation-run\n"
            "6. xferbench select --validation-run ./validation-run --policy ./selection-policy.json --out ./selection.json\n"
            "7. xferbench run --metadata ./metadata.json --splits ./splits.json --stage test --selection ./selection.json "
            "--out ./test-run\n"
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
            RunConfig(md_path, out / "splits.json", "validation", out / "validation-run", profile="core")
        ).run()
        _print_board(val.out)
        typer.echo("[5/7] freezing selection on validation only")
        sel = select(val.out, policy)
        write_json(out / "selection.json", sel.model_dump(mode="json"))
        typer.echo(f"      recommended: {sel.recommended}")
        typer.echo("[6/7] test run with frozen selection")
        test = BenchmarkRunner(
            RunConfig(md_path, out / "splits.json", "test", out / "test-run", selection_path=out / "selection.json")
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
