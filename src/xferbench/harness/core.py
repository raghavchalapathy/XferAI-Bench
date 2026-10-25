"""Harness mechanics with guardrails.

Files (under a harness dir, default ``harness/``):
  lessons.jsonl                 append-only, one schema-validated Lesson per line
  BEST_PRACTICES.v<N>.yaml      versioned rules; the highest N is current
  CHANGELOG.md                  one entry per adopted proposal
  proposals/<id>.yaml           Builder/Scout proposals; Reviewer record required before adoption
  watch.yaml                    revisit sources: new papers, review cadence
  PROTECTED_HASHES.json         sha256 of the protected evaluator files

Guardrails: proposals cannot touch the protected evaluator or its guards (normalised path check on the declared
AND the actual git diff, plus a hash check); results need an existing
run manifest and evidence; synthetic results can never be labelled as rankings; nothing is adopted without an
approved Reviewer record.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import posixpath
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROTECTED_PREFIX = "src/xferbench/evaluation/"
# Protected paths (directories cover everything below them). Compared after normalisation, case-insensitively.
PROTECTED_PATHS = (
    "src/xferbench/evaluation",
    "src/xferbench/scalable_eval",
    "harness/protected_hashes.json",
    "tests/unit/test_scalable_eval.py",
    "tests/review",
)
# Synthetic results may only carry one of these labels (allow-list; normalised: case, whitespace, trailing '.').
SYNTHETIC_LABELS = frozenset(
    {
        "synthetic interface test - not a ranking. synthetic data only checks the software, not which method is better",
        "synthetic interface test, not rankings",
        "synthetic interface test, not a ranking",
        "synthetic smoke test, not a ranking",
        "not a ranking",
    }
)


class HarnessError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _norm_label(label: str) -> str:
    return " ".join(label.lower().split()).rstrip(".")


def _check_label(data_class: str, label: str) -> None:
    if data_class == "synthetic" and _norm_label(label) not in SYNTHETIC_LABELS:
        raise ValueError(f"synthetic results must use an approved non-ranking label, one of {sorted(SYNTHETIC_LABELS)}")


def normalise_path(path: str) -> str:
    """Backslashes -> '/', collapse '//' and '.', resolve '..', lower-case; absolute paths keep their leading '/'."""
    p = path.replace("\\", "/").strip()
    absolute = p.startswith("/") or re.match(r"^[a-zA-Z]:/", p) is not None
    p = posixpath.normpath(re.sub(r"^[a-zA-Z]:", "", p)).lower()
    return p if absolute else p.lstrip("/")


def protected_hit(path: str) -> str | None:
    """Return the protected path that ``path`` touches (itself, a child, a parent dir, or an absolute path into it)."""
    n = normalise_path(path)
    for prot in PROTECTED_PATHS:
        if n in ("", ".", "/"):
            return prot  # the whole repo
        if n == prot or n.startswith(prot + "/") or prot.startswith(n.rstrip("/") + "/"):
            return prot
        if n.startswith("/") and ("/" + prot + "/" in n + "/"):
            return prot
    return None


def _git_touched(root: Path, base: str) -> list[str]:
    def run(*args: str) -> list[str]:
        out = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=True
        ).stdout
        return [x for x in out.splitlines() if x.strip()]

    return sorted(
        set(run("diff", "--name-only", "--no-renames", base)) | set(run("ls-files", "--others", "--exclude-standard"))
    )


def actual_touches(root: Path, base: str | None = "HEAD") -> list[str] | None:
    """Paths changed in the working tree vs ``base`` (plus untracked), each resolved through symlinks.

    Returns None when ``root`` is not a git work tree.
    """
    if base is None or not (root / ".git").exists():
        return None
    rr = root.resolve()
    out = []
    for rel in _git_touched(root, base):
        out.append(rel)
        real = (root / rel).resolve()
        if real.is_relative_to(rr):
            out.append(real.relative_to(rr).as_posix())
    return out


def guard_paths(paths: list[str], root: Path | None = None) -> None:
    for p in paths:
        cand = [p]
        if root is not None and not Path(p).is_absolute():
            real = (root / p).resolve()
            if real.is_relative_to(root.resolve()):
                cand.append(real.relative_to(root.resolve()).as_posix())  # symlink into a protected path
        for c in cand:
            hit = protected_hit(c)
            if hit:
                raise ValueError(f"proposals may not touch the protected evaluator or its guards ({hit}): {p}")


class ResultRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_manifest: str
    run_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence: str
    data_class: Literal["synthetic", "real"]
    label: str
    objective: float | None = None

    @model_validator(mode="after")
    def _label(self) -> ResultRef:
        _check_label(self.data_class, self.label)
        return self

    def verify_files(self, root: Path) -> None:
        man, ev = root / self.run_manifest, root / self.evidence
        if not man.is_file():
            raise HarnessError(f"run manifest missing: {self.run_manifest}")
        if not ev.exists():
            raise HarnessError(f"evidence missing: {self.evidence}")
        if sha256_file(man) != self.run_manifest_sha256:
            raise HarnessError(f"run manifest hash mismatch: {self.run_manifest}")


class Lesson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: dt.date
    experiment: str
    what_changed: str = Field(min_length=3)
    status: Literal["success", "failed"]
    result: ResultRef
    lesson: str = ""
    accepted: bool = False


NON_REVIEWERS = {"builder", "scout", "engineer", "lead", "owner"}


def _norm_id(s: str) -> str:
    """Lower-case and keep only letters and digits, so 'Reviewer_Scout ' and 'reviewer-scout' compare equal."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", s).lower() if ch.isalnum())


def _approver_conflict(reviewer: str, author: str) -> bool:
    """True when the approver id is, or contains, the author id or any non-Reviewer role (V2-4)."""
    who = _norm_id(reviewer)
    names = {r for r in NON_REVIEWERS} | ({author} if author else set())
    return who in names or any(n in who for n in names)


class Review(BaseModel):
    """Reviewer record. ``reviewer`` must be a Reviewer id (``reviewer`` or ``reviewer-<name>``); approvals must
    cite the review file and its sha256, which :func:`check_proposal` verifies."""

    model_config = ConfigDict(extra="forbid")
    reviewer: str = Field(pattern=r"^(?i:reviewer)([-_][A-Za-z0-9._-]+)?$")
    decision: Literal["approved", "rejected", "changes_requested"]
    date: dt.date
    review_file: str | None = None
    review_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    notes: str = ""

    @model_validator(mode="after")
    def _evidence(self) -> Review:
        if self.decision == "approved" and not (self.review_file and self.review_sha256):
            raise ValueError("an approval must cite review_file and review_sha256")
        return self


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    author_role: Literal["builder", "scout"]
    summary: str
    set_rules: dict[str, str] = Field(default_factory=dict)
    remove_rules: list[str] = Field(default_factory=list)
    touches: list[str] = Field(default_factory=list)
    results: list[ResultRef] = Field(default_factory=list)
    review: Review | None = None

    @field_validator("touches")
    @classmethod
    def _no_evaluator(cls, v: list[str]) -> list[str]:
        guard_paths(v)
        return v

    @model_validator(mode="before")
    @classmethod
    def _no_self_approval(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("review"), dict):
            who = str(data["review"].get("reviewer", ""))
            author = _norm_id(str(data.get("author_role", "")))
            if _approver_conflict(who, author):
                raise ValueError(f"self-approval: reviewer {who.strip()!r} is not an independent Reviewer")
        return data


class BestPractices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    review_date: dt.date
    review_every_days: int = 90
    rules: dict[str, str]


# ---------------------------------------------------------------- lessons
def append_lesson(harness: Path, root: Path, lesson: Lesson) -> None:
    lesson.result.verify_files(root)
    with (harness / "lessons.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(lesson.model_dump_json() + "\n")


def read_lessons(harness: Path) -> list[Lesson]:
    p = harness / "lessons.jsonl"
    if not p.exists():
        return []
    return [Lesson.model_validate_json(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def lesson_from_experiment(out: Path, root: Path, experiment: str, what_changed: str) -> Lesson:
    """Build a Lesson from an experiment output directory (results.json + test-run/run_manifest.json)."""
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    man = out / "test-run" / "run_manifest.json"
    rows = [r for r in res["test_rows"] if r["objective"] is not None]
    best = min((r["objective"] for r in rows), default=None)
    rel = lambda p: Path(p).resolve().relative_to(root.resolve()).as_posix()  # noqa: E731
    return Lesson(
        date=dt.date.today(),
        experiment=experiment,
        what_changed=what_changed,
        status="success" if rows else "failed",
        result=ResultRef(
            run_manifest=rel(man),
            run_manifest_sha256=sha256_file(man),
            evidence=rel(out / "results.json"),
            data_class=res["data"]["flavour"],
            label=res["label"],
            objective=best,
        ),
    )


# ---------------------------------------------------------------- best practices
def _versions(harness: Path) -> list[tuple[int, Path]]:
    out = []
    for p in harness.glob("BEST_PRACTICES.v*.yaml"):
        m = re.fullmatch(r"BEST_PRACTICES\.v(\d+)\.yaml", p.name)
        if m:
            out.append((int(m.group(1)), p))
    return sorted(out)


def current_practices(harness: Path) -> tuple[BestPractices, Path]:
    vs = _versions(harness)
    if not vs:
        raise HarnessError(f"no BEST_PRACTICES.v*.yaml in {harness}")
    bp = BestPractices.model_validate(yaml.safe_load(vs[-1][1].read_text(encoding="utf-8")))
    if bp.version != vs[-1][0]:
        raise HarnessError(f"{vs[-1][1].name}: version field {bp.version} != file version")
    return bp, vs[-1][1]


def check_protected_hashes(root: Path, harness: Path) -> None:
    ref = json.loads((harness / "PROTECTED_HASHES.json").read_text(encoding="utf-8"))
    for rel, h in ref.items():
        if sha256_file(root / rel) != h:
            raise HarnessError(f"protected evaluator file changed: {rel}")


def load_proposal(path: Path) -> Proposal:
    try:
        return Proposal.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValueError as exc:
        raise HarnessError(f"{path.name}: {exc}") from exc


REVIEW_DIR = "factory/inbox/reviewer"


def review_file_path(root: Path, review_file: str) -> Path:
    """V3-2: a Reviewer record must sit under factory/inbox/reviewer/ (no '..', no absolute path, no symlink escape)."""
    raw = review_file.replace("\\", "/")
    norm = posixpath.normpath(raw)
    if (
        raw.startswith("/")
        or re.match(r"^[A-Za-z]:", raw)
        or norm.startswith("..")
        or not norm.startswith(REVIEW_DIR + "/")
    ):
        raise HarnessError(f"review_file {review_file!r} must be a relative path under {REVIEW_DIR}/")
    rf = root / norm
    base = (root / REVIEW_DIR).resolve()
    if not rf.resolve().is_relative_to(base):
        raise HarnessError(f"review_file {review_file!r} resolves outside {REVIEW_DIR}/")
    return rf


def check_proposal(p: Proposal, root: Path, harness: Path, base: str | None = "HEAD") -> None:
    """Guardrails. ``touches`` is not trusted: in a git work tree the real diff vs ``base`` (plus untracked files,
    resolved through symlinks) is checked against the protected paths and must be declared in ``touches``."""
    check_protected_hashes(root, harness)
    try:
        guard_paths(p.touches, root)
        actual = actual_touches(root, base)
        if actual is not None:
            guard_paths(actual, root)
            declared = {normalise_path(x) for x in p.touches}
            undeclared = sorted({a for a in actual if normalise_path(a) not in declared} - {_rel(harness, root, p.id)})
            if undeclared:
                raise HarnessError(f"proposal {p.id}: changed files not declared in touches: {undeclared}")
    except ValueError as exc:
        raise HarnessError(str(exc)) from exc
    for r in p.results:
        r.verify_files(root)
    if p.review is None or p.review.decision != "approved":
        raise HarnessError(f"proposal {p.id} has no approved Reviewer record; not adopted")
    rf = review_file_path(root, str(p.review.review_file))
    if not rf.is_file() or sha256_file(rf) != p.review.review_sha256:
        raise HarnessError(f"proposal {p.id}: Reviewer record file missing or sha256 mismatch: {p.review.review_file}")
    bp, _ = current_practices(harness)
    unknown = [r for r in p.remove_rules if r not in bp.rules]
    if unknown:
        raise HarnessError(f"proposal {p.id} removes unknown rules {unknown}")


def _rel(harness: Path, root: Path, pid: str) -> str:
    try:
        return (harness / "proposals" / f"{pid}.yaml").resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return ""


def apply_proposal(path: Path, root: Path, harness: Path) -> Path:
    """Adopt an approved proposal: write BEST_PRACTICES.v<N+1>.yaml and log it in CHANGELOG.md."""
    p = load_proposal(path)
    check_proposal(p, root, harness)
    assert p.review is not None
    bp, _ = current_practices(harness)
    log = harness / "CHANGELOG.md"
    if log.exists() and f"proposal `{p.id}`" in log.read_text(encoding="utf-8"):
        raise HarnessError(f"proposal {p.id} already adopted")
    rules = {k: v for k, v in bp.rules.items() if k not in p.remove_rules} | p.set_rules
    new = BestPractices(
        version=bp.version + 1, review_date=p.review.date, review_every_days=bp.review_every_days, rules=rules
    )
    dest = harness / f"BEST_PRACTICES.v{new.version}.yaml"
    dest.write_text(yaml.safe_dump(new.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    entry = (
        f"\n## v{new.version} - {p.review.date}\n\nproposal `{p.id}` by {p.author_role}: {p.summary}. "
        f"Approved by {p.review.reviewer}. Set: {sorted(p.set_rules)}; removed: {p.remove_rules}.\n"
    )
    with log.open("a", encoding="utf-8") as fh:
        fh.write(entry)
    return dest


# ---------------------------------------------------------------- triggers
def due_triggers(harness: Path, today: dt.date | None = None) -> list[dict[str, Any]]:
    today = today or dt.date.today()
    due: list[dict[str, Any]] = []
    watch_p = harness / "watch.yaml"
    watch = yaml.safe_load(watch_p.read_text(encoding="utf-8")) if watch_p.exists() else {}
    for paper in (watch or {}).get("papers", []):
        if paper.get("status") == "new":
            due.append({"trigger": "new_paper", "detail": f"{paper.get('title')} ({paper.get('url')})"})
    lessons = read_lessons(harness)
    if lessons and lessons[-1].status == "failed":
        due.append({"trigger": "failed_run", "detail": f"{lessons[-1].experiment} on {lessons[-1].date}"})
    accepted = [x for x in lessons if x.accepted and x.result.objective is not None]
    if accepted:
        ref = accepted[-1]
        for x in lessons:
            same = x.experiment == ref.experiment and x.result.data_class == ref.result.data_class
            worse = x.result.objective is not None and x.result.objective > ref.result.objective  # type: ignore[operator]
            if same and x.date >= ref.date and x is not ref and worse:
                due.append(
                    {
                        "trigger": "regression",
                        "detail": f"{x.experiment}: {x.result.objective:.4f} > accepted {ref.result.objective:.4f}",
                    }
                )
    bp, path = current_practices(harness)
    if today > bp.review_date + dt.timedelta(days=bp.review_every_days):
        due.append({"trigger": "stale_review", "detail": f"{path.name} last reviewed {bp.review_date}"})
    return due
