"""Backward-compatible alias (moved in the 2026-10-24 restructure). Use ``xferbench.data_preparation.feature_engineering.hierarchy``."""

import sys

from xferbench.data_preparation.feature_engineering import hierarchy as _moved

sys.modules[__name__] = _moved
