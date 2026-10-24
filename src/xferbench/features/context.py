"""Backward-compatible alias (moved in the 2026-10-24 restructure). Use ``xferbench.data_preparation.feature_engineering.context``."""

import sys

from xferbench.data_preparation.feature_engineering import context as _moved

sys.modules[__name__] = _moved
