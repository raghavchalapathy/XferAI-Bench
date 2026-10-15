"""Frozen split construction, dispatched to the dataset's domain plugin."""

from __future__ import annotations

from xferbench.contracts.splits import SplitManifest
from xferbench.data.io import Dataset
from xferbench.domains.registry import get_domain


def build_splits(dataset: Dataset) -> SplitManifest:
    return get_domain(dataset.metadata.domain_plugin).build_splits(dataset)


__all__ = ["SplitManifest", "build_splits"]
