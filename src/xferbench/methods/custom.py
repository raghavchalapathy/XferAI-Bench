"""Backward-compatible alias (moved in the 2026-10-24 restructure). Use ``xferbench.models.custom``."""

import sys

from xferbench.models import custom as _moved

sys.modules[__name__] = _moved
