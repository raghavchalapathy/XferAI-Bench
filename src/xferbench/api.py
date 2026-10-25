"""Library API shared by the CLI, the experiments and production jobs: ``fit``, ``save``, ``load``, ``predict``
and ``evaluate``.

The benchmarked method *is* the production job: ``fit`` trains exactly the frozen (validation-selected) variant the
benchmark scored, ``save`` writes a versioned artifact with a manifest, and ``predict`` (``xferbench forecast``)
forecasts new launches from that artifact without actuals and without calling the evaluator. ``evaluate`` wraps the
protected evaluator (via ``BenchmarkRunner``) and is the only function here that needs actuals.

Exit codes (``ApiError.exit_code``; also used by ``xferbench fit`` / ``xferbench forecast``):

==== ==================================================================
0    success
1    unexpected error
2    usage / config error (bad path, bad YAML, unknown flag value)
3    method rejected (unknown id, not installed, frozen variant changed)
5    artifact mismatch (manifest hash, method version or config hash differ)
6    input schema mismatch (new data does not match the training schema)
==== ==================================================================
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import platform
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from xferbench.contracts.methods import ModelArtifact
from xferbench.util import hash_obj, read_json, write_json

MANIFEST_SCHEMA = "xferbench.model-manifest/1"
EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_REJECTED, EXIT_ARTIFACT, EXIT_SCHEMA = 0, 1, 2, 3, 5, 6
LIBS = ("xferbench", "xfer-bench", "numpy", "pandas", "polars", "pyarrow", "lightgbm", "pyspark")

log = logging.getLogger("xferbench")


class ApiError(RuntimeError):
    def __init__(self, message: str, exit_code: int = EXIT_ERROR):
        super().__init__(message)
        self.exit_code = exit_code


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)), "level": record.levelname}
        out["event"] = record.getMessage()
        out.update(getattr(record, "fields", {}))
        return json.dumps(out, sort_keys=True, default=str)


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    """Structured (JSON lines on stderr) logging for production jobs; idempotent."""
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(_JsonFormatter() if json_logs else logging.Formatter("%(levelname)s %(message)s"))
    log.handlers[:] = [h]
    log.setLevel(level)
    log.propagate = False


def _event(event: str, **fields: Any) -> None:
    log.info(event, extra={"fields": fields})


def set_seeds(seed: int) -> None:
    """Deterministic seeds for Python and NumPy (methods receive ``seed`` in their config where they accept one)."""
    random.seed(seed)
    np.random.seed(seed % 2**32)


def library_versions() -> dict[str, str | None]:
    out: dict[str, str | None] = {"python": platform.python_version()}
    for name in LIBS:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = None
    return out


def schema_hash(dataset: Any) -> str:
    """Hash of table names, column names and dtypes (not values): what a production input must match."""
    return hash_obj(
        {name: [[str(c), str(t)] for c, t in df.dtypes.items()] for name, df in sorted(dataset.tables.items())}
    )


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@dataclass
class FittedModel:
    artifact: ModelArtifact
    manifest: dict[str, Any]


def _load_inputs(metadata_path: Path, splits_path: Path) -> tuple[Any, Any, Any]:
    from xferbench.data.io import DataError, load_from_metadata_path
    from xferbench.domains.registry import get_domain
    from xferbench.orchestration.runner import load_split

    try:
        ds = load_from_metadata_path(Path(metadata_path))
    except (DataError, FileNotFoundError, OSError) as exc:
        raise ApiError(f"data failed to load: {exc}", EXIT_USAGE) from exc
    domain = get_domain(ds.metadata.domain_plugin)
    errors = [i for i in domain.validate(ds) if i.severity == "error"]
    if errors:
        raise ApiError("input validation failed:\n" + "\n".join(str(e) for e in errors[:20]), EXIT_SCHEMA)
    try:
        split = load_split(Path(splits_path))
    except Exception as exc:
        raise ApiError(f"splits failed to load: {exc}", EXIT_USAGE) from exc
    return ds, domain, split


def _method_and_config(method_id: str, config: dict[str, Any] | None, selection_path: Path | None) -> tuple:
    from xferbench.models.base import variant_id
    from xferbench.models.registry import assess, get_entry
    from xferbench.orchestration.runner import load_selection_file

    try:
        entry = get_entry(method_id)
    except KeyError as exc:
        raise ApiError(f"unknown method id {method_id!r}; see `xferbench list-methods --all`", EXIT_REJECTED) from exc
    rep = assess(entry)
    if entry.factory is None or rep.execution_state == "not_installed":
        raise ApiError(f"{method_id} cannot run: {rep.reason} -> {rep.remedy}", EXIT_REJECTED)
    method = entry.factory()
    grid = method.variants()
    if selection_path is not None:
        sel = load_selection_file(Path(selection_path))
        fam = next((f for f in sel.families if f.method_id == entry.spec.method_id), None)
        if fam is None:
            raise ApiError(f"{method_id} is not in the frozen selection {selection_path}", EXIT_REJECTED)
        if variant_id(entry.spec.method_id, fam.config, grid) != fam.variant_id:
            raise ApiError("frozen variant does not match the method's current grid", EXIT_REJECTED)
        cfg = dict(fam.config)
    else:
        cfg = dict(config) if config is not None else dict(grid[0])
    return entry, method, cfg, grid


def fit(
    metadata_path: Path,
    splits_path: Path,
    method_id: str,
    *,
    config: dict[str, Any] | None = None,
    selection_path: Path | None = None,
    stage: str = "test",
    seed: int = 42,
) -> FittedModel:
    """Fit one method variant on the launches whose labels are available at ``stage``'s fit cutoff."""
    from xferbench.orchestration.runner import BenchmarkRunner, RunConfig, code_provenance

    set_seeds(seed)
    ds, domain, split = _load_inputs(metadata_path, splits_path)
    if split.dataset_hash != ds.content_hash:
        raise ApiError("splits.json was built for different data; rebuild splits", EXIT_USAGE)
    entry, method, cfg, _grid = _method_and_config(method_id, config, selection_path)
    runner = BenchmarkRunner(RunConfig(Path(metadata_path), Path(splits_path), stage, Path("."), methods=[method_id]))  # type: ignore[arg-type]
    training = runner._training_context(ds, split, domain)
    _event("fit.start", method_id=entry.spec.method_id, n_launches=training.n_launches, seed=seed)
    artifact = method.fit(training, None, cfg)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "method_id": artifact.method_id,
        "variant_id": artifact.variant_id,
        "method_version": artifact.method_version,
        "config": cfg,
        "config_hash": hash_obj(cfg),
        "seed": seed,
        "stage": stage,
        "fit_cutoff": artifact.fit_cutoff,
        "training_data_hash": artifact.training_data_hash,
        "data_schema_hash": schema_hash(ds),
        "domain_plugin": ds.metadata.domain_plugin,
        "horizon_weeks": ds.metadata.time.horizon_weeks,
        "code": code_provenance(),
        "libraries": library_versions(),
        "selection": str(selection_path) if selection_path else None,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _event("fit.done", method_id=artifact.method_id, variant_id=artifact.variant_id)
    return FittedModel(artifact, manifest)


