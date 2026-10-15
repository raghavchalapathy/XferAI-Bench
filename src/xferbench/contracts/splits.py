"""Frozen split manifest (splits.json)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from xferbench.util import hash_obj


class LaunchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    launch_id: str
    item_id: str
    fpg_id: str
    scenario: str
    origin: str
    board: str
    ranked: bool
    qualification: str
    launch_type: str
    cohort_id: str
    fixture_kind: str | None = None
    target_end: str
    declared_label_available_at: str
    label_available_at: str | None
    label_status: Literal["complete", "incomplete"]
    measured_target_weeks: int
    missing_target_weeks: int


class StageSplit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    origin_start: str
    origin_end: str
    origins: list[str]
    launches: list[LaunchRecord]
    excluded_pairs: list[str]
    excluded_fpgs: list[str]
    fit_cutoff: str | None = None
    fit_launch_ids: list[str] = Field(default_factory=list)
    fit_exclusions: list[dict] = Field(default_factory=list)
    scoring_cutoff: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)


class SplitCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    check: str
    passed: bool
    detail: str
    stage: str | None = None
    launch_id: str | None = None


class SplitManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    split_schema_version: Literal["1.0"] = "1.0"
    dataset_id: str
    dataset_version: str
    dataset_hash: str
    metadata_hash: str
    domain: str
    task_profile: str
    horizon_weeks: int
    reporting_delay_days: int
    week_start: str
    stages: dict[str, StageSplit]
    selection_cutoff: str | None
    checks: list[SplitCheck]
    split_hash: str = ""

    def compute_hash(self) -> str:
        return hash_obj(self.model_dump(mode="json", exclude={"split_hash"}))

    def frozen(self) -> SplitManifest:
        return self.model_copy(update={"split_hash": self.compute_hash()})

    def verify(self) -> bool:
        return bool(self.split_hash) and self.split_hash == self.compute_hash()

    @property
    def failed_checks(self) -> list[SplitCheck]:
        return [c for c in self.checks if not c.passed]
