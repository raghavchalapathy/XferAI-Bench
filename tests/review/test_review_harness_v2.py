"""Reviewer v2 tests. Supersedes test_self_approval in test_review_harness.py (v1), which was written wrongly:
it built the proposal outside pytest.raises and then asserted reviewer != 'builder', so it could never pass
(accepted -> AssertionError; rejected -> ValidationError)."""
import pytest
from pydantic import ValidationError
from xferbench.harness.core import Proposal, ResultRef
H = "a" * 64
def prop(reviewer, author="builder", decision="approved"):
    return Proposal(id="x", author_role=author, summary="s",
                    review={"reviewer": reviewer, "decision": decision, "date": "2026-10-24", "review_file": "r.md", "review_sha256": H})
@pytest.mark.parametrize("who", ["builder", "Builder ", "scout", "lead", "owner", "engineer"])
def test_self_or_nonreviewer_approval_rejected(who):
    with pytest.raises(ValidationError):
        prop(who)
def test_scout_cannot_approve_own():
    with pytest.raises(ValidationError):
        prop("scout", author="scout")
def test_reviewer_approval_accepted():
    assert prop("reviewer").review.reviewer == "reviewer"
def test_approval_without_review_file_rejected():
    with pytest.raises(ValidationError):
        Proposal(id="x", author_role="builder", summary="s", review={"reviewer": "reviewer", "decision": "approved", "date": "2026-10-24"})
# probes (expected to be rejected; record result)
@pytest.mark.parametrize("who", ["reviewer-builder", "reviewer_scout"])
def test_probe_reviewer_prefixed_author(who):
    with pytest.raises(ValidationError):
        prop(who)
@pytest.mark.parametrize("label", ["Not a ranking. M4 is best", "synthetic smoke test, not a ranking; B2 wins"])
def test_probe_label(label):
    with pytest.raises(ValidationError):
        ResultRef(run_manifest="m", run_manifest_sha256=H, evidence="e", data_class="synthetic", label=label)
@pytest.mark.parametrize("t", ["tests/review/adv.py", "./harness/PROTECTED_HASHES.json", "src/xferbench/evaluation/../evaluation/metrics.py", "src/xferbench/Evaluation/metrics.py"])
def test_probe_paths(t):
    with pytest.raises(ValidationError):
        Proposal(id="x", author_role="builder", summary="s", touches=[t])
