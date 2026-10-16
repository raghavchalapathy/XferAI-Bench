"""BenchmarkRunner: the single execution path behind ``xferbench run`` and the Python API."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from xferbench import __version__
from xferbench.calendar import to_ts
from xferbench.contracts.methods import ModelArtifact, RegistryEntryReport
from xferbench.contracts.selection import Selection
from xferbench.contracts.splits import SplitManifest
from xferbench.contracts.tables import FORECAST_STATUSES
from xferbench.data.io import Dataset, load_from_metadata_path
from xferbench.data.issues import DataError
from xferbench.domains.registry import get_domain
from xferbench.evaluation.evaluator import evaluate, leaderboard_frame
from xferbench.features.context import ContextBuilder, OriginContext
from xferbench.methods.base import Method, TrainingContext, variant_id
from xferbench.methods.registry import REGISTRY_VERSION, RegistryEntry, all_entries, assess, entries_for_profile
from xferbench.orchestration.resources import hardware, max_rss_mib, measure, package_versions
from xferbench.util import (
    atomic_write_csv,
    atomic_write_parquet,
    hash_obj,
    read_json,
    utc_now_iso,
    write_json,
)

RUN_SCHEMA_VERSION = "1.0"
EXIT_OK, EXIT_ERROR, EXIT_REJECTED, EXIT_PARTIAL, EXIT_CANCELLED = 0, 1, 3, 4, 130


class RunError(Exception):
    def __init__(self, message: str, exit_code: int = EXIT_ERROR):
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class RunConfig:
    metadata_path: Path
    splits_path: Path
    stage: Literal["validation", "test"]
    out: Path
    profile: str = "core"
    methods: list[str] | None = None
    selection_path: Path | None = None
    max_seconds: float | None = None
    overwrite: bool = False
    write_report: bool = True
    measure_memory: bool = True
    data_label: dict[str, Any] | None = None  # see xferbench.data.classes


@dataclass
class RunResult:
    out: Path
    status: str
    exit_code: int
    manifest: dict
    leaderboard: pd.DataFrame
    method_support: list[dict] = field(default_factory=list)


@dataclass
class _Variant:
    entry: RegistryEntry
    method: Method
    config: dict[str, Any]
    vid: str
    artifact: ModelArtifact | None = None
    fit_error: str | None = None
    fit_seconds: float = 0.0
    fit_peak: int = 0
    predict_seconds: float = 0.0
    predict_peak: int = 0
    artifact_bytes: int = 0
    frames: list[pd.DataFrame] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def load_split(path: Path) -> SplitManifest:
    split = SplitManifest.model_validate(read_json(path))
    if not split.verify():
        raise RunError(f"{path}: split hash does not match its contents (file was modified after freezing)")
    return split


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._=-]+", "_", name)


def validate_batch(raw: pd.DataFrame, requests: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, list[str]]:
    """Enforce the ForecastBatch contract; violating requests become failed rows (never dropped)."""
    problems: list[str] = []
    need = {"request_id", "horizon_week", "point_units", "status"}
    if not need.issubset(raw.columns):
        problems.append(f"batch missing columns {sorted(need - set(raw.columns))}")
        raw = pd.DataFrame(columns=[*need, "raw_point_units", "reason", "forecast_week"])
    raw = raw.copy()
    defaults: dict[str, Any] = {"raw_point_units": np.nan, "reason": "", "forecast_week": pd.NaT}
    for c, default in defaults.items():
        if c not in raw.columns:
            raw[c] = default
    raw["forecast_week"] = pd.to_datetime(raw["forecast_week"]).astype("datetime64[ns]")
    raw["raw_point_units"] = pd.to_numeric(raw["raw_point_units"], errors="coerce").astype(float)
    raw["reason"] = raw["reason"].fillna("").astype(str)
    raw["point_units"] = pd.to_numeric(raw["point_units"], errors="coerce").astype(float)
    bad_ids: dict[str, str] = {}
    hw = set(range(1, horizon + 1))
    for rid, grp in raw.groupby("request_id"):
        if len(grp) != horizon or set(grp["horizon_week"].astype(int)) != hw:
            bad_ids[str(rid)] = f"expected {horizon} unique horizon rows, got {len(grp)}"
            continue
        ok_rows = grp["status"].isin(["success", "fallback"])
        vals = grp.loc[ok_rows, "point_units"]
        if (~np.isfinite(vals)).any() or (vals < 0).any():
            bad_ids[str(rid)] = "success/fallback rows must have finite nonnegative point_units"
        elif grp.loc[~ok_rows, "point_units"].notna().any():
            bad_ids[str(rid)] = "failed rows must have null point_units"
        elif not grp["status"].isin(FORECAST_STATUSES).all():
            bad_ids[str(rid)] = "invalid status value"
    expected = set(requests["request_id"])
    for rid in expected - set(raw["request_id"]):
        bad_ids[str(rid)] = "no rows returned for request"
    extra = set(raw["request_id"]) - expected
    if extra:
        problems.append(f"batch returned unknown request ids {sorted(extra)[:5]}")
        raw = raw[raw["request_id"].isin(expected)]
    if bad_ids:
        problems.append(f"{len(bad_ids)} requests violated the forecast contract")
        raw = raw[~raw["request_id"].isin(bad_ids)]
        failed = failed_rows(
            requests[requests["request_id"].isin(bad_ids)],
            horizon,
            "failed",
            lambda rid: f"contract_violation: {bad_ids[rid]}",
        )
        raw = pd.concat([f for f in (raw, failed) if not f.empty], ignore_index=True)
    return raw, problems


def failed_rows(requests: pd.DataFrame, horizon: int, status: str, reason: str | Callable[[str], str]) -> pd.DataFrame:
    frames = []
    for r in requests.itertuples(index=False):
        hw = np.arange(1, horizon + 1)
        frames.append(
            pd.DataFrame(
                {
                    "request_id": r.request_id,
                    "horizon_week": hw,
                    "forecast_week": [r.origin + pd.Timedelta(days=7 * (h - 1)) for h in hw],
                    "point_units": np.nan,
                    "raw_point_units": np.nan,
                    "status": status,
                    "reason": reason(r.request_id) if callable(reason) else reason,
                }
            )
        )
    return (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(
            columns=[
                "request_id",
                "horizon_week",
                "forecast_week",
                "point_units",
                "raw_point_units",
                "status",
                "reason",
            ]
        )
    )


class BenchmarkRunner:
    def __init__(self, config: RunConfig, progress: Callable[[str], None] | None = None):
        self.cfg = config
        self.progress = progress or (lambda msg: None)

    def run(self) -> RunResult:
        cfg = self.cfg
        out = cfg.out
        if out.exists() and any(out.iterdir()) and not cfg.overwrite:
            raise RunError(f"output directory {out} is not empty; runs are append-only. Choose a new --out.")
        out.mkdir(parents=True, exist_ok=True)
        t_start = time.perf_counter()
        try:
            dataset = load_from_metadata_path(cfg.metadata_path)
        except DataError as exc:
            raise RunError(f"data failed to load:\n{exc}") from exc
        domain = get_domain(dataset.metadata.domain_plugin)
        issues = domain.validate(dataset)
        split = load_split(cfg.splits_path)
        write_json(
            out / "data_quality.json",
            {
                "schema_version": RUN_SCHEMA_VERSION,
                "dataset_hash": dataset.content_hash,
                "issues": [i.to_dict() for i in issues],
                "error_count": sum(i.severity == "error" for i in issues),
                "profile": domain.data_profile(dataset, split),
            },
        )
        errors = [i for i in issues if i.severity == "error"]
        if errors:
            raise RunError("data validation failed:\n" + "\n".join(str(e) for e in errors[:20]))
        if split.dataset_hash != dataset.content_hash:
            raise RunError("splits.json was built for different data (dataset hash mismatch); rebuild splits")
        if split.failed_checks:
            raise RunError(
                "split checks failed:\n" + "\n".join(f"{c.check}: {c.detail}" for c in split.failed_checks[:20])
            )
        stage = split.stages[cfg.stage]
        if not stage.launches:
            raise RunError(f"stage '{cfg.stage}' has no launches")

        selection: Selection | None = None
        if cfg.stage == "test":
            if cfg.selection_path is None:
                raise RunError("the test stage requires --selection (frozen validation selection)")
            selection = Selection.model_validate(read_json(cfg.selection_path))
            if selection.dataset_hash != dataset.content_hash or selection.split_hash != split.split_hash:
                raise RunError("selection.json was frozen on a different dataset/split; refusing test run")
            if (
                selection.selection_cutoff
                and stage.origins
                and to_ts(selection.selection_cutoff) > to_ts(stage.origins[0])
            ):
                raise RunError("selection cutoff is after the first test origin")

        entries_all = all_entries()
        requested, explicit = self._requested(selection)
        variants, support = self._preflight(entries_all, requested, explicit, dataset, selection, domain, split)

        requests = domain.requests(dataset, split, cfg.stage)
        n_req = len(requests)
        runnable_ids = {v.entry.spec.method_id for v in variants}
        for s in support:
            if s.method_id in {e.spec.method_id for e in requested} and s.method_id not in runnable_ids:
                s.affected_requests = n_req
        horizon = dataset.metadata.time.horizon_weeks
        run_id = f"{cfg.stage}-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
        status = "complete"

        training = self._training_context(dataset, split, domain)
        (out / "artifacts").mkdir(exist_ok=True)
        for v in variants:
            self.progress(f"fit {v.vid}")
            try:
                with measure(cfg.measure_memory) as m:
                    v.artifact = v.method.fit(training, None, v.config)
                path = out / "artifacts" / f"{_safe(v.vid)}.json"
                write_json(path, v.artifact.model_dump(mode="json"))
                v.artifact_bytes = path.stat().st_size
            except Exception as exc:
                v.fit_error = f"fit failed: {type(exc).__name__}: {exc}"
            v.fit_seconds, v.fit_peak = m.seconds, m.peak_bytes

        builder = domain.context_builder(dataset, split, cfg.stage)
        origins = sorted(requests["origin"].unique())
        done_origins: set = set()
        try:
            for i, origin in enumerate(origins, 1):
                if cfg.max_seconds is not None and time.perf_counter() - t_start > cfg.max_seconds:
                    status = "partial"
                    break
                batch = requests[requests["origin"] == origin]
                self.progress(f"origin {pd.Timestamp(origin).date()} ({i}/{len(origins)}, {len(batch)} requests)")
                ctx = builder.at(origin)
                for v in variants:
                    v.frames.append(self._predict(v, batch, ctx, horizon))
                done_origins.add(origin)
        except KeyboardInterrupt:
            status = "cancelled"

        remaining = requests[~requests["origin"].isin(done_origins)]
        if len(remaining):
            reason = "run budget exceeded before this origin" if status == "partial" else "run cancelled"
            for v in variants:
                v.frames.append(failed_rows(remaining, horizon, "skipped", reason))

        forecasts = self._assemble(variants, requests, run_id)
        atomic_write_parquet(out / "forecasts.parquet", forecasts)

        targets = domain.targets(dataset, requests)
        weights = dataset.metadata.cohorts.selection_weights
        result = evaluate(forecasts, targets, requests, weights)
        resources = {
            v.vid: {
                "method_id": v.entry.spec.method_id,
                "fit_seconds": round(v.fit_seconds, 6),
                "predict_seconds": round(v.predict_seconds, 6),
                "peak_python_mib": round(max(v.fit_peak, v.predict_peak) / 2**20, 3),
                "artifact_bytes": v.artifact_bytes,
                "requests": n_req,
                "predict_rows": int(n_req * horizon),
            }
            for v in variants
        }
        lb = leaderboard_frame(result, resources)
        atomic_write_csv(out / "leaderboard.csv", lb)
        atomic_write_csv(out / "slices.csv", pd.DataFrame(result["slices"]))
        fail = forecasts[forecasts["status"] != "success"]
        fail_summary = (
            fail.groupby(["variant_id", "status", "reason"], dropna=False)
            .agg(rows=("request_id", "size"), requests=("request_id", "nunique"))
            .reset_index()
        )
        atomic_write_csv(out / "failures.csv", fail_summary)

        for s in support:
            vs = [v for v in variants if v.entry.spec.method_id == s.method_id]
            if not vs:
                continue
            if all(v.fit_error is None and not v.errors for v in vs) and status == "complete":
                s.execution_state = "success"
            elif status != "complete":
                s.execution_state = "success" if all(v.fit_error is None for v in vs) else "failed"
                s.reason = f"run {status}; unfinished requests marked skipped"
            else:
                s.execution_state = "failed"
                s.reason = "; ".join(sorted({v.fit_error or "" for v in vs} | {e for v in vs for e in v.errors}))[:500]
        support_json = [s.model_dump(mode="json") for s in support]
        write_json(out / "method_support.json", {"registry_version": REGISTRY_VERSION, "entries": support_json})
        write_json(
            out / "resources.json",
            {
                "variants": resources,
                "process_max_rss_mib": max_rss_mib(),
                "wall_seconds": round(time.perf_counter() - t_start, 3),
                "memory_note": "peak_python_mib is the tracemalloc peak (Python heap incl. NumPy buffers) during "
                "fit or predict of that variant; process_max_rss_mib is whole-process.",
                "cost": "not reported (no measured pricing inputs)",
            },
        )
        write_json(
            out / "metrics.json",
            {k: v for k, v in result.items() if k != "slices"}
            | {
                "metric_definitions": dataset.metadata.metrics.definitions,
                "zero_denominator": dataset.metadata.metrics.zero_denominator,
                "stage": cfg.stage,
                "run_id": run_id,
            },
        )
        manifest = self._manifest(
            run_id, status, dataset, split, selection, variants, support_json, result, requests, horizon
        )
        write_json(out / "run_manifest.json", manifest)

        if cfg.write_report:
            from xferbench.reports.html import write_run_report

            write_run_report(out, out / "report.html")
        if (cfg.data_label or {}).get("data_class") == "local":
            from xferbench.data.classes import redact_local_outputs

            ent = tuple(getattr(domain, "entity_columns", ()))
            ids = set(requests["request_id"].astype(str))
            for df in [requests, *dataset.tables.values()]:
                for c in ent:
                    if c in df.columns:
                        ids |= set(df[c].dropna().astype(str))
            redact_local_outputs(out, ids, run_id)
        exit_code = {"complete": EXIT_OK, "partial": EXIT_PARTIAL, "cancelled": EXIT_CANCELLED}[status]
        return RunResult(out, status, exit_code, manifest, lb, support_json)

    def _requested(self, selection: Selection | None) -> tuple[list[RegistryEntry], bool]:
        cfg = self.cfg
        if selection is not None:
            ids = [f.method_id for f in selection.families if f.eligible]
            return [e for e in all_entries() if e.spec.method_id in ids], True
        if cfg.methods:
            known = {e.spec.method_id: e for e in all_entries()}
            unknown = [m for m in cfg.methods if m not in known]
            if unknown:
                raise RunError(f"unknown method ids {unknown}; see `xferbench list-methods --all`", EXIT_REJECTED)
            return [known[m] for m in cfg.methods], True
        try:
            return entries_for_profile(cfg.profile), False
        except KeyError as exc:
            raise RunError(str(exc), EXIT_REJECTED) from exc

    def _preflight(
        self,
        entries_all: list[RegistryEntry],
        requested: list[RegistryEntry],
        explicit: bool,
        dataset: Dataset,
        selection: Selection | None,
        domain: Any,
        split: SplitManifest,
    ) -> tuple[list[_Variant], list[RegistryEntryReport]]:
        req_ids = {e.spec.method_id for e in requested}
        support: list[RegistryEntryReport] = []
        variants: list[_Variant] = []
        rejected_explicit = []
        for e in entries_all:
            rep = assess(e, dataset)
            if e.spec.method_id not in req_ids:
                frozen = (
                    next((f for f in selection.families if f.method_id == e.spec.method_id), None)
                    if selection is not None
                    else None
                )
                if frozen is not None:
                    rep.reason = f"rejected by the frozen validation selection: {frozen.reason}"
                elif not explicit:
                    rep.reason = f"not requested (profile '{self.cfg.profile}')" + (
                        f"; {rep.reason}" if rep.reason else ""
                    )
                else:
                    rep.reason = "not requested" + (f"; {rep.reason}" if rep.reason else "")
                support.append(rep)
                continue
            runnable = (
                e.implementation_state in ("implemented", "experimental")
                and e.factory is not None
                and rep.execution_state != "not_installed"
                and rep.eligibility_state == "compatible"
            )
            if not runnable:
                support.append(rep)
                rejected_explicit.append(f"{e.spec.method_id}: {rep.reason} -> {rep.remedy}")
                continue
            method = e.factory()  # type: ignore[misc]
            grid = method.variants()
            if selection is not None:
                fam = next(f for f in selection.families if f.method_id == e.spec.method_id)
                if variant_id(e.spec.method_id, fam.config, grid) != fam.variant_id:
                    raise RunError(
                        f"frozen variant {fam.variant_id} does not match the method's current grid; "
                        "the method changed after selection",
                        EXIT_REJECTED,
                    )
                configs = [fam.config]
            else:
                configs = grid
            for c in configs:
                variants.append(_Variant(e, method, dict(c), variant_id(e.spec.method_id, c, grid)))
            support.append(rep)
        if explicit and rejected_explicit and selection is None:
            raise RunError(
                "explicitly requested methods cannot run (no substitute is used):\n  " + "\n  ".join(rejected_explicit),
                EXIT_REJECTED,
            )
        return variants, support

    def _training_context(self, dataset: Dataset, split: SplitManifest, domain: Any) -> TrainingContext:
        stage = self.cfg.stage
        treq = domain.training_requests(dataset, split, stage)
        labels = domain.targets(dataset, treq) if len(treq) else pd.DataFrame()
        cutoff = to_ts(split.stages[stage].fit_cutoff)
        builders: dict[str, ContextBuilder] = {}
        by_id = treq.set_index("request_id") if len(treq) else None

        def context_for(request_id: str) -> OriginContext:
            assert by_id is not None
            row = by_id.loc[request_id]
            src = row["source_stage"]
            if src not in builders:
                builders[src] = domain.context_builder(dataset, split, src)
            return builders[src].at(row["origin"])

        return TrainingContext(
            requests=treq,
            labels=labels,
            fit_cutoff=cutoff,
            data_hash=hash_obj(
                {"dataset": dataset.content_hash, "fit": sorted(treq["request_id"]) if len(treq) else []}
            ),
            context_for=context_for,
        )

    def _predict(self, v: _Variant, batch: pd.DataFrame, ctx: OriginContext, horizon: int) -> pd.DataFrame:
        if v.fit_error is not None or v.artifact is None:
            return failed_rows(batch, horizon, "failed", v.fit_error or "no artifact")
        try:
            with measure(self.cfg.measure_memory) as m:
                raw = v.method.predict_batch(batch.reset_index(drop=True), ctx, v.artifact)
            v.predict_seconds += m.seconds
            v.predict_peak = max(v.predict_peak, m.peak_bytes)
        except Exception as exc:
            msg = f"predict failed: {type(exc).__name__}: {exc}"
            v.errors.append(msg)
            return failed_rows(batch, horizon, "failed", msg)
        fixed, problems = validate_batch(raw, batch, horizon)
        v.errors.extend(problems)
        return fixed

    def _assemble(self, variants: list[_Variant], requests: pd.DataFrame, run_id: str) -> pd.DataFrame:
        cols = ["request_id", "launch_id", "item_id", "fpg_id", "scenario", "board", "origin"]
        frames = []
        for v in variants:
            if not v.frames:
                continue
            f = pd.concat(v.frames, ignore_index=True)
            f = f.merge(requests[cols], on="request_id", how="left")
            f["forecast_week"] = f["origin"] + pd.to_timedelta(7 * (f["horizon_week"].astype(int) - 1), unit="D")
            f["method_id"] = v.entry.spec.method_id
            f["variant_id"] = v.vid
            f["run_id"] = run_id
            f["point_statistic"] = v.entry.spec.point_statistic
            f["postprocessing"] = "none"
            frames.append(f)
        order = [
            *cols,
            "horizon_week",
            "forecast_week",
            "point_units",
            "raw_point_units",
            "status",
            "reason",
            "point_statistic",
            "postprocessing",
            "method_id",
            "variant_id",
            "run_id",
        ]
        if not frames:
            return pd.DataFrame(columns=order)
        out = pd.concat(frames, ignore_index=True)[order]
        out["horizon_week"] = out["horizon_week"].astype("int64")
        return out.sort_values(["variant_id", "request_id", "horizon_week"]).reset_index(drop=True)

    def _manifest(
        self,
        run_id: str,
        status: str,
        dataset: Dataset,
        split: SplitManifest,
        selection: Selection | None,
        variants: list[_Variant],
        support: list[dict],
        result: dict,
        requests: pd.DataFrame,
        horizon: int,
    ) -> dict:
        md = dataset.metadata
        st = split.stages[self.cfg.stage]
        return {
            "run_schema_version": RUN_SCHEMA_VERSION,
            "data": self.cfg.data_label
            or {"data_class": "unlabeled", "benchmark_id": None, "benchmark_version": None, "benchmark_kind": None},
            "run_id": run_id,
            "status": status,
            "stage": self.cfg.stage,
            "created_at": utc_now_iso(),
            "software": {
                "xferbench": __version__,
                "packages": package_versions(),
                "registry_version": REGISTRY_VERSION,
            },
            "hardware": hardware(),
            "config": {
                "profile": self.cfg.profile,
                "methods": self.cfg.methods,
                "max_seconds": self.cfg.max_seconds,
                "metadata_path": self.cfg.metadata_path.name,
                "splits_path": self.cfg.splits_path.name,
            },
            "domain_plugin": md.domain_plugin,
            "dataset_id": md.dataset.id,
            "dataset_version": md.dataset.version,
            "dataset_hash": dataset.content_hash,
            "table_hashes": dataset.table_hashes,
            "feature_hash": dataset.table_hashes.get("origin_features"),
            "synthetic": md.dataset.synthetic,
            "generator": md.dataset.generator,
            "metadata_hash": split.metadata_hash,
            "split_hash": split.split_hash,
            "selection": None
            if selection is None
            else {
                "validation_run_id": selection.validation_run_id,
                "policy_hash": selection.policy_hash,
                "recommended": selection.recommended,
                "frozen_variants": [f.variant_id for f in selection.families if f.eligible],
            },
            "selection_cutoff": split.selection_cutoff,
            "fit_cutoff": st.fit_cutoff,
            "n_fit_launches": len(st.fit_launch_ids),
            "origins": st.origins,
            "horizon_weeks": horizon,
            "n_requests": len(requests),
            "boards": {b: int(n) for b, n in requests["board"].value_counts().items()},
            "population": result["population"],
            "variants": [
                {
                    "method_id": v.entry.spec.method_id,
                    "variant_id": v.vid,
                    "config": v.config,
                    "point_statistic": v.entry.spec.point_statistic,
                    "artifact": f"artifacts/{_safe(v.vid)}.json" if v.artifact else None,
                    "fit_error": v.fit_error,
                    "contract_problems": v.errors,
                }
                for v in variants
            ],
            "method_states": {
                s["method_id"]: {k: s[k] for k in ("implementation_state", "execution_state", "eligibility_state")}
                for s in support
            },
            "rights_context": {
                "data": md.rights.model_dump(),
                "mode": "commercial-safe default: restricted weights and services are blocked",
            },
            "privacy": md.privacy.model_dump() | {"network_calls_made": False},
            "metric_definitions": md.metrics.definitions,
            "contamination_note": "No pretrained foundation model was used in this run.",
            "limitations": [
                "Synthetic results demonstrate software behavior, not real-world model superiority."
                if md.dataset.synthetic
                else "Results apply to this dataset, split and protocol only.",
                "Paired block-bootstrap uncertainty is not computed in this version.",
            ],
        }
