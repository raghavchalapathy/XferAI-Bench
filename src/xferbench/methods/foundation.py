"""Licence-pinned donor-prior composites: Chronos-2, Chronos-Bolt, TimesFM 2.5 and GluonTS DeepAR (count).

Status: licence-pinned, not Reviewer-recommended for PAIR0. Code and HF weight revisions come from R3 pins.v2,
which is still pending Reviewer review.

Recipe (donor_only composite, never a native C0 claim): the backend forecasts the item's *donor/national*
weekly rate per household, built only from the request's OriginContext (same-item observations at donor FPGs
up to the latest usable week; held-out pairs and the stage's new FPGs are already excluded). The target pair
has no history and is never given fabricated history. The rate forecast is then allocated to the target FPG
by multiplying by its households.

Heavy packages (torch, chronos, timesfm, gluonts) are imported lazily inside the backend only. Model weights
are loaded from the local Hugging Face cache only (``local_files_only=True``) unless the user sets
``XFERBENCH_ALLOW_WEIGHT_DOWNLOAD=1``; nothing is downloaded on import, in tests or in the demo. The real
backend calls follow each library's documentation and are untested here (documented-only).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import pandas as pd

from xferbench.contracts.methods import CapabilitySpec, ModelArtifact, Rights
from xferbench.features.context import OriginContext
from xferbench.methods.base import RowResult, TrainingContext, expand, stateless_artifact
from xferbench.methods.baselines.rates import _target_households

VERSION = "0.1.0"
STATUS_LABEL = "licence-pinned, not Reviewer-recommended for PAIR0"
PINS_NOTE = "revisions from R3 pins.v2 (PROPOSAL_PENDING_R4_REVIEW)"
MIN_CONTEXT_WEEKS = 8
MAX_CONTEXT_WEEKS = 156
CHRONOS_CODE = "1224fafa91e1ecd6674f5204066b159e40b5e4a1"
TIMESFM_CODE = "e51928e27119cb17bebc005be2696b75e0a9e688"
GLUONTS_CODE = "d60556ca71167a3ec1ea807b491dd982d1de2112"
CHRONOS_WEIGHTS = {
    "amazon/chronos-2": "29ec3766d36d6f73f0696f85560a422f50e8498c",
    "amazon/chronos-bolt-tiny": "a0e552de83495b5c28c14c71c374f3e33280b340",
    "amazon/chronos-bolt-mini": "251268337516a88e253628c43e1d26ec577b376b",
    "amazon/chronos-bolt-small": "772f3d25d38aec6d914c8949dab4462e2d46f5d8",
    "amazon/chronos-bolt-base": "5d9f166d69f47aef3401367a7b842e78fe97b121",
}
TIMESFM_WEIGHTS = {"google/timesfm-2.5-200m-pytorch": "1d952420fba87f3c6dee4f240de0f1a0fbc790e3"}


class ExtraMissingError(ImportError):
    """The optional extra for this adapter is not installed."""


@dataclass(frozen=True)
class DonorSeries:
    """Weekly donor/national series of one item, origin-scoped. ``units`` and ``households`` per week."""

    item_id: str
    weeks: pd.DatetimeIndex
    units: np.ndarray
    households: np.ndarray

    @property
    def rate(self) -> np.ndarray:
        return self.units / self.households


class ForecastBackend(Protocol):
    def fit(self, series: list[DonorSeries], horizon: int) -> None: ...

    def forecast(self, series: list[DonorSeries], horizon: int) -> list[np.ndarray]:
        """Point forecast of the weekly rate per household, one array of length ``horizon`` per series."""
        ...


def donor_series(ctx: OriginContext, item_id: str, max_weeks: int = MAX_CONTEXT_WEEKS) -> DonorSeries | None:
    """Same-item weekly units / households over measured donor pairs, up to the latest usable week only."""
    obs = ctx.observations
    last = ctx.latest_usable_week
    o = obs[(obs["item_id"] == item_id) & obs["units"].notna() & (obs["week_start"] <= last)]
    if o.empty:
        return None
    hh = ctx.locations.set_index("fpg_id")["households"]
    o = o.assign(hh=o["fpg_id"].map(hh).astype(float))
    o = o[o["hh"].notna() & (o["hh"] > 0)]
    g = o.groupby("week_start", sort=True).agg(units=("units", "sum"), hh=("hh", "sum"))
    if g.empty:
        return None
    idx = pd.date_range(g.index.min(), last, freq="7D")
    g = g.reindex(idx).tail(max_weeks)
    g = g[g["hh"].notna().cummax()]
    if g["hh"].notna().sum() < MIN_CONTEXT_WEEKS:
        return None
    g["hh"] = g["hh"].ffill()
    g["units"] = g["units"].fillna(0.0)
    return DonorSeries(item_id, pd.DatetimeIndex(g.index), g["units"].to_numpy(float), g["hh"].to_numpy(float))


def _require(module: str, extra: str) -> Any:
    import importlib

    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ExtraMissingError(
            f"'{module}' is not installed; install the '{extra}' extra (pip install -e \".[{extra}]\")"
        ) from exc


def _hf_kwargs(revision: str) -> dict[str, Any]:
    allow = os.environ.get("XFERBENCH_ALLOW_WEIGHT_DOWNLOAD") == "1"
    return {"revision": revision, "local_files_only": not allow}


class ChronosBackend:
    """Documented-only: chronos-forecasting BaseChronosPipeline (Chronos-2 / Chronos-Bolt), CPU, median."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.revision = CHRONOS_WEIGHTS[model_id]
        self._pipe: Any = None

    def fit(self, series: list[DonorSeries], horizon: int) -> None:
        chronos = _require("chronos", "foundation")
        self._pipe = chronos.BaseChronosPipeline.from_pretrained(
            self.model_id, device_map="cpu", **_hf_kwargs(self.revision)
        )

    def forecast(self, series: list[DonorSeries], horizon: int) -> list[np.ndarray]:
        torch = _require("torch", "foundation")
        if self._pipe is None:
            self.fit(series, horizon)
        q, _mean = self._pipe.predict_quantiles(
            [torch.tensor(s.rate, dtype=torch.float32) for s in series],
            prediction_length=horizon,
            quantile_levels=[0.5],
        )
        return [np.asarray(x, dtype=float).reshape(horizon, -1)[:, 0] for x in q]


