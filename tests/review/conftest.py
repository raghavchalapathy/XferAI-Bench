"""Reviewer-supplied regression tests (copied verbatim from the review folders; do not edit them).

``test_review_harness.py::test_self_approval`` (v1) is retired, as the Reviewer asked in
xferbench-restructure-v2-review-20261024 (V2-3): it was written so it could never pass. It is superseded by
``test_review_harness_v2.py``, which tests the same rule correctly. The v1 file stays byte-identical; only that
one test is deselected here, and the other v1 tests still run.
"""

from __future__ import annotations

import pytest

RETIRED = {"tests/review/test_review_harness.py::test_self_approval": "superseded by test_review_harness_v2.py (V2-3)"}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    keep, drop = [], []
    for item in items:
        (drop if item.nodeid in RETIRED else keep).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep
