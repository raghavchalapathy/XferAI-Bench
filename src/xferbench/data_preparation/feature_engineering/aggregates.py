"""Origin-valid donor/national aggregates computed only from an :class:`OriginContext`."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from xferbench.calendar import CYCLE_WEEKS, WEEK, cycle_week
from xferbench.data_preparation.feature_engineering.context import OriginContext


def window_bounds(ctx: OriginContext, weeks: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    last = ctx.latest_usable_week
    return last - WEEK * (weeks - 1), last


def pair_rates(ctx: OriginContext) -> pd.DataFrame:
    """Per donor pair: measured weeks, units and season-neutral rate per household over the trailing window.

    A pair is *consistently exposed* if it was measured in at least ``min_fraction`` of the window weeks;
    over a full annual window its plain ratio is season-neutral.
    """

    def build() -> pd.DataFrame:
        pol = ctx.metadata.donor_policy
        w = pol.consistent_exposure_window_weeks
        start, last = window_bounds(ctx, w)
        obs = ctx.observations
        win = obs[(obs["week_start"] >= start) & (obs["week_start"] <= last) & obs["units"].notna()]
        g = win.groupby(["item_id", "fpg_id"], sort=True).agg(units_sum=("units", "sum"), n_obs=("units", "size"))
        g = g.reset_index()
        hh = ctx.locations.set_index("fpg_id")["households"]
        g["households"] = g["fpg_id"].map(hh).astype(float)
        g = g[g["households"].notna() & (g["households"] > 0)].copy()
        g["rate"] = g["units_sum"] / (g["households"] * g["n_obs"])
        g["avg_units"] = g["units_sum"] / g["n_obs"]
        g["consistent"] = g["n_obs"] >= math.ceil(pol.consistent_exposure_min_fraction * w)
        return g.reset_index(drop=True)

    return ctx.cached("pair_rates", build)


@dataclass(frozen=True)
class NationalRate:
    rate: float | None
    n_fpgs: int
    household_weeks: float
    footprint: str  # consistent | all_measured | none


def national_rates(ctx: OriginContext) -> dict[str, NationalRate]:
    """B0 national rate r_i = sum(units)/sum(households * measured weeks) over the consistent footprint.

    Each FPG's households are counted once per measured week (non-overlapping households), so the
    footprint is deduplicated by construction.
    """

    def build() -> dict[str, NationalRate]:
        pr = pair_rates(ctx)
        out: dict[str, NationalRate] = {}
        for item, grp in pr.groupby("item_id", sort=True):
            cons = grp[grp["consistent"]]
            use, label = (cons, "consistent") if len(cons) else (grp, "all_measured")
            denom = float((use["households"] * use["n_obs"]).sum())
            rate = float(use["units_sum"].sum()) / denom if denom > 0 else None
            out[str(item)] = NationalRate(rate, len(use), denom, label if rate is not None else "none")
        return out

    return ctx.cached("national_rates", build)


@dataclass(frozen=True)
class SeasonalProfile:
    values: np.ndarray  # length 52, mean exactly one
    n_cycles: int
    status: str  # estimated | flat_fallback
    reason: str = ""

    def at(self, weeks: pd.Series | list[pd.Timestamp]) -> np.ndarray:
        return self.values[cycle_week(pd.Series(weeks)) - 1]


FLAT = np.ones(CYCLE_WEEKS)


def _circular_smooth(x: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return x
    half = window // 2
    padded = np.concatenate([x[-half:], x, x[:half]])
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="valid")[: len(x)]


def seasonal_profiles(ctx: OriginContext) -> dict[str, SeasonalProfile]:
    """Category-level profiles (kept for backward compatibility; see seasonal_profiles_by)."""
    return {k: v for k, (v, _) in seasonal_profiles_by(ctx, "category").items()}


def seasonal_profiles_by(ctx: OriginContext, level: str) -> dict[str, tuple[SeasonalProfile, int]]:
    """Per-group (``level`` column, e.g. category or product_type), calendar-aligned, mean-one seasonal index estimated from donor history.

    For each complete 52-week cycle ending at the latest usable week, the category's weekly rate per
    measured household is divided by that cycle's mean rate (removing level and slow trend between
    cycles); indices are averaged by cycle position, circularly smoothed and renormalized to mean one.
    """

    def build() -> dict[str, tuple[SeasonalProfile, int]]:
        spec = ctx.metadata.features.seasonality
        obs = ctx.observations
        meas = obs[obs["units"].notna()]
        if level not in ctx.items.columns:
            return {}
        cat = ctx.items.set_index("item_id")[level]
        hh = ctx.locations.set_index("fpg_id")["households"]
        frame = pd.DataFrame(
            {
                "item_id": meas["item_id"],
                "category": meas["item_id"].map(cat),
                "week_start": meas["week_start"],
                "units": meas["units"].astype(float),
                "hh": meas["fpg_id"].map(hh).astype(float),
            }
        ).dropna(subset=["category", "hh"])
        last = ctx.latest_usable_week
        out: dict[str, tuple[SeasonalProfile, int]] = {}
        for c, grp in frame.groupby("category", sort=True):
            n_items = int(grp["item_id"].nunique())
            wk = grp.groupby("week_start").agg(units=("units", "sum"), hh=("hh", "sum"))
            wk = wk[wk["hh"] > 0]
            rate = wk["units"] / wk["hh"]
            idx_rows: list[pd.Series] = []
            for k in range(spec.max_cycles):
                c_end = last - WEEK * (CYCLE_WEEKS * k)
                c_start = c_end - WEEK * (CYCLE_WEEKS - 1)
                seg = rate[(rate.index >= c_start) & (rate.index <= c_end)]
                if len(seg) < 0.9 * CYCLE_WEEKS or seg.mean() <= 0:
                    break
                idx_rows.append(pd.Series((seg / seg.mean()).to_numpy(), index=cycle_week(seg.index)))
            if not idx_rows:
                out[str(c)] = (
                    SeasonalProfile(FLAT.copy(), 0, "flat_fallback", "fewer than one complete donor cycle"),
                    n_items,
                )
                continue
            stacked = pd.concat(idx_rows).groupby(level=0).mean()
            raw = stacked.reindex(range(1, CYCLE_WEEKS + 1))
            raw = raw.interpolate(limit_direction="both").fillna(1.0).to_numpy(dtype=float)
            sm = _circular_smooth(raw, spec.smoothing_window)
            sm = np.clip(sm, 1e-6, None)
            out[str(c)] = (SeasonalProfile(sm / sm.mean(), len(idx_rows), "estimated"), n_items)
        return out

    return ctx.cached(f"seasonal_profiles:{level}", build)


def profile_for_item(ctx: OriginContext, item_id: str) -> SeasonalProfile:
    """Hierarchical seasonal profile (category -> product type by default); see features/hierarchy.py."""
    from xferbench.data_preparation.feature_engineering.hierarchy import profile_for_item as hier

    return hier(ctx, item_id).profile


def location_attributes(ctx: OriginContext) -> pd.DataFrame:
    """Prelaunch location attributes used for similarity (shares, log households, region)."""
    cols = ["fpg_id", "households", "region", *ctx.share_columns]
    return ctx.locations[[c for c in cols if c in ctx.locations.columns]].copy()
