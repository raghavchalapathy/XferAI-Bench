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
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from xferbench.experiments.runner import ExperimentConfig, ExperimentError, run_experiment

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
TEMPLATE_README = """# {id}

**Synthetic interface test, not a ranking.** Outputs check the software, not which method is better.

- **Paper(s):** {papers}
- **Data:** synthetic preset `{preset}`, seed {seed} (`data.flavour: synthetic`). To use your own data, see
  `DIY-GettingStarted.md` (data/<flavour>/ plus configs/<flavour>/); only config changes.
- **Models:** {methods}{optional}
- **Run:** `xferbench experiment run {id}` -> `experiments/{id}/runs/<timestamp>/` (git-ignored)
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
    if not NAME_RE.fullmatch(name):
        raise ExperimentError(
            f"invalid experiment name {name!r}: use 3-64 chars, lowercase letters, digits and '_', starting with a letter"
        )
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
                    )
                )  # fmt: skip
            continue
        try:
            c = ExperimentConfig.load(cfg_path)
            out.append(
                ExperimentInfo(c.id, d, c.title, c.methods, c.optional_methods, c.preset, c.not_day_zero is None)
            )
        except (ExperimentError, KeyError, yaml.YAMLError) as exc:
            out.append(ExperimentInfo(d.name, d, "", [], [], "", False, error=str(exc)))
    return out


def new_experiment(name: str, root: Path | None = None, from_id: str | None = None, force: bool = False) -> Path:
    validate_name(name)
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
        f"# Scaffolded by `xferbench experiment new {name}" + (f" --from {from_id}`\n" if from_id else "`\n")
        + yaml.safe_dump(raw, sort_keys=False),
        encoding="utf-8",
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


def run_dir_for(exp_dir: Path) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    d = exp_dir / "runs" / stamp
    n = 1
    while d.exists():
        n += 1
        d = exp_dir / "runs" / f"{stamp}-{n}"
    return d


class ResearchOnlyError(ExperimentError):
    """Research-only / licence-gated experiment requested without --allow-research-only."""


def run_one(
    exp_id: str,
    root: Path | None = None,
    progress: Callable[[str], None] = print,
    allow_research_only: bool = False,
) -> dict[str, Any]:
    exp_dir = experiments_root(root) / exp_id
    if not (exp_dir / "config.yaml").is_file():
        raise ExperimentError(f"unknown experiment {exp_id!r}; see `xferbench experiment list`")
    out = run_dir_for(exp_dir)
    if is_research_only(_raw(exp_dir / "config.yaml")):
        if not allow_research_only:
            raise ResearchOnlyError(
                f"{exp_id} is research-only and licence-gated; pass --allow-research-only to run it"
            )
        from xferbench.repro.visuelle import run_reproduction

        res = run_reproduction(exp_dir / "config.yaml", out)
        res["_out"] = str(out)
        return res
    res = run_experiment(exp_dir / "config.yaml", out, progress=progress)
    res["_out"] = str(out)
    return res


def run_all(
    root: Path | None = None,
    only: list[str] | None = None,
    progress: Callable[[str], None] = print,
    allow_research_only: bool = False,
) -> list[dict[str, Any]]:
    """Run every experiment, continuing past failures. Returns one summary row per experiment (alphabetical).

    Research-only / licence-gated reproductions are excluded unless ``allow_research_only``.
    """
    from xferbench.repro.visuelle import ReproError

    rows = []
    for info in list_experiments(root, allow_research_only=allow_research_only):
        if only and info.id not in only:
            continue
        row: dict[str, Any] = {"experiment": info.id, "status": "ok", "ran": 0, "not_run": 0, "out": "", "detail": ""}
        if info.error:
            row.update(status="invalid_config", detail=info.error[:200])
        elif info.kind == "reproduction":
            try:
                res = run_one(info.id, root, progress=progress, allow_research_only=True)
                row.update(out=res["_out"], detail="RESEARCH ONLY")
            except ReproError as exc:
                row.update(status="blocked", detail=f"RESEARCH ONLY; {exc}"[:200])
            except Exception as exc:  # noqa: BLE001
                row.update(status="failed", detail=f"{type(exc).__name__}: {exc}"[:200])
        else:
            try:
                res = run_one(info.id, root, progress=progress)
                row.update(ran=len(res["test_rows"]), not_run=len(res["not_run"]), out=res["_out"])
                if not res["day_zero_result"]:
                    row["detail"] = "NOT A DAY-ZERO RESULT"
            except Exception as exc:  # noqa: BLE001 - run-all must continue past any failure
                row.update(status="failed", detail=f"{type(exc).__name__}: {exc}"[:200])
        rows.append(row)
    return rows


def summary_table(rows: list[dict[str, Any]]) -> str:
    head = "| experiment | status | methods run | not run | output | note |\n|---|---|---|---|---|---|"
    body = [
        f"| {r['experiment']} | {r['status']} | {r['ran']} | {r['not_run']} | {r['out']} | {r['detail']} |" for r in rows
    ]
    note = "Synthetic interface test, not a ranking: experiments are listed alphabetically; no scores are compared."
    return "\n".join([note, "", head, *body])
