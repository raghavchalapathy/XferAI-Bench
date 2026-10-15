"""Weekly calendar arithmetic with half-open [week_start, week_end) intervals.

All dates are local calendar dates in the timezone declared by metadata. A date-valued
``known_at`` means "available from 00:00 local time on that date".
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

WEEKDAYS = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}
CYCLE_WEEKS = 52
DAY = pd.Timedelta(days=1)
WEEK = pd.Timedelta(days=7)


def to_ts(value: str | dt.date | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.normalize()


def week_floor(value: pd.Timestamp | str | dt.date, week_start: str = "Monday") -> pd.Timestamp:
    ts = to_ts(value)
    offset = (ts.weekday() - WEEKDAYS[week_start]) % 7
    return ts - pd.Timedelta(days=offset)


def week_ceil(value: pd.Timestamp | str | dt.date, week_start: str = "Monday") -> pd.Timestamp:
    floor = week_floor(value, week_start)
    return floor if floor == to_ts(value) else floor + WEEK


def week_range(start: str | pd.Timestamp, end: str | pd.Timestamp, week_start: str = "Monday") -> list[pd.Timestamp]:
    """Every week start in [week_ceil(start), end] inclusive of ``end`` when aligned."""
    first = week_ceil(start, week_start)
    last = to_ts(end)
    out: list[pd.Timestamp] = []
    cur = first
    while cur <= last:
        out.append(cur)
        cur += WEEK
    return out


def is_week_start(series: pd.Series, week_start: str = "Monday") -> pd.Series:
    return pd.to_datetime(series).dt.weekday == WEEKDAYS[week_start]


def forecast_weeks(origin: pd.Timestamp, horizon: int) -> list[pd.Timestamp]:
    return [origin + WEEK * h for h in range(horizon)]


def target_end(origin: pd.Timestamp, horizon: int) -> pd.Timestamp:
    """Exclusive end of the last target interval."""
    return origin + WEEK * horizon


def declared_label_available_at(origin: pd.Timestamp, horizon: int, reporting_delay_days: int) -> pd.Timestamp:
    return target_end(origin, horizon) + pd.Timedelta(days=reporting_delay_days)


def cycle_week(dates: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    """Calendar-aligned position 1..52 in an annual cycle; ISO week 53 folds into 52."""
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    iso = idx.isocalendar().week.to_numpy(dtype=int)
    return np.minimum(iso, CYCLE_WEEKS)


def horizon_bucket(h: pd.Series) -> pd.Series:
    bins = [0, 4, 13, 26, 52]
    labels = ["h01-04", "h05-13", "h14-26", "h27-52"]
    return pd.cut(h, bins=bins, labels=labels).astype(str)
