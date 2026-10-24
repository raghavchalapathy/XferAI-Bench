"""Old import paths keep working after the 2026-10-24 restructure (aliases point at the same module)."""

from __future__ import annotations

import importlib

import pytest

MOVED = {
    "xferbench.methods.base": "xferbench.models.base",
    "xferbench.methods.registry": "xferbench.models.registry",
    "xferbench.methods.custom": "xferbench.models.custom",
    "xferbench.methods.baselines.rates": "xferbench.models.stats.rates",
    "xferbench.methods.boosting": "xferbench.models.machine_learning.lightgbm_pairs",
    "xferbench.methods.foundation": "xferbench.models.foundation_models.donor_prior",
    "xferbench.features.context": "xferbench.data_preparation.feature_engineering.context",
    "xferbench.features.aggregates": "xferbench.data_preparation.feature_engineering.aggregates",
    "xferbench.features.hierarchy": "xferbench.data_preparation.feature_engineering.hierarchy",
}


@pytest.mark.parametrize(("old", "new"), sorted(MOVED.items()))
def test_old_path_is_alias(old: str, new: str) -> None:
    assert importlib.import_module(old) is importlib.import_module(new)


def test_old_from_import_still_works() -> None:
    from xferbench.methods.baselines.rates import B0NationalRate
    from xferbench.models.stats.rates import B0NationalRate as New

    assert B0NationalRate is New


def test_family_reexports() -> None:
    from xferbench.models.analogs import B2AnalogRate, B3AnalogRate
    from xferbench.models.stats.rates import B2AnalogRate as B2
    from xferbench.models.stats.rates import B3AnalogRate as B3

    assert (B2AnalogRate, B3AnalogRate) == (B2, B3)