class TimesFMBackend:
    """Documented-only: timesfm 2.5 (TimesFM_2p5_200M_torch), CPU, point forecast."""

    def __init__(self, model_id: str = "google/timesfm-2.5-200m-pytorch") -> None:
        self.model_id = model_id
        self.revision = TIMESFM_WEIGHTS[model_id]
        self._model: Any = None

    def fit(self, series: list[DonorSeries], horizon: int) -> None:
        timesfm = _require("timesfm", "timesfm")
        m = timesfm.TimesFM_2p5_200M_torch.from_pretrained(self.model_id, **_hf_kwargs(self.revision))
        m.compile(timesfm.ForecastConfig(max_context=MAX_CONTEXT_WEEKS, max_horizon=max(horizon, 64)))
        self._model = m

    def forecast(self, series: list[DonorSeries], horizon: int) -> list[np.ndarray]:
        if self._model is None:
            self.fit(series, horizon)
        point, _q = self._model.forecast(horizon=horizon, inputs=[s.rate for s in series])
        return [np.asarray(p, dtype=float)[:horizon] for p in point]


class DeepARCountBackend:
    """Documented-only: GluonTS torch DeepAR with a negative-binomial likelihood, trained locally (no weights)
    on donor/national unit counts of the fit launches' items; rate = forecast units / last donor households."""

    def __init__(self, max_epochs: int = 5) -> None:
        self.max_epochs = max_epochs
        self._predictor: Any = None

    @staticmethod
    def _entries(series: list[DonorSeries]) -> list[dict[str, Any]]:
        return [
            {"start": pd.Period(s.weeks[0], freq="W"), "target": s.units.astype(float), "item_id": s.item_id}
            for s in series
        ]

    def fit(self, series: list[DonorSeries], horizon: int) -> None:
        _require("torch", "neural")
        _require("gluonts", "neural")
        from gluonts.dataset.common import ListDataset  # type: ignore[import-not-found]
        from gluonts.torch.distributions import NegativeBinomialOutput  # type: ignore[import-not-found]
        from gluonts.torch.model.deepar import DeepAREstimator  # type: ignore[import-not-found]

        est = DeepAREstimator(
            prediction_length=horizon,
            freq="W",
            distr_output=NegativeBinomialOutput(),
            trainer_kwargs={"max_epochs": self.max_epochs, "accelerator": "cpu", "enable_progress_bar": False},
        )
        self._predictor = est.train(ListDataset(self._entries(series), freq="W"))

    def forecast(self, series: list[DonorSeries], horizon: int) -> list[np.ndarray]:
        from gluonts.dataset.common import ListDataset  # type: ignore[import-not-found]

        if self._predictor is None:
            raise RuntimeError("DeepAR backend used before fit")
        out = []
        for s, f in zip(series, self._predictor.predict(ListDataset(self._entries(series), freq="W")), strict=True):
            out.append(np.asarray(f.mean, dtype=float)[:horizon] / float(s.households[-1]))
        return out