def save(model: FittedModel, out_dir: Path, force: bool = False) -> Path:
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()) and not force:
        raise ApiError(f"{out_dir} is not empty; artifacts are immutable (use a new directory)", EXIT_USAGE)
    write_json(out_dir / "artifact.json", model.artifact.model_dump(mode="json"))
    manifest = dict(model.manifest, artifact_sha256=_sha256_file(out_dir / "artifact.json"))
    write_json(out_dir / "manifest.json", manifest)
    return out_dir


def load(model_dir: Path) -> FittedModel:
    """Load an artifact and refuse it (exit 5) if the files or the registered method no longer match."""
    from xferbench.models.registry import get_entry

    model_dir = Path(model_dir)
    try:
        manifest = read_json(model_dir / "manifest.json")
        art_path = model_dir / "artifact.json"
        artifact = ModelArtifact.model_validate(read_json(art_path))
    except (FileNotFoundError, ValueError) as exc:
        raise ApiError(f"not a model directory ({model_dir}): {exc}", EXIT_USAGE) from exc
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ApiError(f"unsupported manifest schema {manifest.get('schema')!r}", EXIT_ARTIFACT)
    if _sha256_file(art_path) != manifest.get("artifact_sha256"):
        raise ApiError("artifact.json does not match manifest artifact_sha256 (modified or corrupt)", EXIT_ARTIFACT)
    if hash_obj(artifact.config) != manifest.get("config_hash") or artifact.method_id != manifest.get("method_id"):
        raise ApiError("artifact config/method does not match the manifest", EXIT_ARTIFACT)
    try:
        spec = get_entry(artifact.method_id).spec
    except KeyError as exc:
        raise ApiError(f"method {artifact.method_id} is not registered here", EXIT_ARTIFACT) from exc
    if spec.version != artifact.method_version:
        raise ApiError(
            f"method version mismatch: artifact {artifact.method_version}, installed {spec.version}; refit",
            EXIT_ARTIFACT,
        )
    return FittedModel(artifact, manifest)


