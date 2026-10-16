"""Hand-calculated checks for B0, B1, B2, B3, the raw-units ablation, M1 and M2 (see tests/handmade.py)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from tests import handmade as hm
from xferbench.features.aggregates import national_rates, pair_rates, seasonal_profiles
from xferbench.features.context import ContextBuilder, Exclusions
from xferbench.methods.base import TrainingContext
from xferbench.methods.baselines.rates import (
    B0NationalRate,
    B1NationalSeasonal,
    B2AnalogRate,
    B2RawUnits,
    B3AnalogRate,
    M1FlatRule,
    M2SeasonalRule,
)

EXCL = Exclusions(fpgs=frozenset({"X"}))


def _training() -> TrainingContext:
    return TrainingContext(
        requests=pd.DataFrame(),
        labels=pd.DataFrame(),
        fit_cutoff=hm.ORIGIN,
        data_hash="hand",
        context_for=lambda _: None,
    )  # type: ignore[arg-type,return-value]


def _predict(method, config: dict | None = None, item: str = "I1", **build_kw) -> pd.DataFrame:  # type: ignore[no-untyped-def]
    ds = hm.build(**build_kw)
    ctx = ContextBuilder(ds, EXCL).at(hm.ORIGIN)
    cfg = config if config is not None else method.variants()[0]
    art = method.fit(_training(), None, cfg)
    return method.predict_batch(hm.request(item), ctx, art)


def _predict_ds(method, config: dict, ds) -> pd.DataFrame:  # type: ignore[no-untyped-def]
    ctx = ContextBuilder(ds, EXCL).at(hm.ORIGIN)
    return method.predict_batch(hm.request(), ctx, method.fit(_training(), None, config))


def _weights() -> tuple[float, float]:
    d1 = 0.25 * abs(math.log(100 / 80))
    d2 = math.sqrt(0.2**2 + 0.2**2) / math.sqrt(2) + 0.25 * abs(math.log(300 / 80)) + 0.25
    return 1 / (d1 + 0.05), 1 / (d2 + 0.05)


S = hm.m(hm.FORECAST_WEEKS)


def test_context_drops_late_future_and_excluded_rows() -> None:
    ctx = ContextBuilder(hm.build(), EXCL).at(hm.ORIGIN)
    obs = ctx.observations
    assert obs["week_start"].max() == pd.Timestamp("2023-12-18")
    assert (obs["units"] < 500).all()
    assert "X" not in set(obs["fpg_id"])
    assert ctx.feature("propensity_rate")["value"].tolist() == [0.02]


def test_pair_and_national_rates() -> None:
    ctx = ContextBuilder(hm.build(), EXCL).at(hm.ORIGIN)
    pr = pair_rates(ctx).set_index(["item_id", "fpg_id"])
    assert pr.loc[("I1", "D1"), "rate"] == pytest.approx(0.02)
    assert pr.loc[("I1", "D2"), "rate"] == pytest.approx(0.01)
    assert not pr.loc[("I2", "D2"), "consistent"]
    nr = national_rates(ctx)
    assert nr["I1"].rate == pytest.approx(0.0125)
    assert nr["I1"].footprint == "consistent"
    assert nr["I2"].footprint == "all_measured"
    assert nr["I2"].rate == pytest.approx(40 / (300 * 10))


def test_seasonal_profile_is_mean_one_and_calendar_aligned() -> None:
    ctx = ContextBuilder(hm.build(), EXCL).at(hm.ORIGIN)
    prof = seasonal_profiles(ctx)["C1"]
    assert prof.status == "estimated"
    assert prof.values.mean() == pytest.approx(1.0)
    np.testing.assert_allclose(prof.at(list(hm.FORECAST_WEEKS)), S)
    assert seasonal_profiles(ctx)["C2"].status == "flat_fallback"


def test_b0_flat_national_rate() -> None:
    out = _predict(B0NationalRate())
    assert len(out) == 52
    np.testing.assert_allclose(out["point_units"], 1.0)
    assert set(out["status"]) == {"success"}


def test_b0_without_exclusion_would_be_contaminated() -> None:
    ds = hm.build()
    ctx = ContextBuilder(ds, Exclusions()).at(hm.ORIGIN)
    assert national_rates(ctx)["I1"].rate > 0.0125 * 10


def test_b1_applies_seasonal_profile_once() -> None:
    out = _predict(B1NationalSeasonal())
    np.testing.assert_allclose(out["point_units"], 1.0 * S)
    assert out["point_units"].sum() == pytest.approx(52.0)


def test_b0_b1_fallback_is_visible() -> None:
    out = _predict(B1NationalSeasonal(), item="I2")
    assert set(out["status"]) == {"fallback"}
    assert "consistently exposed" in out["reason"].iloc[0]
    assert "flat seasonal profile" in out["reason"].iloc[0]
    np.testing.assert_allclose(out["point_units"], 80 * 40 / 3000)


@pytest.mark.parametrize("kappa", [1.0, 4.0])
def test_b3_shrunk_analog_rate(kappa: float) -> None:
    cfg = next(c for c in B3AnalogRate().variants() if c["k"] == 3 and c["kappa"] == kappa)
    out = _predict(B3AnalogRate(), cfg)
    w1, w2 = _weights()
    r_analog = (w1 * 0.02 + w2 * 0.01) / (w1 + w2)
    r = (2 * r_analog + kappa * 0.0125) / (2 + kappa)
    np.testing.assert_allclose(out["point_units"], 80 * r * S)
    assert set(out["status"]) == {"success"}


def test_b2_household_adjusted_no_shrinkage() -> None:
    cfg = next(c for c in B2AnalogRate().variants() if c["k"] == 3)
    assert "kappa" not in cfg
    out = _predict(B2AnalogRate(), cfg)
    w1, w2 = _weights()
    np.testing.assert_allclose(out["point_units"], 80 * (w1 * 0.02 + w2 * 0.01) / (w1 + w2) * S)
    assert set(out["status"]) == {"success"}


def test_b2_scales_with_target_households() -> None:
    from xferbench.data.io import Dataset

    cfg = next(c for c in B2AnalogRate().variants() if c["k"] == 3)
    ds = hm.build()
    base = _predict_ds(B2AnalogRate(), cfg, ds)
    t = {k: v.copy() for k, v in ds.tables.items()}
    loc = t["locations"]
    loc.loc[loc["fpg_id"] == "T", "households"] = loc.loc[loc["fpg_id"] == "T", "households"] * 2
    doubled = _predict_ds(B2AnalogRate(), cfg, Dataset(ds.metadata, ds.base_dir, t))
    # households also enter the similarity distance, so recompute the weights for H_target = 160
    d1 = 0.25 * abs(math.log(100 / 160))
    d2 = math.sqrt(0.2**2 + 0.2**2) / math.sqrt(2) + 0.25 * abs(math.log(300 / 160)) + 0.25
    w1, w2 = 1 / (d1 + 0.05), 1 / (d2 + 0.05)
    np.testing.assert_allclose(doubled["point_units"], 160 * (w1 * 0.02 + w2 * 0.01) / (w1 + w2) * S)
    assert (doubled["point_units"].to_numpy() > 1.5 * base["point_units"].to_numpy()).all()


@pytest.mark.parametrize("cls", [B2AnalogRate, B3AnalogRate])
def test_b2_b3_fall_back_to_b1_without_donors(cls) -> None:  # type: ignore[no-untyped-def]
    out = _predict(cls(), item="I2")
    assert set(out["status"]) == {"fallback"}
    assert out["reason"].iloc[0].startswith("B1 fallback")


def test_b2_raw_units_ablation() -> None:
    cfg = next(c for c in B2RawUnits().variants() if c["k"] == 3)
    out = _predict(B2RawUnits(), cfg)
    w1, w2 = _weights()
    np.testing.assert_allclose(out["point_units"], (w1 * 2 + w2 * 3) / (w1 + w2) * S)


def test_m1_and_m2_business_rules_use_origin_snapshot() -> None:
    np.testing.assert_allclose(_predict(M1FlatRule())["point_units"], 80 * 0.02)
    np.testing.assert_allclose(_predict(M2SeasonalRule())["point_units"], 80 * 0.02 * S)


def test_m1_missing_propensity_fails_visibly() -> None:
    out = _predict(M1FlatRule(), propensity=None)
    assert set(out["status"]) == {"failed"}
    assert out["point_units"].isna().all()
    assert "missing feature" in out["reason"].iloc[0]
