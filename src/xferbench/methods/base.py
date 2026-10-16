"""Method adapter interface.

Every recipe implements::

    capabilities() -> CapabilitySpec
    variants() -> list[dict]                     # declared configuration grid (selected on validation)
    fit(training, inner_validation, config) -> ModelArtifact
    predict_batch(requests, origin_context, artifact) -> pd.DataFrame   # 52 keyed rows per request

``training`` exposes only fit launches whose labels were available at the fit cutoff, and origin
contexts built for each training launch's own origin. Outer validation/test labels are never passed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd

from xferbench.calendar import WEEK
from xferbench.contracts.methods import CapabilitySpec, ModelArtifact
from xferbench.features.context import OriginContext

PREDICTION_COLUMNS = [
    "request_id",
    "horizon_week",
    "forecast_week",
    "point_units",
    "raw_point_units",
    "status",
    "reason",
    "rate_level",
    "season_level",
]


@dataclass(frozen=True)
class TrainingContext:
    """Permitted training data for one fit. Labels are evaluator-provided and availability-checked."""

    requests: pd.DataFrame
    labels: pd.DataFrame
    fit_cutoff: pd.Timestamp
    data_hash: str
    context_for: Callable[[str], OriginContext]

    @property
    def n_launches(self) -> int:
        return len(self.requests)


@runtime_checkable
class Method(Protocol):
    def capabilities(self) -> CapabilitySpec: ...

    def variants(self) -> list[dict[str, Any]]: ...

    def fit(
        self, training: TrainingContext, inner_validation: TrainingContext | None, config: dict[str, Any]
    ) -> ModelArtifact: ...

    def predict_batch(self, requests: pd.DataFrame, ctx: OriginContext, artifact: ModelArtifact) -> pd.DataFrame: ...


def varying_keys(grid: list[dict[str, Any]]) -> list[str]:
    keys = sorted({k for c in grid for k in c})
    return [k for k in keys if len({repr(c.get(k)) for c in grid}) > 1]


def variant_id(method_id: str, config: dict[str, Any], grid: list[dict[str, Any]] | None = None) -> str:
    """Readable ID naming only the parameters that vary across the method's declared grid."""
    keys = varying_keys(grid) if grid is not None else sorted(config)
    if not keys:
        return method_id
    return f"{method_id}[{','.join(f'{k}={config.get(k)}' for k in keys)}]"


def stateless_artifact(
    spec: CapabilitySpec,
    training: TrainingContext,
    config: dict[str, Any],
    notes: str,
    grid: list[dict[str, Any]] | None = None,
) -> ModelArtifact:
    return ModelArtifact(
        method_id=spec.method_id,
        variant_id=variant_id(spec.method_id, config, grid),
        method_version=spec.version,
        config=config,
        params={},
        fit_cutoff=training.fit_cutoff.date().isoformat(),
        n_training_launches=training.n_launches,
        training_data_hash=training.data_hash,
        notes=notes,
    )


@dataclass
class RowResult:
    """Forecast for one request: 52 values, or None with a failure reason."""

    request_id: str
    values: np.ndarray | None
    status: str
    reason: str = ""
    raw: np.ndarray | None = None
    rate_level: str = ""  # shared hierarchy level of the rate (item/subcategory/product_type/propensity/...)
    season_level: str = ""  # shared hierarchy level of the seasonal profile (category/product_type/flat)


def expand(requests: pd.DataFrame, results: Sequence[RowResult], horizon: int) -> pd.DataFrame:
    by_id = {r.request_id: r for r in results}
    frames = []
    hw = np.arange(1, horizon + 1)
    for req in requests.itertuples(index=False):
        res = by_id.get(req.request_id) or RowResult(req.request_id, None, "failed", "adapter returned no result")
        vals = np.full(horizon, np.nan) if res.values is None else np.asarray(res.values, dtype=float)
        raw = vals if res.raw is None else np.asarray(res.raw, dtype=float)
        frames.append(
            pd.DataFrame(
                {
                    "request_id": req.request_id,
                    "horizon_week": hw,
                    "forecast_week": [req.origin + WEEK * (h - 1) for h in hw],
                    "point_units": vals,
                    "raw_point_units": raw,
                    "status": res.status,
                    "reason": res.reason,
                    "rate_level": res.rate_level,
                    "season_level": res.season_level,
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=PREDICTION_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def join_reasons(*parts: str) -> str:
    return "; ".join(p for p in parts if p)