def _rights(code: str, revision: str, weights: str, weights_revision: str | None) -> Rights:
    return Rights(
        code_license="Apache-2.0",
        code_source=code,
        code_revision=f"{revision} (R3 pin)",
        weights=weights,
        weights_revision=weights_revision,
        notes=f"{STATUS_LABEL}; {PINS_NOTE}; real backend documented-only (untested here)",
    )


class DonorPriorComposite:
    """Backend forecast of the donor/national rate per household x target households."""

    spec: CapabilitySpec
    trains_backend: bool = False

    def __init__(self, backend: ForecastBackend | None = None) -> None:
        self._backend = backend

    def capabilities(self) -> CapabilitySpec:
        return self.spec

    def variants(self) -> list[dict[str, Any]]:
        return [{}]

    def make_backend(self, config: dict[str, Any]) -> ForecastBackend:
        raise NotImplementedError

    def backend(self, config: dict[str, Any]) -> ForecastBackend:
        if self._backend is None:
            self._backend = self.make_backend(config)
        return self._backend

    def fit(
        self, training: TrainingContext, inner_validation: TrainingContext | None, config: dict[str, Any]
    ) -> ModelArtifact:
        be = self.backend(config)
        if self.trains_backend:
            series, horizon = [], 0
            seen: set[str] = set()
            for req in training.requests.itertuples(index=False):
                if req.item_id in seen:
                    continue
                ctx = training.context_for(req.request_id)
                horizon = ctx.metadata.time.horizon_weeks
                s = donor_series(ctx, req.item_id)
                if s is not None:
                    series.append(s)
                    seen.add(req.item_id)
            if not series:
                raise ValueError("no origin-valid donor series in the fit launches")
            be.fit(series, horizon)
        return stateless_artifact(
            self.spec,
            training,
            config,
            f"{STATUS_LABEL}. Donor-prior composite; "
            + ("backend trained on fit-launch donor series." if self.trains_backend else "zero-shot backend."),
            self.variants(),
        )

    def predict_batch(self, requests: pd.DataFrame, ctx: OriginContext, artifact: ModelArtifact) -> pd.DataFrame:
        h = ctx.metadata.time.horizon_weeks
        be = self.backend(artifact.config)
        results: list[RowResult] = []
        todo: dict[str, DonorSeries] = {}
        for item in requests["item_id"].unique():
            s = donor_series(ctx, str(item))
            if s is not None:
                todo[str(item)] = s
        fc = dict(zip(todo, be.forecast(list(todo.values()), h), strict=True)) if todo else {}
        for req in requests.itertuples(index=False):
            hh = _target_households(ctx, req.fpg_id)
            if hh is None:
                results.append(RowResult(req.request_id, None, "failed", "target households unknown at origin"))
                continue
            r = fc.get(req.item_id)
            if r is None:
                results.append(
                    RowResult(req.request_id, None, "failed", f"fewer than {MIN_CONTEXT_WEEKS} donor weeks at origin")
                )
                continue
            results.append(RowResult(req.request_id, np.clip(np.asarray(r, float), 0, None) * hh, "success"))
        return expand(requests, results, h)


