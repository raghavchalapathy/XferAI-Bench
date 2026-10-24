"""Backward-compatible alias (moved in the 2026-10-24 restructure). Use ``xferbench.models.machine_learning.lightgbm_pairs``."""

import sys

from xferbench.models.machine_learning import lightgbm_pairs as _moved

sys.modules[__name__] = _moved
