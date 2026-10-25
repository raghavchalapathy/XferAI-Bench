"""Experiment workspaces: one standard, self-contained folder per experiment.

Layout (``experiments/<id>/``)::

    config.yaml      # the only thing that changes between data flavours / backends / local vs cluster
    README.md        # paper + citation, data used, models used, how to run
    runs/<UTC timestamp>/   # outputs of `xferbench experiment run <id>` (git-ignored, never published)

``eval/`` keeps generated, git-ignored outputs of ad-hoc runs; ``results/`` holds shareable reports that a human
copies there after Scientist verification and Reviewer review. Synthetic runs are interface tests, never rankings.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from xferbench.experiments.runner import ExperimentConfig, ExperimentError, run_experiment

# Owner naming rule (2026-10-24): exp<NN>_<dataset>_<method>, lowercase [a-z0-9_]; dataset = data.flavour.
NAME_RE = re.compile(r"^exp[0-9]{2}_[a-z0-9]+_[a-z0-9_]*[a-z0-9]$")
NAME_RULE = "exp<NN>_<dataset>_<method> (lowercase letters, digits and '_'; e.g. exp04_synthetic_lightgbm)"
# Renamed 2026-10-24; old ids still resolve with a deprecation warning.
DEPRECATED_ALIASES = {
    "exp01_m5_lightgbm_analogs": "exp01_synthetic_lightgbm_analogs",
    "exp02_chronos_zero_shot": "exp02_synthetic_chronos_zero_shot",
    "repro_visuelle_gtm": "exp03_visuelle_gtm",
}
TEMPLATE_README = """# {id}

**Synthetic interface test, not a ranking.** Outputs check the software, not which method is better.

- **Paper(s):** {papers}
- **Data:** synthetic preset `{preset}`, seed {seed} (`data.flavour: synthetic`), data tier `synthetic`.
- **Data tiers:** `synthetic` (default), `sample` or `complete`. Switch with `--tier` or the `tier:` key; the
  overlays `configs/sample.yaml` and `configs/complete.yaml` set `data.metadata` to your own data (keep it under
  `local/`, never in git). Same experiment, same code; only the config changes.
- **Models:** {methods}{optional}
- **Run:** `xferbench experiment run {id}` -> `eval/{id}__<tier>/` (git-ignored)
"""

TIER_OVERLAY = """# Data tier '{tier}': {text}. Deep-merged over ../config.yaml by `xferbench experiment run {id} --tier {tier}`.
# Point data.metadata at the metadata.json of your own data (docs/GETTING_STARTED.md Step 2).
# Keep that data in data/{tier}_data/ (git-ignored); never commit it. Results go to eval/{id}__{tier}/, labelled local.
data:
  metadata: ""  # e.g. data/{tier}_data/metadata/metadata.json
"""


@dataclass(frozen=True)
class ExperimentInfo:
    id: str
    path: Path
    title: str
    methods: list[str]
    optional_methods: list[str]
    preset: str
    day_zero: bool
    error: str | None = None
    kind: str = "synthetic"
    usage_tag: str = "interface_test"
    name_problem: str | None = None


def _uses_own_data(exp_dir: Path) -> bool:
    """True if a sample/complete overlay points at the user's own data (then <dataset> names that data)."""
    for t in ("sample", "complete"):
        f = exp_dir / "configs" / f"{t}.yaml"
        if f.is_file():
            over = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            if str((over.get("data") or {}).get("metadata") or "").strip():
                return True
    return False


def name_problem(folder: str, flavour: str | None) -> str | None:
    """Why a folder name breaks the naming rule (None if it follows it). Used to flag entries in `list`."""
    if len(folder) > 64 or not NAME_RE.fullmatch(folder):
        return f"name does not follow {NAME_RULE}"
    if flavour and folder.split("_")[1] != flavour:
        return f"dataset part {folder.split('_')[1]!r} does not match data.flavour {flavour!r}"
    return None


def _raw(cfg_path: Path) -> dict[str, Any]:
    try:
        d = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    return d if isinstance(d, dict) else {}


def is_research_only(raw: dict[str, Any]) -> bool:
    return raw.get("kind") == "reproduction" or raw.get("usage_tag") == "research_only"


def experiments_root(root: Path | None = None) -> Path:
    return (root or Path.cwd()) / "experiments"


def validate_name(name: str) -> str:
    if len(name) > 64 or not NAME_RE.fullmatch(name):
        raise ExperimentError(f"invalid experiment name {name!r}: use {NAME_RULE}, at most 64 characters")
    return name


