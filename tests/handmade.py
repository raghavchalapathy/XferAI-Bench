"""A small hand-built dataset whose baseline forecasts can be computed by hand.

Origin 2024-01-01, reporting delay 7 days -> latest usable week 2023-12-18; the 52-week window is
2022-12-26 .. 2023-12-18 (cycle weeks 52, 1..51, each exactly once).

Item I1 (category C1), demand multiplier m(w) = 1.5 on even cycle weeks, 0.5 on odd (mean exactly 1):
  D1: households 100, units 2*m(w)   -> pair rate 0.02 per household-week
  D2: households 300, units 3*m(w)   -> pair rate 0.01
  B0 rate = (52*2 + 52*3) / (100*52 + 300*52) = 0.0125; target T has 80 households -> 1.0 unit/week.
Item I2 (category C2) sells only 10 weeks at D2 -> no consistent footprint (fallback).
Leakage traps: a late-reported week, post-origin weeks and an excluded FPG X with huge sales.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from xferbench.calendar import cycle_week
from xferbench.contracts.metadata import Metadata
from xferbench.data.io import Dataset
from xferbench.scaffold import metadata_template

ORIGIN = pd.Timestamp("2024-01-01")
WINDOW = pd.date_range("2022-12-26", "2023-12-18", freq="7D")
EARLY = pd.Timestamp("2015-01-01")


def m(weeks: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    cw = cycle_week(pd.Series(weeks))
    return np.where(cw % 2 == 0, 1.5, 0.5)


def _obs(item: str, fpg: str, weeks: pd.DatetimeIndex, units: np.ndarray, delay_days: int = 7) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "item_id": item,
            "fpg_id": fpg,
            "week_start": weeks,
            "week_end": weeks + pd.Timedelta(days=7),
            "units": units.astype(float),
            "observation_state": "observed",
            "known_at": weeks + pd.Timedelta(days=7 + delay_days),
        }
    )


def build(smoothing_window: int = 1, propensity: float | None = 0.02) -> Dataset:
    md_dict = metadata_template(shares=["share_a", "share_b"])
    md_dict["features"]["seasonality"]["smoothing_window"] = smoothing_window
    md = Metadata.model_validate(md_dict)

    obs = [
        _obs("I1", "D1", WINDOW, 2 * m(WINDOW)),
        _obs("I1", "D2", WINDOW, 3 * m(WINDOW)),
        _obs("I2", "D2", WINDOW[-10:], np.full(10, 4.0)),
        # late report: week 2023-12-25 ends on the origin but is only known a week after it
        _obs("I1", "D1", pd.DatetimeIndex(["2023-12-25"]), np.array([999.0]), delay_days=7),
        # post-origin weeks
        _obs("I1", "D1", pd.date_range("2024-01-01", periods=8, freq="7D"), np.full(8, 777.0)),
        # excluded FPG (e.g. a held-out new FPG of this stage)
        _obs("I1", "X", WINDOW, np.full(len(WINDOW), 500.0)),
    ]
    observations = pd.concat(obs, ignore_index=True)
    offers = observations[["item_id", "fpg_id", "week_start", "week_end", "known_at"]].assign(
        offer_state="offered", offered_days=7, available_days=7, exposure_fraction=1.0, stockout_state="in_stock"
    )
    items = pd.DataFrame(
        {
            "item_id": ["I1", "I2"],
            "category": ["C1", "C2"],
            "product_type": "t",
            "seasonality_class": "s",
            "effective_from": EARLY,
            "known_at": EARLY,
        }
    )
    locations = pd.DataFrame(
        {
            "fpg_id": ["T", "D1", "D2", "X"],
            "region": ["R1", "R1", "R2", "R1"],
            "fpg_open_at": EARLY,
            "households": [80.0, 100.0, 300.0, 100.0],
            "effective_from": EARLY,
            "known_at": EARLY,
            "share_a": [0.5, 0.5, 0.7, 0.5],
            "share_b": [0.5, 0.5, 0.3, 0.5],
        }
    )
    feats = []
    if propensity is not None:
        feats.append(
            {
                "feature_name": "propensity_rate",
                "scope": "pair",
                "item_id": "I1",
                "fpg_id": "T",
                "scope_id": None,
                "origin": ORIGIN,
                "value": propensity,
                "unit": "units_per_household_per_week",
                "known_at": ORIGIN - pd.Timedelta(days=1),
                "source_version": "hand",
            }
        )
        # revised value issued after the origin: must not be visible
        feats.append({**feats[0], "value": 9.0, "known_at": ORIGIN + pd.Timedelta(days=3)})
    origin_features = pd.DataFrame(
        feats,
        columns=[
            "feature_name",
            "scope",
            "item_id",
            "fpg_id",
            "scope_id",
            "origin",
            "value",
            "unit",
            "known_at",
            "source_version",
        ],
    )
    tables = {
        "observations": observations,
        "offers": offers,
        "items": items,
        "locations": locations,
        "origin_features": origin_features,
    }
    return Dataset(metadata=md, base_dir=Path("."), tables=tables)


def request(item: str = "I1", fpg: str = "T") -> pd.DataFrame:
    return pd.DataFrame({"request_id": [f"{item}@{fpg}"], "item_id": [item], "fpg_id": [fpg], "origin": [ORIGIN]})


FORECAST_WEEKS = pd.date_range(ORIGIN, periods=52, freq="7D")