def _spec(method_id: str, name: str, extra: str, modules: list[str], rights: Rights, desc: str) -> CapabilitySpec:
    return CapabilitySpec(
        method_id=method_id,
        version=VERSION,
        family="foundation" if method_id.startswith("FM.") else "neural",
        display_name=f"{name} [{STATUS_LABEL}]",
        task_profiles=["retail_pair_zero_v1"],
        board="donor_only",
        identity="composite",
        min_own_pair_history_weeks=0,
        min_donor_history_weeks=MIN_CONTEXT_WEEKS,
        supports_new_location=True,
        point_statistic="median" if method_id.startswith("FM.") else "mean",
        compute="cpu-heavy",
        optional_extra=extra,
        python_modules=modules,
        rights=rights,
        used_features=["households", "same-item donor/national weekly units and households (origin-scoped)"],
        history_rules="Donor/national history only, up to the latest usable week at origin; the target pair is "
        "never given fabricated history. Prior then allocation by target households.",
        description=desc,
    )


CHRONOS_SRC = "https://github.com/amazon-science/chronos-forecasting"


class FMChronos2(DonorPriorComposite):
    spec = _spec(
        "FM.chronos2",
        "Chronos-2 donor prior x households",
        "foundation",
        ["chronos", "torch"],
        _rights(CHRONOS_SRC, CHRONOS_CODE, "amazon/chronos-2 (Apache-2.0)", CHRONOS_WEIGHTS["amazon/chronos-2"]),
        "Zero-shot Chronos-2 median forecast of the item's donor rate, allocated by target households.",
    )

    def make_backend(self, config: dict[str, Any]) -> ForecastBackend:
        return ChronosBackend("amazon/chronos-2")


BOLT = [m for m in CHRONOS_WEIGHTS if "bolt" in m]


class FMChronosBolt(DonorPriorComposite):
    spec = _spec(
        "FM.chronos_bolt",
        "Chronos-Bolt donor prior x households (tiny/mini/small/base)",
        "foundation",
        ["chronos", "torch"],
        _rights(
            CHRONOS_SRC,
            CHRONOS_CODE,
            "amazon/chronos-bolt-{tiny,mini,small,base} (Apache-2.0)",
            "; ".join(f"{m.split('/')[1]}={CHRONOS_WEIGHTS[m]}" for m in BOLT),
        ),
        "Zero-shot Chronos-Bolt median forecast of the item's donor rate; size chosen on validation.",
    )

    def variants(self) -> list[dict[str, Any]]:
        return [{"model": m.split("/")[1]} for m in BOLT]

    def make_backend(self, config: dict[str, Any]) -> ForecastBackend:
        return ChronosBackend(f"amazon/{config.get('model', 'chronos-bolt-base')}")


class FMTimesFM25(DonorPriorComposite):
    spec = _spec(
        "FM.timesfm25",
        "TimesFM 2.5 (200m) donor prior x households",
        "timesfm",
        ["timesfm", "torch"],
        _rights(
            "https://github.com/google-research/timesfm",
            TIMESFM_CODE,
            "google/timesfm-2.5-200m-pytorch (Apache-2.0)",
            TIMESFM_WEIGHTS["google/timesfm-2.5-200m-pytorch"],
        ),
        "Zero-shot TimesFM 2.5 point forecast of the item's donor rate; pinned checkpoint, never replaced.",
    )

    def make_backend(self, config: dict[str, Any]) -> ForecastBackend:
        return TimesFMBackend()


class M6DeepARCount(DonorPriorComposite):
    trains_backend = True
    spec = _spec(
        "M6.deepar_count",
        "GluonTS DeepAR (negative binomial) donor prior x households",
        "neural",
        ["gluonts", "torch"],
        Rights(
            code_license="Apache-2.0",
            code_source="https://github.com/awslabs/gluonts",
            code_revision=f"{GLUONTS_CODE} (R3 pin)",
            notes=f"{STATUS_LABEL}; {PINS_NOTE}; no pretrained weights (trained locally); "
            "real backend documented-only (untested here)",
        ),
        "DeepAR trained locally on fit-launch donor unit series; forecast rate x target households.",
    )

    def make_backend(self, config: dict[str, Any]) -> ForecastBackend:
        return DeepARCountBackend()
