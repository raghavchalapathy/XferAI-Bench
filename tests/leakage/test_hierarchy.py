"""Shared retail hierarchy: rate item -> subcategory -> product_type; season category -> product_type.

Every fallback step is exercised on a small hand-built dataset, each level is checked for origin-only data,
and the level used is recorded in forecasts and the run manifest.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests import handmade as hm
from xferbench.data.io import Dataset
from xferbench.data_preparation.feature_engineering.context import ContextBuilder, Exclusions
from xferbench.data_preparation.feature_engineering.hierarchy import profile_for_item, rate_for_item
from xferbench.models.base import TrainingContext
from xferbench.models.foundation_models.donor_prior import donor_series
from xferbench.models.stats.rates import B0NationalRate, B1NationalSeasonal, M2SeasonalRule
from xferbench.util import read_json

EXCL = Exclusions(fpgs=frozenset({"X"}))
FPGS = ["D1", "D2", "D3", "D4"]

# items: (item_id, subcategory, category, product_type, donor FPGs with full history, units per week)
ITEMS = [
    ("A1", "s1", "c1", "p", FPGS[:3], 2.0),  # history; subcategory s1 has 3 donor FPGs
    ("A2", "s1", "c1", "p", [], 0.0),  # no history -> subcategory s1
    ("B1", "s2", "c2", "p", FPGS[:1], 4.0),  # history at 1 FPG only
    ("B2", "s2", "c2", "p", [], 0.0),  # no history; s2 has 1 donor FPG (< 3) -> product type p
    ("C1", "s3", "c3", "q", [], 0.0),  # no history anywhere in s3 or q -> none
]


def build(min_rate_fpgs: int = 3, min_season_items: int = 2, drop_subcategory: bool = False) -> Dataset:
    base = hm.build(min_season_items=min_season_items)
    md = base.metadata.model_copy(deep=True)
    md.features.hierarchy.min_rate_support_fpgs = min_rate_fpgs
    obs = []
    weeks = pd.date_range(hm.WINDOW[0] - pd.Timedelta(days=7 * 52), hm.WINDOW[-1], freq="7D")
    for it, _s, c, _p, fpgs, u in ITEMS:
        amp = 1.0 if c == "c1" else 0.0
        for f in fpgs:
            obs.append(hm._obs(it, f, weeks, u * (1 + amp * (hm.m(weeks) - 1))))
    o = pd.concat(obs, ignore_index=True)
    future = pd.date_range(hm.ORIGIN, periods=20, freq="7D")
    o = pd.concat([o, hm._obs("A2", "D1", future, np.full(len(future), 1e5))], ignore_index=True)  # post-origin
    items = pd.DataFrame(
        {
            "item_id": [i[0] for i in ITEMS],
            "category": [i[2] for i in ITEMS],
            "product_type": [i[3] for i in ITEMS],
            "seasonality_class": "seasonal",
            "effective_from": hm.EARLY,
            "known_at": hm.EARLY,
        }
    )
    if not drop_subcategory:
        items["subcategory"] = [i[1] for i in ITEMS]
    loc = base.tables["locations"]
    extra = loc[loc["fpg_id"] == "D2"].assign(fpg_id="D3")
    extra4 = loc[loc["fpg_id"] == "D2"].assign(fpg_id="D4")
    loc = pd.concat([loc, extra, extra4], ignore_index=True)
    offers = o[["item_id", "fpg_id", "week_start", "week_end", "known_at"]].assign(
        offer_state="offered", offered_days=7, available_days=7, exposure_fraction=1.0, stockout_state="in_stock"
    )
    tables = dict(base.tables, observations=o, items=items, locations=loc, offers=offers)
    return Dataset(md, Path("."), tables)


def ctx_of(ds: Dataset):  # type: ignore[no-untyped-def]
    return ContextBuilder(ds, EXCL).at(hm.ORIGIN)


def test_rate_level_item() -> None:
    lr = rate_for_item(ctx_of(build()), "A1")
    assert lr.level == "item" and lr.rate is not None


def test_rate_fallback_to_subcategory() -> None:
    ctx = ctx_of(build())
    lr = rate_for_item(ctx, "A2")
    assert lr.level == "subcategory" and "item: no origin-valid history" in lr.reason
    assert lr.rate == pytest.approx(rate_for_item(ctx, "A1").rate)  # s1's only history is A1


def test_rate_fallback_to_product_type_when_subcategory_sparse() -> None:
    ctx = ctx_of(build())
    lr = rate_for_item(ctx, "B2")
    assert lr.level == "product_type" and "subcategory: fewer than 3 donor FPGs" in lr.reason


def test_rate_subcategory_when_threshold_lowered() -> None:
    assert rate_for_item(ctx_of(build(min_rate_fpgs=1)), "B2").level == "subcategory"


def test_rate_skips_missing_subcategory_column() -> None:
    lr = rate_for_item(ctx_of(build(drop_subcategory=True)), "A2")
    assert lr.level == "product_type" and "subcategory: unknown at origin" in lr.reason


def test_rate_none_when_no_level_has_history() -> None:
    lr = rate_for_item(ctx_of(build()), "C1")
    assert lr.level == "none" and lr.rate is None
    out = B0NationalRate().predict_batch(hm.request("C1", "T"), ctx_of(build()), _art(B0NationalRate()))
    assert set(out["status"]) == {"failed"}


def test_season_category_level() -> None:
    p = profile_for_item(ctx_of(build(min_season_items=1)), "A1")
    assert p.level == "category" and p.status == "estimated"


def test_season_fallback_to_product_type_when_category_sparse() -> None:
    p = profile_for_item(ctx_of(build(min_season_items=2)), "A1")  # c1 has one item with history
    assert p.level == "product_type" and "1 item(s) < 2" in p.reason


def test_season_flat_when_no_level_supported() -> None:
    p = profile_for_item(ctx_of(build(min_season_items=5)), "A1")
    assert p.level == "flat" and p.status == "flat_fallback"


def test_each_level_is_origin_only() -> None:
    ds = build(min_season_items=1)
    fut = {k: v.copy() for k, v in ds.tables.items()}
    o = fut["observations"]
    late = o["week_start"] >= hm.ORIGIN - pd.Timedelta(days=7)
    o.loc[late, "units"] = o.loc[late, "units"] * 1000 + 7
    ds2 = Dataset(ds.metadata, ds.base_dir, fut)
    for item in ("A1", "A2", "B2"):
        a, b = rate_for_item(ctx_of(ds), item), rate_for_item(ctx_of(ds2), item)
        assert a.level == b.level and a.rate == pytest.approx(b.rate)
    for lv_build in (1, 2):
        d1, d2 = build(min_season_items=lv_build), None
        f2 = {k: v.copy() for k, v in d1.tables.items()}
        oo = f2["observations"]
        oo.loc[oo["week_start"] >= hm.ORIGIN - pd.Timedelta(days=7), "units"] *= 50
        d2 = Dataset(d1.metadata, d1.base_dir, f2)
        p1, p2 = profile_for_item(ctx_of(d1), "A1"), profile_for_item(ctx_of(d2), "A1")
        assert p1.level == p2.level
        np.testing.assert_allclose(p1.profile.values, p2.profile.values)
    s1, s2 = donor_series(ctx_of(ds), "A2"), donor_series(ctx_of(ds2), "A2")
    assert s1 is not None and s2 is not None and s1.level == "subcategory"
    np.testing.assert_allclose(s1.units, s2.units)


def _art(m):  # type: ignore[no-untyped-def]
    return m.fit(TrainingContext(pd.DataFrame(), pd.DataFrame(), hm.ORIGIN, "h", lambda _: None), None, m.variants()[0])  # type: ignore[arg-type,return-value]


def test_levels_recorded_in_forecast_rows() -> None:
    ctx = ctx_of(build(min_season_items=2))
    out = B1NationalSeasonal().predict_batch(hm.request("A2", "T"), ctx, _art(B1NationalSeasonal()))
    assert set(out["rate_level"]) == {"subcategory"} and set(out["season_level"]) == {"product_type"}
    assert set(out["status"]) == {"fallback"}
    m2 = M2SeasonalRule().predict_batch(hm.request("I1", "T"), ctx_of(hm.build()), _art(M2SeasonalRule()))
    assert set(m2["rate_level"]) <= {"propensity", ""}


def test_donor_prior_series_uses_hierarchy() -> None:
    ctx = ctx_of(build())
    assert donor_series(ctx, "A1").level == "item"  # type: ignore[union-attr]
    assert donor_series(ctx, "A2").level == "subcategory"  # type: ignore[union-attr]
    assert donor_series(ctx, "B2").level == "product_type"  # type: ignore[union-attr]
    assert donor_series(ctx, "C1") is None


def test_manifest_and_forecasts_record_levels(tiny_runs: dict[str, Path]) -> None:
    man = read_json(tiny_runs["validation"] / "run_manifest.json")
    h = man["hierarchy"]
    assert h["config"]["rate_levels"] == ["item", "subcategory", "product_type"]
    assert h["config"]["season_levels"] == ["category", "product_type"]
    assert any("B1" in v for v in h["levels_used"])
    f = pd.read_parquet(tiny_runs["validation"] / "forecasts.parquet")
    assert {"rate_level", "season_level"} <= set(f.columns)
    b1 = f[(f["method_id"] == "B1") & f["status"].isin(["success", "fallback"])]
    assert set(b1["season_level"]) <= {"category", "product_type", "flat"} and len(b1)


def test_synthetic_items_carry_hierarchy(tiny: Dataset) -> None:
    it = tiny["items"]
    assert {"subcategory", "category", "product_type"} <= set(it.columns)
    # broad -> fine: every subcategory sits in one category, every category in one product type
    assert it.groupby("subcategory")["category"].nunique().max() == 1
    assert it.groupby("category")["product_type"].nunique().max() == 1
