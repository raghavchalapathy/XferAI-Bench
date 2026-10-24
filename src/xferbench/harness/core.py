"""Harness mechanics with guardrails.

Files (under a harness dir, default ``harness/``):
  lessons.jsonl                 append-only, one schema-validated Lesson per line
  BEST_PRACTICES.v<N>.yaml      versioned rules; the highest N is current
  CHANGELOG.md                  one entry per adopted proposal
  proposals/<id>.yaml           Builder/Scout proposals; Reviewer record required before adoption
  watch.yaml                    revisit sources: new papers, review cadence
  PROTECTED_HASHES.json         sha256 of the protected evaluator files

Guardrails: proposals cannot touch the protected evaluator (path check and hash check); results need an existing
run manifest and evidence; synthetic results can never be labelled as rankings; nothing is adopted without an
approved Reviewer record.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROTECTED_PREFIX = "src/xferbench/evaluation/"
RANKING_WORDS = re.compile(r"\b(rank|ranking|rankings|leader|winner|best|beats|outperform\w*|sota)\b", re.I)
NOT_RANKING = re.compile(r"not (a )?rankings?", re.I)


class HarnessError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_label(data_class: str, label: str) -> None:
    claim = not NOT_RANKING.search(label) or RANKING_WORDS.search(NOT_RANKING.sub("", label))
    if data_class == "synthetic" and claim:
        raise ValueError("synthetic results must be labelled 'not a ranking' and make no ranking claim")


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


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer: str = Field(min_length=1)
    decision: Literal["approved", "rejected", "changes_requested"]
    date: dt.date
    notes: str = ""


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
        for p in v:
            if p.replace("\\", "/").lstrip("./").startswith(PROTECTED_PREFIX):
                raise ValueError(f"proposals may not touch the protected evaluator: {p}")
        return v


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


def check_proposal(p: Proposal, root: Path, harness: Path) -> None:
    check_protected_hashes(root, harness)
    for r in p.results:
        r.verify_files(root)
    if p.review is None or p.review.decision != "approved":
        raise HarnessError(f"proposal {p.id} has no approved Reviewer record; not adopted")
    bp, _ = current_practices(harness)
    unknown = [r for r in p.remove_rules if r not in bp.rules]
    if unknown:
        raise HarnessError(f"proposal {p.id} removes unknown rules {unknown}")


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
