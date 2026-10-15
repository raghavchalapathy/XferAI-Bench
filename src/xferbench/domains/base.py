"""Domain plugin interface.

A domain plugin owns everything industry-specific: entity roles, keys, target units, calendar,
exposure semantics, cohort/scenario rules, slices and validation. The engine (runner, evaluator,
reports) only relies on this interface and on generic request/forecast/target frames:

* requests: ``request_id, origin, scenario, board`` plus the plugin's ``entity_columns`` and
  ``slice_columns``;
* targets: ``request_id, horizon_week, forecast_week, actual, measured`` plus optional
  ``slice_week_columns``.

Nothing here assumes FPGs, households or propensity.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd

from xferbench.contracts.splits import SplitManifest
from xferbench.data.io import Dataset
from xferbench.data.issues import Issue


@runtime_checkable
class DomainPlugin(Protocol):
    id: str
    version: str
    task_profiles: tuple[str, ...]
    entity_columns: tuple[str, ...]
    scenarios: tuple[str, ...]
    slice_columns: tuple[str, ...]
    slice_week_columns: tuple[str, ...]

    def validate(self, dataset: Dataset) -> list[Issue]: ...

    def build_splits(self, dataset: Dataset) -> SplitManifest: ...

    def requests(self, dataset: Dataset, split: SplitManifest, stage: str) -> pd.DataFrame: ...

    def training_requests(self, dataset: Dataset, split: SplitManifest, stage: str) -> pd.DataFrame: ...

    def targets(self, dataset: Dataset, requests: pd.DataFrame) -> pd.DataFrame: ...

    def context_builder(self, dataset: Dataset, split: SplitManifest, stage: str): ...  # type: ignore[no-untyped-def]

    def data_profile(self, dataset: Dataset, split: SplitManifest | None) -> dict: ...
