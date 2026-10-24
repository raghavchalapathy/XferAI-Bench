"""Backward-compatible alias (moved in the 2026-10-24 restructure). Use ``xferbench.models.foundation_models.donor_prior``."""

import sys

from xferbench.models.foundation_models import donor_prior as _moved

sys.modules[__name__] = _moved
