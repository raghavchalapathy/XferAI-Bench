"""Validation selection policy and the frozen selection record."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SelectionPolicy(BaseModel):
    """Preregistered rule applied to VALIDATION results only."""

    model_config = ConfigDict(extra="forbid")
    policy_version: Literal["1.0"] = "1.0"
    objective: Literal["equal_scenario_wmape"] = "equal_scenario_wmape"
    scenario_weights: dict[str, float] = Field(default_factory=lambda: {"PAIR0-E": 0.5, "PAIR0-N": 0.5})
    max_abs_bias: float = Field(0.5, gt=0, description="Symmetric |Bias| limit applied to EACH scenario.")
    min_coverage: float = Field(1.0, gt=0, le=1)
    max_total_seconds: float | None = Field(None, gt=0)
    undefined_metric_rule: Literal["ineligible"] = "ineligible"
    board: str = "cold_c0"

    @field_validator("scenario_weights")
    @classmethod
    def _w(cls, v: dict[str, float]) -> dict[str, float]:
        if abs(sum(v.values()) - 1) > 1e-9 or any(x < 0 for x in v.values()):
            raise ValueError("scenario_weights must be nonnegative and sum to 1")
        return v


class SelectedVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method_id: str
    variant_id: str
    config: dict
    objective: float | None
    per_scenario: dict[str, dict]
    eligible: bool
    reason: str


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selection_schema_version: Literal["1.0"] = "1.0"
    created_at: str
    policy: SelectionPolicy
    policy_hash: str
    validation_run_id: str
    validation_manifest_hash: str
    dataset_hash: str
    split_hash: str
    selection_cutoff: str
    families: list[SelectedVariant]
    # V2-1: omitted from selection.json on synthetic runs (interface test, not a ranking)
    recommended: str | None = None
    recommended_reason: str | None = None
    rejected_variants: list[dict]
