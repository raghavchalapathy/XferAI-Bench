"""Shared retail hierarchy fallback (one component for every method; no per-method logic).

* Rate fallback, when the item lacks origin-valid history: levels from ``metadata.features.hierarchy.rate_levels``
  (retail default ``item -> subcategory -> product_type``). A group level uses every same-group item's donor
  pairs (season-neutral rate per household, consistent footprint when available) and needs at least
  ``min_rate_support_fpgs`` donor FPGs.
* Seasonality: levels from ``season_levels`` (retail default ``category -> product_type``). A level is used when its
  profile is estimated from at least one complete donor cycle and at least ``min_season_support_items`` items;
  otherwise the next level; flat as a visible last resort.

Everything is computed from the OriginContext only, so it inherits the origin cut, reporting delay and stage
exclusions. The level used is returned so methods record it in the forecast output and run manifest.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from xferbench.data_preparation.feature_engineering.aggregates import (
    FLAT,
    NationalRate,
    SeasonalProfile,
    national_rates,
    pair_rates,
    seasonal_profiles_by,
)
from xferbench.data_preparation.feature_engineering.context import OriginContext


@dataclass(frozen=True)
class LevelRate:
    rate: float | None
    level: str  # e.g. item | subcategory | product_type | none
    footprint: str
    reason: str = ""


def _attr(ctx: OriginContext, item_id: str, column: str) -> str | None:
    if column not in ctx.items.columns:
        return None
    v = ctx.items.set_index("item_id")[column].get(item_id)
    return None if v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v) else str(v)


def group_items(ctx: OriginContext, item_id: str, level: str) -> list[str] | None:
    """Items sharing ``item_id``'s value at ``level`` (as known at origin); None if the level is unknown."""
    if level == "item":
        return [item_id]
    g = _attr(ctx, item_id, level)
    if g is None:
        return None
    it = ctx.items
    return sorted(it.loc[it[level].astype(object) == g, "item_id"].astype(str).unique())


def _group_rate(ctx: OriginContext, items: list[str], min_fpgs: int) -> NationalRate | None:
    pr = pair_rates(ctx)
    grp = pr[pr["item_id"].isin(items)]
    if grp.empty:
        return None
    cons = grp[grp["consistent"]]
    use, label = (cons, "consistent") if len(cons) else (grp, "all_measured")
    if use["fpg_id"].nunique() < min_fpgs:
        return None
    denom = float((use["households"] * use["n_obs"]).sum())
    if denom <= 0:
        return None
    return NationalRate(float(use["units_sum"].sum()) / denom, int(use["fpg_id"].nunique()), denom, label)


def rate_for_item(ctx: OriginContext, item_id: str) -> LevelRate:
    return ctx.cached(f"hier_rate:{item_id}", lambda: _rate_for_item(ctx, item_id))  # type: ignore[no-any-return]


def _rate_for_item(ctx: OriginContext, item_id: str) -> LevelRate:
    spec = ctx.metadata.features.hierarchy
    tried: list[str] = []
    for level in spec.rate_levels:
        if level == "item":
            nr = national_rates(ctx).get(item_id)
            if nr is not None and nr.rate is not None:
                return LevelRate(nr.rate, "item", nr.footprint)
            tried.append("item: no origin-valid history")
            continue
        items = group_items(ctx, item_id, level)
        if items is None:
            tried.append(f"{level}: unknown at origin")
            continue
        nr = _group_rate(ctx, items, spec.min_rate_support_fpgs)
        if nr is None:
            tried.append(f"{level}: fewer than {spec.min_rate_support_fpgs} donor FPGs")
            continue
        return LevelRate(nr.rate, level, nr.footprint, "rate fallback to " + level + " (" + "; ".join(tried) + ")")
    return LevelRate(None, "none", "none", "no rate at any hierarchy level (" + "; ".join(tried) + ")")


@dataclass(frozen=True)
class LevelProfile:
    profile: SeasonalProfile
    level: str  # e.g. category | product_type | flat

    def at(self, weeks: pd.Series | list[pd.Timestamp]) -> np.ndarray:
        return self.profile.at(weeks)

    @property
    def status(self) -> str:
        return self.profile.status

    @property
    def reason(self) -> str:
        return self.profile.reason


def profile_for_item(ctx: OriginContext, item_id: str) -> LevelProfile:
    return ctx.cached(f"hier_season:{item_id}", lambda: _profile_for_item(ctx, item_id))  # type: ignore[no-any-return]


def _profile_for_item(ctx: OriginContext, item_id: str) -> LevelProfile:
    spec = ctx.metadata.features.hierarchy
    tried: list[str] = []
    for i, level in enumerate(spec.season_levels):
        g = _attr(ctx, item_id, level)
        if g is None:
            tried.append(f"{level}: unknown at origin")
            continue
        prof, n_items = seasonal_profiles_by(ctx, level).get(g, (None, 0))
        if prof is None:
            tried.append(f"{level} '{g}': no donor history")
        elif prof.status != "estimated":
            tried.append(f"{level} '{g}': {prof.reason}")
        elif n_items < spec.min_season_support_items:
            tried.append(f"{level} '{g}': {n_items} item(s) < {spec.min_season_support_items}")
        else:
            if i == 0:
                return LevelProfile(prof, level)
            return LevelProfile(
                SeasonalProfile(
                    prof.values, prof.n_cycles, "estimated", f"season fallback to {level} ({'; '.join(tried)})"
                ),
                level,
            )
    return LevelProfile(SeasonalProfile(FLAT.copy(), 0, "flat_fallback", "; ".join(tried) or "no levels"), "flat")
