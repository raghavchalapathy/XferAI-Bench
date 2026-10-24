import pytest
from pydantic import ValidationError
from xferbench.harness.core import Proposal, ResultRef
H="0"*64
def P(touches): return Proposal(id="x", author_role="builder", summary="s", touches=touches)
@pytest.mark.parametrize("t",["src/xferbench/evaluation/metrics.py","./src/xferbench/evaluation/evaluator.py","src\\xferbench\\evaluation\\selection.py"])
def test_neg_blocked(t):
    with pytest.raises(ValidationError): P([t])
@pytest.mark.parametrize("t",["src/xferbench/models/x.py","docs/a.md"])
def test_pos_allowed(t): assert P([t])
# regression / bypass probes: these SHOULD be blocked; xfail-strict style recorded as result
BYPASS=["src/xferbench/evaluation","/abs/repo/src/xferbench/evaluation/metrics.py","src/xferbench//evaluation/metrics.py",
 "src/xferbench/models/../evaluation/metrics.py","SRC/xferbench/evaluation/metrics.py","harness/PROTECTED_HASHES.json",
 "src/xferbench/scalable_eval/core.py","tests/unit/test_scalable_eval.py"]
@pytest.mark.parametrize("t",BYPASS)
def test_bypass(t):
    with pytest.raises(ValidationError): P([t])
def R(dc,label): return ResultRef(run_manifest="m",run_manifest_sha256=H,evidence="e",data_class=dc,label=label)
@pytest.mark.parametrize("l",["synthetic ranking","best method","not a ranking; X is the winner","SOTA"])
def test_syn_neg(l):
    with pytest.raises(ValidationError): R("synthetic",l)
@pytest.mark.parametrize("l",["synthetic smoke test, not a ranking","not a ranking"])
def test_syn_pos(l): assert R("synthetic",l)
def test_real_rank_ok(): assert R("real","ranking")
SYN_BYPASS=["not a ranking: M5 ranked #1","not a ranking; top method","not a ranking, lowest WMAPE wins","not a ranking - first place: B2","not a ranking; B2 ranks first"]
@pytest.mark.parametrize("l",SYN_BYPASS)
def test_syn_bypass(l):
    with pytest.raises(ValidationError): R("synthetic",l)
def test_self_approval():
    p=Proposal(id="x",author_role="builder",summary="s",review={"reviewer":"builder","decision":"approved","date":"2026-10-24"})
    assert p.review.reviewer!="builder", "self-approval accepted"
