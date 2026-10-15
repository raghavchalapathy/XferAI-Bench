"""Origin-scoped, allowlisted views of the dataset.

An :class:`OriginContext` contains only information usable at its origin:

* observations/offers whose interval ended by the origin AND whose ``known_at <= origin``;
* attribute versions with ``effective_from <= origin`` and ``known_at <= origin``;
* origin feature snapshots and future covariates issued for this origin and known by then;
* never any row of a held-out pair or a held-out new location of the evaluated stage.

Evaluator targets are not reachable from a context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from xferbench.calendar import WEEK, to_ts
from xferbench.contracts.metadata import Metadata
from xferbench.data.io import Dataset
from xferbench.util import hash_frame, hash_obj


@dataclass(frozen=True)
class Exclusions:
    """Held-out pairs/locations whose rows never enter contexts built for this stage."""

    pairs: frozenset[tuple[str, str]] = frozenset()
    fpgs: frozenset[str] = frozenset()

    def to_dict(self) -> dict:
        return {"pairs": sorted(f"{i}|{f}" for i, f in self.pairs), "fpgs": sorted(self.fpgs)}


@dataclass(frozen=True)
class OriginContext:
    origin: pd.Timestamp
    metadata: Metadata
    observations: pd.DataFrame
    offers: pd.DataFrame
    items: pd.DataFrame
    locations: pd.DataFrame
    origin_features: pd.DataFrame
    future_covariates: pd.DataFrame
    exclusions: Exclusions
    share_columns: tuple[str, ...]
    _cache: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def reporting_delay(self) -> pd.Timedelta:
        return pd.Timedelta(days=self.metadata.time.reporting_delay_days)

    @property
    def latest_usable_week(self) -> pd.Timestamp:
        """Latest week start whose interval end plus declared reporting delay is <= origin."""
        return self.origin - self.reporting_delay - WEEK

    def households(self, fpg_ids: list[str] | pd.Series) -> pd.Series:
        loc = self.locations.set_index("fpg_id")["households"]
        return pd.Series(list(fpg_ids)).map(loc)

    def cached(self, key: str, fn: Any) -> Any:
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def feature(self, name: str) -> pd.DataFrame:
        f = self.origin_features
        return f[f["feature_name"] == name]

    def content_hash(self) -> str:
        parts = {
            "origin": self.origin.date().isoformat(),
            "observations": hash_frame(self.observations, ["item_id", "fpg_id", "week_start"]),
            "offers": hash_frame(self.offers, ["item_id", "fpg_id", "week_start"]),
            "items": hash_frame(self.items, ["item_id"]),
            "locations": hash_frame(self.locations, ["fpg_id"]),
            "origin_features": hash_frame(self.origin_features),
            "future_covariates": hash_frame(self.future_covariates),
            "exclusions": self.exclusions.to_dict(),
        }
        return hash_obj(parts)


def _as_of(df: pd.DataFrame, key: str, origin: pd.Timestamp) -> pd.DataFrame:
    ok = df[(df["effective_from"] <= origin) & (df["known_at"] <= origin)]
    if ok.empty:
        return ok.copy()
    ok = ok.sort_values([key, "effective_from", "known_at"], kind="mergesort")
    return ok.groupby(key, sort=True).tail(1).reset_index(drop=True)


def _drop_excluded(df: pd.DataFrame, ex: Exclusions) -> pd.DataFrame:
    if df.empty:
        return df
    mask = np.ones(len(df), dtype=bool)
    if ex.fpgs:
        mask &= ~df["fpg_id"].isin(ex.fpgs).to_numpy()
    if ex.pairs:
        idx = pd.MultiIndex.from_arrays([df["item_id"], df["fpg_id"]])
        mask &= ~idx.isin(list(ex.pairs))
    return df[mask]


class ContextBuilder:
    """Builds origin contexts for one stage; pre-applies the stage exclusions once."""

    def __init__(self, dataset: Dataset, exclusions: Exclusions):
        self.dataset = dataset
        self.metadata = dataset.metadata
        self.exclusions = exclusions
        self._obs = _drop_excluded(dataset["observations"], exclusions)
        self._offers = _drop_excluded(dataset["offers"], exclusions)
        self._of = dataset.tables.get("origin_features")
        self._fc = dataset.tables.get("future_covariates")
        self.share_columns = tuple(self.metadata.features.demographic_share_columns)

    def at(self, origin: pd.Timestamp | str) -> OriginContext:
        o = to_ts(origin)
        obs = self._obs[(self._obs["week_end"] <= o) & (self._obs["known_at"] <= o)].reset_index(drop=True)
        offers = self._offers[(self._offers["week_end"] <= o) & (self._offers["known_at"] <= o)].reset_index(drop=True)
        items = _as_of(self.dataset["items"], "item_id", o)
        locations = _as_of(self.dataset["locations"], "fpg_id", o)
        if self._of is not None:
            of = self._of[(self._of["origin"] == o) & (self._of["known_at"] <= o)].reset_index(drop=True)
        else:
            of = pd.DataFrame(
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
                ]
            )
        if self._fc is not None:
            fc = self._fc[(self._fc["origin"] == o) & (self._fc["known_at"] <= o)].reset_index(drop=True)
        else:
            fc = pd.DataFrame(
                columns=[
                    "feature_name",
                    "item_id",
                    "fpg_id",
                    "scope_id",
                    "origin",
                    "forecast_week",
                    "value",
                    "availability_class",
                    "known_at",
                    "source_version",
                ]
            )
        return OriginContext(
            origin=o,
            metadata=self.metadata,
            observations=obs,
            offers=offers,
            items=items,
            locations=locations,
            origin_features=of,
            future_covariates=fc,
            exclusions=self.exclusions,
            share_columns=self.share_columns,
        )
