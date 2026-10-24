"""Backward-compatible alias (moved in the 2026-10-24 restructure). Use ``xferbench.models.base``."""

import sys

from xferbench.models import base as _moved

sys.modules[__name__] = _moved
