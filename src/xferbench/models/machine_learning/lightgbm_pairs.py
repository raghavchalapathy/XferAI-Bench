"""M4.lightgbm: pooled gradient-boosted tree on origin-built cold-pair features (optional extra `lightgbm`).

LightGBM is imported lazily inside ``fit``/``predict_batch``; the package imports and every other method run
without it. Features come only from the request's OriginContext (the same origin-scoped aggregates the
transparent baselines use); no own-pair lags exist for a cold pair. Training rows come only from fit
launches, and labels dated on or after the fit cutoff are dropped defensively.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from xferbench.contracts.methods import CapabilitySpec, ModelArtifact, Rights
from xferbench.data_preparation.feature_engineering.aggregates import profile_for_item
from xferbench.data_preparation.feature_engineering.context import OriginContext
from xferbench.data_preparation.feature_engineering.hierarchy import profile_for_item as hier_profile
from xferbench.data_preparation.feature_engineering.hierarchy import rate_for_item
from xferbench.models.base import RowResult, TrainingContext, expand
from xferbench.models.stats.rates import _forecast_weeks, _target_households, national_level, propensity

VERSION = "1.0.0"
LGBM_PARAMS: dict[str, Any] = {
    "objective": "poisson",
    "learning_rate": 0.05,
    "num_leaves": 15,
    "min_data_in_leaf": 20,
    "feature_fraction": 0.9,
    "bagging_fraction": 1.0,
    "lambda_l2": 1.0,
    "seed": 0,
    "deterministic": True,
    "num_threads": 1,
    "verbose": -1,
}
NUM_ROUNDS = 200
BASE_FEATURES = ["log_h", "log_b0", "log_m1", "has_p", "season", "horizon_week", "week_of_year"]


def pair_features(ctx: OriginContext, req: Any, horizon: int) -> pd.DataFrame | None:
    """One row per horizon week for one request, built from origin-scoped data only. None if H unknown."""
    hh = _target_households(ctx, req.fpg_id)
    if hh is None:
        return None
    b0, _, _ = national_level(ctx, req)
    p, _ = propensity(ctx, req)
    weeks = _forecast_weeks(req.origin, horizon)
    s = profile_for_item(ctx, req.item_id).at(weeks)
    loc = ctx.locations.set_index("fpg_id")
    shares = {c: float(loc[c].get(req.fpg_id, np.nan)) for c in ctx.share_columns if c in loc.columns}
    df = pd.DataFrame(
        {
            "log_h": np.log1p(hh),
            "log_b0": np.log1p(b0) if b0 is not None else np.nan,
            "log_m1": np.log1p(hh * p) if p is not None else np.nan,
            "has_p": float(p is not None),
            "season": np.asarray(s, dtype=float),
            "horizon_week": np.arange(1, horizon + 1, dtype=float),
            "week_of_year": [float(w.isocalendar()[1]) for w in weeks],
        }
    )
    for c, v in shares.items():
        df[f"share_{c}"] = v
    return df


class M4LightGBM:
    spec = CapabilitySpec(
        method_id="M4.lightgbm",
        version=VERSION,
        family="boosting",
        display_name="Global LightGBM (Poisson) on origin-built pair features",
        task_profiles=["retail_pair_zero_v1"],
        board="cold_c0",
        identity="native",
        min_own_pair_history_weeks=0,
        min_donor_history_weeks=1,
        supports_new_location=True,
        point_statistic="mean",
        compute="cpu-light",
        optional_extra="lightgbm",
        python_modules=["lightgbm"],
        rights=Rights(
            code_license="MIT",
            code_source="https://github.com/lightgbm-org/LightGBM (installed package; adapter code Apache-2.0)",
            notes="No pretrained weights; model trained locally on the fit launches.",
        ),
        used_features=[
            "households",
            "national item rate (B0 level)",
            "propensity P (M1 level, if present)",
            "mean-one seasonal profile",
            "horizon week",
            "week of year",
            "demographic shares",
        ],
        history_rules="Zero own-pair history; features from origin-scoped donor/national aggregates only; trained "
        "on fit launches with labels before the fit cutoff.",
        description="Pooled Poisson GBT over (launch, horizon week) rows; no own-pair lags; deterministic seed.",
    )

    def __init__(self) -> None:
        self._booster: Any = None
        self._feature_names: list[str] = []

    def capabilities(self) -> CapabilitySpec:
        return self.spec

    def variants(self) -> list[dict[str, Any]]:
        return [{}]

    def _matrix(self, frames: list[pd.DataFrame]) -> pd.DataFrame:
        X = pd.concat(frames, ignore_index=True)
        return X.reindex(columns=self._feature_names)

    def fit(
        self, training: TrainingContext, inner_validation: TrainingContext | None, config: dict[str, Any]
    ) -> ModelArtifact:
        import lightgbm as lgb

        horizon = None
        labels = training.labels
        if len(labels):
            labels = labels[labels["measured"] & (labels["forecast_week"] < training.fit_cutoff)]
        frames, ys = [], []
        for req in training.requests.itertuples(index=False):
            ctx = training.context_for(req.request_id)
            horizon = ctx.metadata.time.horizon_weeks
            f = pair_features(ctx, req, horizon)
            lab = labels[labels["request_id"] == req.request_id] if len(labels) else labels
            if f is None or lab.empty:
                continue
            f = f.assign(_hw=np.arange(1, horizon + 1))
            m = f.merge(lab[["horizon_week", "actual"]], left_on="_hw", right_on="horizon_week", how="inner")
            frames.append(
                m.drop(columns=["_hw", "horizon_week_y", "actual"]).rename(columns={"horizon_week_x": "horizon_week"})
            )
            ys.append(m["actual"].to_numpy(dtype=float))
        if not frames:
            raise ValueError("no labelled training rows available before the fit cutoff")
        X = pd.concat(frames, ignore_index=True)
        self._feature_names = list(X.columns)
        y = np.concatenate(ys)
        self._booster = lgb.train(dict(LGBM_PARAMS), lgb.Dataset(X, label=y), num_boost_round=NUM_ROUNDS)
        return ModelArtifact(
            method_id=self.spec.method_id,
            variant_id=self.spec.method_id,
            method_version=VERSION,
            config=dict(config),
            params={
                "lgbm_params": LGBM_PARAMS,
                "num_boost_round": NUM_ROUNDS,
                "features": self._feature_names,
                "n_rows": len(y),
                "lightgbm_version": lgb.__version__,
            },
            fit_cutoff=training.fit_cutoff.date().isoformat(),
            n_training_launches=training.n_launches,
            training_data_hash=training.data_hash,
            notes="Model kept in memory for this run; params record the exact training configuration.",
        )

    def predict_batch(self, requests: pd.DataFrame, ctx: OriginContext, artifact: ModelArtifact) -> pd.DataFrame:
        h = ctx.metadata.time.horizon_weeks
        results = []
        for req in requests.itertuples(index=False):
            f = pair_features(ctx, req, h)
            if f is None or self._booster is None:
                results.append(RowResult(req.request_id, None, "failed", "target households unknown at origin"))
                continue
            pred = np.clip(self._booster.predict(self._matrix([f])), 0, None)
            results.append(
                RowResult(
                    req.request_id,
                    pred,
                    "success",
                    rate_level=rate_for_item(ctx, req.item_id).level,
                    season_level=hier_profile(ctx, req.item_id).level,
                )
            )
        return expand(requests, results, h)
