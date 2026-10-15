"""Interactive metadata wizard: previews real columns and asks the user to confirm every mapping."""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq
import typer

from xferbench.contracts.metadata import (
    CohortSpec,
    DatasetInfo,
    FeatureSpec,
    Metadata,
    PropensitySpec,
    Rights,
    StageWindow,
    TableSource,
    TimeSpec,
)
from xferbench.contracts.tables import TABLES
from xferbench.data.io import read_header
from xferbench.scaffold import DEFAULT_STAGES
from xferbench.util import write_json


def _preview(path: Path, fmt: str, n: int = 3) -> dict[str, list[str]]:
    if fmt == "parquet":
        t = pq.read_table(path).slice(0, n).to_pydict()
        return {k: [str(v) for v in vals] for k, vals in t.items()}
    import csv

    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))[: n + 1]
    header = rows[0] if rows else []
    return {h: [r[i] if i < len(r) else "" for r in rows[1:]] for i, h in enumerate(header)}


def run_wizard(data_dir: Path, out: Path) -> int:
    files = sorted(
        p for p in data_dir.rglob("*") if p.suffix.lower() in (".csv", ".parquet") and "_synthetic_truth" not in p.parts
    )
    if not files:
        typer.secho(f"no .csv or .parquet files under {data_dir}", fg=typer.colors.RED)
        return 1
    typer.echo("Files found:")
    for i, f in enumerate(files, 1):
        typer.echo(f"  [{i}] {f.relative_to(data_dir)}")
    base = out.resolve().parent
    tables: dict[str, TableSource] = {}
    shares: list[str] = []
    for name, spec in TABLES.items():
        req = "required" if spec.required_table else "optional, Enter to skip"
        typer.echo(f"\nLogical table '{name}' ({req}): {spec.description}")
        default = next((str(i) for i, f in enumerate(files, 1) if f.stem == name), "")
        choice = typer.prompt("  file number", default=default, show_default=bool(default))
        if not choice.strip():
            if spec.required_table:
                typer.secho("  a required table cannot be skipped", fg=typer.colors.RED)
                return 1
            continue
        path = files[int(choice) - 1]
        fmt = "parquet" if path.suffix.lower() == ".parquet" else "csv"
        cols = read_header(path, fmt)
        prev = _preview(path, fmt)
        typer.echo("  columns (first values):")
        for c in cols:
            typer.echo(f"    - {c}: {prev.get(c, [])}")
        mapping: dict[str, str] = {}
        for col in spec.columns:
            suggestion = col.name if col.name in cols else ""
            meaning = f"{col.description} [{col.type}{', ' + col.unit if col.unit else ''}]"
            if col.allowed:
                meaning += f" allowed: {list(col.allowed)}"
            ans = typer.prompt(
                f"  source column for '{col.name}' - {meaning}" + ("" if col.required else " (optional, '-' for none)"),
                default=suggestion or ("-" if not col.required else ""),
                show_default=True,
            )
            ans = ans.strip()
            if ans == "-" and not col.required:
                continue
            if ans not in cols:
                typer.secho(f"  '{ans}' is not a column of {path.name}", fg=typer.colors.RED)
                return 1
            if ans != col.name:
                mapping[col.name] = ans
        extra: list[str] = []
        if name == "locations":
            guess = ",".join(c for c in cols if c.startswith("share_"))
            raw = typer.prompt(
                "  demographic share columns (comma-separated, must sum to 1; '-' for none)", default=guess or "-"
            )
            shares = [] if raw.strip() == "-" else [s.strip() for s in raw.split(",") if s.strip()]
        rel = Path(path).resolve()
        try:
            rel_str = str(rel.relative_to(base))
        except ValueError:
            rel_str = str(rel)
        tables[name] = TableSource(path=rel_str, format=fmt, columns=mapping, extra_columns=extra)  # type: ignore[arg-type]

    typer.echo("\nTime semantics")
    tz = typer.prompt("  timezone of all dates", default="America/Los_Angeles")
    week_start = typer.prompt("  week starts on", default="Monday")
    delay = int(typer.prompt("  reporting delay in days (week end -> data available)", default="7"))
    horizon = int(typer.prompt("  forecast horizon in weeks", default="52"))
    typer.echo("\nPropensity P (used by business rules M1/M2)")
    prop = None
    if "origin_features" in tables and typer.confirm(
        "  Is P EXPECTED WEEKLY UNITS PER HOUSEHOLD (not a purchase probability) and season-neutral?", default=False
    ):
        prop = PropensitySpec(feature_name=typer.prompt("  feature_name of P", default="propensity_rate"))
    else:
        typer.echo("  P disabled: M1/M2 will be reported as missing_features.")
    typer.echo("\nCohort origin windows (completed historical launches only)")
    stages = {}
    for s, (a, b) in DEFAULT_STAGES.items():
        stages[s] = StageWindow(
            origin_start=typer.prompt(f"  {s} first origin", default=a),
            origin_end=typer.prompt(f"  {s} last origin", default=b),
        )
    md = Metadata(
        dataset=DatasetInfo(
            id=typer.prompt("\ndataset id", default="my_retail_dataset"),
            version=typer.prompt("dataset version", default="v1"),
        ),
        time=TimeSpec(timezone=tz, week_start=week_start, reporting_delay_days=delay, horizon_weeks=horizon),  # type: ignore[arg-type]
        tables=tables,
        features=FeatureSpec(demographic_share_columns=shares, propensity=prop),
        cohorts=CohortSpec(stages=stages),
        rights=Rights(data_owner=typer.prompt("data owner"), permitted_use=typer.prompt("permitted use")),
    )
    write_json(out, md.model_dump(mode="json"))
    typer.echo(f"\nwrote {out}; checking data and label completeness...")
    return _post_check(out)


def _post_check(md_path: Path) -> int:
    from xferbench.data.io import load_from_metadata_path
    from xferbench.data.issues import DataError
    from xferbench.domains.registry import get_domain

    try:
        ds = load_from_metadata_path(md_path)
    except DataError as exc:
        for i in exc.issues:
            typer.echo(str(i))
        return 1
    dom = get_domain(ds.metadata.domain_plugin)
    issues = dom.validate(ds)
    for i in issues:
        typer.echo(str(i))
    split = dom.build_splits(ds)
    for c in split.checks:
        if c.check == "scored_labels_complete":
            typer.echo(f"  {c.stage}: {'OK' if c.passed else 'NOT SCOREABLE'} - {c.detail}")
    errors = sum(i.severity == "error" for i in issues) + len(split.failed_checks)
    typer.echo(
        "ready for `xferbench split` and `xferbench run`"
        if not errors
        else "fix the errors above; launches without complete actuals need a forecast-only workflow"
    )
    return 1 if errors else 0