def list_experiments(root: Path | None = None, allow_research_only: bool = False) -> list[ExperimentInfo]:
    """Experiments in alphabetical order. Research-only / licence-gated reproductions only when opted in."""
    out = []
    for cfg_path in sorted(experiments_root(root).glob("*/config.yaml")):
        d = cfg_path.parent
        raw = _raw(cfg_path)
        if is_research_only(raw):
            if allow_research_only:
                out.append(
                    ExperimentInfo(
                        str(raw.get("id", d.name)), d, str(raw.get("title", "")), [], [],
                        str((raw.get("data") or {}).get("flavour", "")), False,
                        kind="reproduction", usage_tag="research_only",
                        name_problem=name_problem(d.name, (raw.get("data") or {}).get("flavour")),
                    )
                )  # fmt: skip
            continue
        try:
            c = ExperimentConfig.load(cfg_path)
            out.append(
                ExperimentInfo(
                    c.id, d, c.title, c.methods, c.optional_methods, c.preset, c.not_day_zero is None,
                    name_problem=name_problem(d.name, None if _uses_own_data(d) else (raw.get("data") or {}).get("flavour", "synthetic")),
                )
            )  # fmt: skip
        except (ExperimentError, KeyError, yaml.YAMLError) as exc:
            out.append(
                ExperimentInfo(
                    d.name, d, "", [], [], "", False, error=str(exc), name_problem=name_problem(d.name, None)
                )
            )
    return out


def new_experiment(name: str, root: Path | None = None, from_id: str | None = None, force: bool = False) -> Path:
    validate_name(name)
    if from_id is not None:
        from_id = resolve_id(from_id)
    base = experiments_root(root)
    dest = base / name
    if dest.exists() and not force:
        raise ExperimentError(f"{dest} already exists; pass --force to overwrite")
    if from_id is not None:
        src = base / from_id
        if not (src / "config.yaml").is_file():
            raise ExperimentError(f"--from {from_id}: {src / 'config.yaml'} not found")
        raw: dict[str, Any] = yaml.safe_load((src / "config.yaml").read_text(encoding="utf-8")) or {}
    else:
        raw = {
            "id": name,
            "title": f"{name} (synthetic interface test, not rankings)",
            "papers": [{"citation": "TODO: author (year). Title. Venue.", "url": "https://doi.org/TODO"}],
            "data": {"flavour": "synthetic", "preset": "tiny", "seed": 42},
            "runtime": {"backend": "polars", "mode": "local"},
            "methods": ["B0", "B2", "B3"],
            "optional_methods": [],
        }
    raw["id"] = name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    if from_id is not None:
        for f in (base / from_id).iterdir():
            if f.name in ("runs", "config.yaml", "README.md") or f.name.startswith("."):
                continue
            (shutil.copytree if f.is_dir() else shutil.copy2)(f, dest / f.name)
    (dest / "config.yaml").write_text(
        f"# Scaffolded by `xferbench experiment new {name}"
        + (f" --from {from_id}`\n" if from_id else "`\n")
        + yaml.safe_dump(raw, sort_keys=False),
        encoding="utf-8",
    )
    from xferbench.data.tiers import TIER_TEXT

    (dest / "configs").mkdir(exist_ok=True)
    for t in ("sample", "complete"):
        f = dest / "configs" / f"{t}.yaml"
        copied = yaml.safe_load(f.read_text(encoding="utf-8")) or {} if f.exists() else {}
        if not str((copied.get("data") or {}).get("metadata") or "").strip():  # fresh template naming this id
            (dest / "configs" / f"{t}.yaml").write_text(
                TIER_OVERLAY.format(tier=t, text=TIER_TEXT[t], id=name), encoding="utf-8"
            )
    cfg = ExperimentConfig.load(dest / "config.yaml")
    papers = "; ".join(f"{p.get('citation', '')} <{p.get('url', '')}>" for p in cfg.papers) or "none"
    optional = f"; optional (extras needed): {', '.join(cfg.optional_methods)}" if cfg.optional_methods else ""
    (dest / "README.md").write_text(
        TEMPLATE_README.format(
            id=name, papers=papers, preset=cfg.preset, seed=cfg.seed, methods=", ".join(cfg.methods), optional=optional
        ),
        encoding="utf-8",
    )
    return dest


def resolve_id(exp_id: str) -> str:
    if exp_id in DEPRECATED_ALIASES:
        import warnings

        new = DEPRECATED_ALIASES[exp_id]
        # FutureWarning (not DeprecationWarning) so CLI users see it: Python shows it by default, on stderr.
        warnings.warn(
            f"experiment id {exp_id!r} is deprecated and will be removed; use {new!r}", FutureWarning, stacklevel=2
        )
        return new
    return exp_id


def run_dir_for(root: Path | None, exp_id: str, tier: str) -> Path:
    """Default output: eval/<exp_id>__<tier>/ (git-ignored); -2, -3, ... if that folder is already used."""
    base = (root or Path.cwd()) / "eval"
    d = base / f"{exp_id}__{tier}"
    n = 1
    while d.exists() and any(d.iterdir()):
        n += 1
        d = base / f"{exp_id}__{tier}-{n}"
    return d


class ResearchOnlyError(ExperimentError):
    """Research-only / licence-gated experiment requested without --allow-research-only."""


