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
    check_proposal,
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
    for rel in json.loads((ROOT / "harness/PROTECTED_HASHES.json").read_text(encoding="utf-8")):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, root / rel)
    (root / "factory/inbox/reviewer").mkdir(parents=True)
    (root / "factory/inbox/reviewer/review.md").write_text("Reviewer: approved\n", encoding="utf-8")
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
        "review": {
            "reviewer": "reviewer",
            "decision": "approved",
            "date": "2026-10-24",
            "review_file": "factory/inbox/reviewer/review.md",
            "review_sha256": sha256_file(root / "factory/inbox/reviewer/review.md"),
        },
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


@pytest.mark.parametrize("review", [None, {"reviewer": "reviewer", "decision": "rejected", "date": "2026-10-24"}])
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


# ---------------------------------------------------------------- v2 (Reviewer findings F-3 / F-4)
@pytest.mark.parametrize("who", ["builder", "Builder", "scout", "engineer"])
def test_self_or_non_reviewer_approval_rejected(env: tuple[Path, Path], who: str) -> None:
    root, h = env
    p = _proposal(h, root)
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["review"]["reviewer"] = who
    p.write_text(yaml.safe_dump(d), encoding="utf-8")
    with pytest.raises(HarnessError):
        load_proposal(p)


def test_review_file_hash_must_match(env: tuple[Path, Path]) -> None:
    root, h = env
    p = _proposal(h, root)
    (root / "factory/inbox/reviewer/review.md").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(HarnessError, match="sha256 mismatch"):
        apply_proposal(p, root, h)


def _git(root: Path, *args: str) -> None:
    import subprocess

    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env={**__import__("os").environ, **env})


@pytest.fixture
def gitenv(env: tuple[Path, Path]) -> tuple[Path, Path]:
    root, h = env
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root, h


def test_actual_diff_into_protected_path_is_blocked(gitenv: tuple[Path, Path]) -> None:
    root, h = gitenv
    p = _proposal(h, root, touches=["docs/a.md"])
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "proposal")
    (root / "harness/PROTECTED_HASHES.json").write_text("{}", encoding="utf-8")  # declared touches lie
    with pytest.raises(HarnessError, match="protected"):
        check_proposal(load_proposal(p), root, h)


def test_undeclared_change_is_blocked(gitenv: tuple[Path, Path]) -> None:
    root, h = gitenv
    p = _proposal(h, root, touches=["docs/a.md"])
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "proposal")
    (root / "docs").mkdir()
    (root / "docs/a.md").write_text("ok", encoding="utf-8")
    (root / "docs/b.md").write_text("sneaky", encoding="utf-8")
    with pytest.raises(HarnessError, match="not declared"):
        check_proposal(load_proposal(p), root, h)
    (root / "docs/b.md").unlink()
    check_proposal(load_proposal(p), root, h)


def test_symlink_into_protected_path_is_blocked(env: tuple[Path, Path]) -> None:
    root, h = env
    (root / "docs").mkdir()
    try:
        (root / "docs/link").symlink_to(root / "src/xferbench/evaluation", target_is_directory=True)
    except OSError:  # Windows without developer mode
        pytest.skip("symlinks unsupported")
    p = _proposal(h, root, touches=["docs/link/metrics.py"])
    with pytest.raises(HarnessError, match="protected"):
        check_proposal(load_proposal(p), root, h)


def test_reviewer_files_unmodified() -> None:
    pins = {
        "tests/review/test_review_harness.py": "07252b7d650b6716ff14beb263357ca34302f44d2d5fdadd342755a9c35cea64",
        "tests/review/test_review_harness_v2.py": "c190f9faf99cd231892663faee65966f5b38e185416057eefc4fba2b8e23b903",
        "tests/review/test_review_adv.py": "e50daf8bb60dcb356062482067796dee189b5db3bbb87258a933717e7738bfca",
        "tests/review/adv.py": "f734c76739373b33bb5a5693f09e6c61635cc55830602799856017ff2b3a537e",
    }
    for rel, h in pins.items():
        assert sha256_file(ROOT / rel) == h, rel


# ---------------------------------------------------------------- v3 (Reviewer finding V2-4)
@pytest.mark.parametrize(
    "who", ["reviewer-builder", "reviewer_scout", " Reviewer-Scout ", "Reviewer-ENGINEER", "reviewer-\uff22uilder"]
)
def test_approver_containing_author_or_role_rejected(env: tuple[Path, Path], who: str) -> None:
    root, h = env
    p = _proposal(h, root)
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["review"]["reviewer"] = who
    p.write_text(yaml.safe_dump(d), encoding="utf-8")
    with pytest.raises(HarnessError):
        load_proposal(p)


def test_approver_conflict_normalisation() -> None:
    from xferbench.harness.core import _approver_conflict

    assert _approver_conflict("reviewer-builder", "builder")
    assert _approver_conflict("Reviewer.S-c_o-u t", "builder")  # normalised substring of a role
    assert not _approver_conflict("reviewer", "builder")
    assert not _approver_conflict("reviewer-alice", "scout")


@pytest.mark.parametrize(
    "rf",
    [
        "reviews/review.md",
        "/abs/factory/inbox/reviewer/review.md",
        "factory/inbox/reviewer/../../../review.md",
        "factory/inbox/reviewerX/review.md",
        "factory/inbox/builder/review.md",
        "C:/factory/inbox/reviewer/review.md",
    ],
)
def test_review_file_must_sit_under_reviewer_inbox(env: tuple[Path, Path], rf: str) -> None:
    """V3-2: the Reviewer record must live under factory/inbox/reviewer/."""
    root, h = env
    (root / "reviews").mkdir(exist_ok=True)
    (root / "reviews/review.md").write_text("Reviewer: approved\n", encoding="utf-8")
    d = yaml.safe_load(_proposal(h, root).read_text(encoding="utf-8"))
    d["review"]["review_file"] = rf
    (h / "proposals/p1.yaml").write_text(yaml.safe_dump(d), encoding="utf-8")
    with pytest.raises(HarnessError, match="factory/inbox/reviewer"):
        apply_proposal(h / "proposals/p1.yaml", root, h)


def test_review_file_symlink_escape_rejected(env: tuple[Path, Path]) -> None:
    root, h = env
    (root / "outside.md").write_text("Reviewer: approved\n", encoding="utf-8")
    link = root / "factory/inbox/reviewer/link.md"
    try:
        link.symlink_to(root / "outside.md")
    except OSError:
        pytest.skip("symlinks unavailable")
    d = yaml.safe_load(_proposal(h, root).read_text(encoding="utf-8"))
    d["review"]["review_file"] = "factory/inbox/reviewer/link.md"
    d["review"]["review_sha256"] = sha256_file(root / "outside.md")
    (h / "proposals/p1.yaml").write_text(yaml.safe_dump(d), encoding="utf-8")
    with pytest.raises(HarnessError, match="outside"):
        apply_proposal(h / "proposals/p1.yaml", root, h)