def predict(model: FittedModel, metadata_path: Path, splits_path: Path, stage: str = "test") -> Any:
    """Forecast the launches of ``stage`` (the new launches) from a frozen artifact. Needs no actuals and never
    calls the evaluator. Returns the keyed 52-week forecast frame."""
    import pandas as pd

    from xferbench.models.registry import get_entry
    from xferbench.orchestration.runner import validate_batch

    ds, domain, split = _load_inputs(metadata_path, splits_path)
    got = schema_hash(ds)
    if got != model.manifest["data_schema_hash"]:
        raise ApiError(
            f"input schema mismatch: data schema hash {got[:12]} != artifact {model.manifest['data_schema_hash'][:12]}",
            EXIT_SCHEMA,
        )
    if ds.metadata.domain_plugin != model.manifest.get("domain_plugin"):
        raise ApiError("domain plugin differs from the one the artifact was trained for", EXIT_SCHEMA)
    horizon = ds.metadata.time.horizon_weeks
    if horizon != model.manifest.get("horizon_weeks"):
        raise ApiError("horizon_weeks differs from the artifact's", EXIT_SCHEMA)
    set_seeds(int(model.manifest.get("seed", 42)))
    method = get_entry(model.artifact.method_id).factory()  # type: ignore[misc]
    requests = domain.requests(ds, split, stage)
    builder = domain.context_builder(ds, split, stage)
    frames = []
    for origin in sorted(requests["origin"].unique()):
        batch = requests[requests["origin"] == origin].reset_index(drop=True)
        raw = method.predict_batch(batch, builder.at(origin), model.artifact)
        fixed, problems = validate_batch(raw, batch, horizon)
        for p in problems:
            _event("forecast.row_problem", detail=p)
        frames.append(fixed)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out.insert(0, "variant_id", model.artifact.variant_id)
    out.insert(0, "method_id", model.artifact.method_id)
    _event("forecast.done", rows=len(out), launches=int(requests["launch_id"].nunique()) if len(requests) else 0)
    return out


def evaluate(
    metadata_path: Path,
    splits_path: Path,
    out: Path,
    *,
    stage: str = "test",
    selection_path: Path | None = None,
    methods: list[str] | None = None,
) -> Any:
    """Score with the protected evaluator (needs actuals). Thin wrapper over ``BenchmarkRunner``."""
    from xferbench.orchestration.runner import BenchmarkRunner, RunConfig

    return BenchmarkRunner(
        RunConfig(
            Path(metadata_path),
            Path(splits_path),
            stage,  # type: ignore[arg-type]
            Path(out),
            methods=methods,  # type: ignore[arg-type]
            selection_path=selection_path,
        )
    ).run()