def run_one(
    exp_id: str,
    root: Path | None = None,
    progress: Callable[[str], None] = print,
    allow_research_only: bool = False,
    tier: str | None = None,
    out: Path | None = None,
) -> dict[str, Any]:
    from xferbench.experiments.runner import load_tiered

    exp_id = resolve_id(exp_id)
    exp_dir = experiments_root(root) / exp_id
    if not (exp_dir / "config.yaml").is_file():
        raise ExperimentError(f"unknown experiment {exp_id!r}; see `xferbench experiment list`")
    research = is_research_only(_raw(exp_dir / "config.yaml"))
    if research:
        tier = tier or "complete"  # a reproduction runs on the full licensed dataset
    else:
        _, tier = load_tiered(exp_dir / "config.yaml", tier)
    out = out or run_dir_for(root, exp_id, tier)
    if research:
        if not allow_research_only:
            raise ResearchOnlyError(
                f"{exp_id} is research-only and licence-gated; pass --allow-research-only to run it"
            )
        from xferbench.repro.visuelle import run_reproduction

        res = run_reproduction(exp_dir / "config.yaml", out)
        res["_out"] = str(out)
        res.setdefault("tier", tier)
        return res
    res = run_experiment(exp_dir / "config.yaml", out, progress=progress, tier=tier)
    res["_out"] = str(out)
    return res


def planned_tiers(infos: list[ExperimentInfo], tier: str | None = None) -> dict[str, str]:
    """The data tier each experiment would run at (same rules as run_one), checked to be a single tier.

    Raises TierMixError without running anything if the selection would mix tiers. Invalid configs are skipped
    (they are reported as invalid_config rows, not run)."""
    from xferbench.data.tiers import require_single_tier
    from xferbench.experiments.runner import load_tiered

    plan: dict[str, str] = {}
    for info in infos:
        if info.error:
            continue
        cfg = info.path / "config.yaml"
        if tier:
            plan[info.id] = tier
        elif is_research_only(_raw(cfg)):
            plan[info.id] = "complete"
        else:
            try:
                plan[info.id] = load_tiered(cfg, None)[1]
            except Exception:  # reported by run_one as a failed row
                continue
    require_single_tier(plan.items(), what="run-all (nothing was run)")
    return plan


def run_all(
    root: Path | None = None,
    only: list[str] | None = None,
    progress: Callable[[str], None] = print,
    allow_research_only: bool = False,
    tier: str | None = None,
) -> list[dict[str, Any]]:
    """Run every experiment, continuing past failures. Returns one summary row per experiment (alphabetical).

    Research-only / licence-gated reproductions are excluded unless ``allow_research_only``.
    """
    from xferbench.repro.visuelle import ReproError

    selected = [i for i in list_experiments(root, allow_research_only=allow_research_only) if not only or i.id in only]
    plan = planned_tiers(selected, tier)  # raises TierMixError before anything runs
    rows = []
    for info in selected:
        row: dict[str, Any] = {
            "experiment": info.id, "tier": plan.get(info.id, tier or "synthetic"), "status": "ok", "ran": 0, "not_run": 0, "out": "",
            "detail": "",
        }  # fmt: skip
        if info.error:
            row.update(status="invalid_config", detail=info.error[:200])
        elif info.kind == "reproduction":
            try:
                res = run_one(info.id, root, progress=progress, allow_research_only=True, tier=tier)
                row.update(out=res["_out"], detail="RESEARCH ONLY", tier=res.get("tier", row["tier"]))
            except ReproError as exc:
                row.update(status="blocked", detail=f"RESEARCH ONLY; {exc}"[:200])
            except Exception as exc:
                row.update(status="failed", detail=f"{type(exc).__name__}: {exc}"[:200])
        else:
            try:
                res = run_one(info.id, root, progress=progress, tier=tier)
                row.update(ran=len(res["test_rows"]), not_run=len(res["not_run"]), out=res["_out"], tier=res["tier"])
                if not res["day_zero_result"]:
                    row["detail"] = "NOT A DAY-ZERO RESULT"
            except Exception as exc:
                row.update(status="failed", detail=f"{type(exc).__name__}: {exc}"[:200])
        rows.append(row)
    return rows


def summary_table(rows: list[dict[str, Any]]) -> str:
    """Status table for run-all. Refuses rows from different data tiers (TierMixError)."""
    from xferbench.data.tiers import require_single_tier

    tier = require_single_tier(((r["experiment"], r.get("tier")) for r in rows), "experiments")
    head = "| experiment | tier | status | methods run | not run | output | note |\n|---|---|---|---|---|---|---|"
    body = [
        f"| {r['experiment']} | {r.get('tier')} | {r['status']} | {r['ran']} | {r['not_run']} | {r['out']} | {r['detail']} |"
        for r in rows
    ]
    note = (
        "Synthetic interface test, not a ranking: experiments are listed alphabetically; no scores are compared."
        if tier == "synthetic"
        else f"Data tier {tier}, not a ranking: experiments are listed alphabetically; no scores are compared."
    )
    return "\n".join([note, f"Data tier: {tier}", "", head, *body])
