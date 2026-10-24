"""Backward-compatible alias (moved in the 2026-10-24 restructure). Use ``xferbench.models.stats.rates``."""

import sys

from xferbench.models.stats import rates as _moved

sys.modules[__name__] = _moved
