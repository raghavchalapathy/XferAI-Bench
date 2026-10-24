"""Reviewer-supplied regression tests (copied verbatim from the review folder; do not edit them).

One Reviewer test is flagged rather than edited: ``test_self_approval`` builds a self-approved Proposal and then
asserts on it, so it can only pass if self-approval is *accepted*. The fix rejects self-approval at construction,
so the test is marked xfail(strict=True, raises=ValidationError): it must fail with exactly that error, and it
turns red if self-approval is ever accepted again. See DESIGN_NOTE v2 (F-4).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.nodeid.endswith("test_review_harness.py::test_self_approval"):
            item.add_marker(
                pytest.mark.xfail(
                    strict=True,
                    raises=ValidationError,
                    reason="Reviewer test flagged: self-approval is now rejected at construction (ValidationError)",
                )
            )
