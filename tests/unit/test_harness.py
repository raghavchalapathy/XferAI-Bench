"""Harness guardrails: evaluator protection, evidence, synthetic labels, reviewer gate, versioning, triggers."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest
import yaml

from xferbench.harness.core import (
    HarnessError,
    Lesson,
    ResultRef,
    append_lesson,
    apply_proposal,
    current_practices,
    due_triggers,
    load_proposal,
    read_lessons,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[2]
TODAY = dt.date(2026, 10, 24)
LBL = "synthetic interface test, not rankings"


@pytest.fixture()
def env(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    ev = root / "src/xferbench/evaluation"
    ev.mkdir(parents=True)
    for n in ("evaluator.py", "metrics.py", "selection.py", "__init__.py"):
        shutil.copy(ROOT / "src/xferbench/evaluation" / n, ev / n)
    h = root / "harness"
    (h / "proposals").mkdir(parents=True)
    for n in ("BEST_PRACTICES.v1.yaml", "CHANGELOG.md", "PROTECTED_HASHES.json", "watch.yaml"):
        shutil.copy(ROOT / "harness" / n, h / n)
    run = root / "eval/x/test-run"
    run.mkdir(parents=True)
    (run / "run_manifest.json").write_text("{}", encoding="utf-8")
    (root / "eval/x/results.json").write_text("{}", encoding="utf-8")
    return root, h


def _ref(root: Path, **kw: object) -> dict[str, object]:
    m = root / "eval/x/test-run/run_manifest.json"
    d: dict[str, object] = {
        "run_manifest": "eval/x/test-run/run_manifest.json",
        "run_manifest_sha256": sha256_file(m),
        "evidence": "eval/x/results.json",
        "data_class": "synthetic",
        "label": LBL,
        "objective": 1.5,
    }
    d.update(kw)
    return d


def _proposal(h: Path, root: Path, **kw: object) -> Path:
    d: dict[str, object] = {
        "id": "p1",
        "author_role": "builder",
        "summary": "tighten rule",
        "set_rules": {"new_rule": "text"},
        "results": [_ref(root)],
        "review": {"reviewer": "Reviewer", "decision": "approved", "date": "2026-10-24"},
    }
    d.update(kw)
    p = h / "proposals/p1.yaml"
    p.write_text(yaml.safe_dump(d), encoding="utf-8")
    return p


def test_repo_harness_is_valid() -> None:
    bp, _ = current_practices(ROOT / "harness")
    assert bp.version >= 1 and "scope" in bp.rules
    read_lessons(ROOT / "harness")
    ref = json.loads((ROOT / "harness/PROTECTED_HASHES.json").read_text(encoding="utf-8"))
    for rel, h in ref.items():
        assert sha256_file(ROOT / rel) == h, rel


def test_apply_approved_bumps_version_and_logs(env: tuple[Path, Path]) -> None:
    root, h = env
    dest = apply_proposal(_proposal(h, root), root, h)
    assert dest.name == "BEST_PRACTICES.v2.yaml"
    bp, _ = current_practices(h)
    assert bp.version == 2 and bp.rules["new_rule"] == "text"
    assert "proposal `p1`" in (h / "CHANGELOG.md").read_text(encoding="utf-8")
    with pytest.raises(HarnessError, match="already adopted"):
        apply_proposal(h / "proposals/p1.yaml", root, h)


@pytest.mark.parametrize("review", [None, {"reviewer": "R", "decision": "rejected", "date": "2026-10-24"}])
def test_no_adoption_without_approved_review(env: tuple[Path, Path], review: object) -> None:
    root, h = env
    with pytest.raises(HarnessError, match="Reviewer"):
        apply_proposal(_proposal(h, root, review=review), root, h)
    assert current_practices(h)[0].version == 1


def test_cannot_touch_evaluator_path(env: tuple[Path, Path]) -> None:
    root, h = env
    with pytest.raises(HarnessError, match="protected evaluator"):
        load_proposal(_proposal(h, root, touches=["src/xferbench/evaluation/metrics.py"]))


def test_evaluator_hash_change_blocks(env: tuple[Path, Path]) -> None:
    root, h = env
    with (root / "src/xferbench/evaluation/metrics.py").open("a", encoding="utf-8") as fh:
        fh.write("\n# tampered\n")
    with pytest.raises(HarnessError, match="protected evaluator file changed"):
        apply_proposal(_proposal(h, root), root, h)


def test_results_need_manifest_and_evidence(env: tuple[Path, Path]) -> None:
    root, h = env
    with pytest.raises(HarnessError, match="evidence missing"):
        apply_proposal(_proposal(h, root, results=[_ref(root, evidence="eval/nope.json")]), root, h)
    with pytest.raises(HarnessError, match="hash mismatch"):
        apply_proposal(_proposal(h, root, results=[_ref(root, run_manifest_sha256="0" * 64)]), root, h)


@pytest.mark.parametrize("label", ["synthetic ranking", "best method on synthetic", "not a ranking but B2 wins: best"])
def test_synthetic_cannot_be_ranking(env: tuple[Path, Path], label: str) -> None:
    root, _ = env
    with pytest.raises(ValueError):
        ResultRef.model_validate(_ref(root, label=label))
    ResultRef.model_validate(_ref(root, data_class="real", label="validated real benchmark ranking"))


def _lesson(root: Path, obj: float, status: str = "success", accepted: bool = False) -> Lesson:
    return Lesson.model_validate(
        {
            "date": "2026-10-24",
            "experiment": "exp01",
            "what_changed": "k grid",
            "status": status,
            "result": _ref(root, objective=obj),
            "accepted": accepted,
        }
    )


def test_lessons_and_triggers(env: tuple[Path, Path]) -> None:
    root, h = env
    assert due_triggers(h, TODAY) == []
    append_lesson(h, root, _lesson(root, 1.5, accepted=True))
    append_lesson(h, root, _lesson(root, 1.7))
    append_lesson(h, root, _lesson(root, 1.4, status="failed"))
    (h / "watch.yaml").write_text(
        yaml.safe_dump({"papers": [{"title": "T", "url": "u", "status": "new"}]}), encoding="utf-8"
    )
    kinds = {d["trigger"] for d in due_triggers(h, TODAY + dt.timedelta(days=91))}
    assert kinds == {"new_paper", "failed_run", "regression", "stale_review"}
    assert len(read_lessons(h)) == 3


def test_lesson_requires_existing_evidence(env: tuple[Path, Path]) -> None:
    root, h = env
    bad = _lesson(root, 1.0)
    bad.result.evidence = "missing.json"
    with pytest.raises(HarnessError):
        append_lesson(h, root, bad)
