"""Typed method contract: capabilities, registry states and persisted artifacts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ImplementationState = Literal["implemented", "experimental", "unimplemented", "config_required"]
ExecutionState = Literal["success", "not_run", "not_installed", "failed"]
EligibilityState = Literal[
    "compatible", "unsupported_history", "missing_features", "license_blocked", "service_required"
]
Board = Literal["cold_c0", "cold_composite", "donor_only", "warm_reference"]
PointStatistic = Literal["mean", "median", "quantile", "unspecified"]


class Rights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code_license: str
    code_source: str
    code_revision: str | None = None
    weights: str = "none (trained on the user's permitted data)"
    weights_revision: str | None = None
    service_terms: str | None = None
    commercial_use: Literal["permitted", "restricted", "unknown", "not_applicable"] = "permitted"
    notes: str = ""


class CapabilitySpec(BaseModel):
    """What a recipe accepts and produces. Checked before any fit/predict."""

    model_config = ConfigDict(extra="forbid")
    method_id: str
    version: str
    family: str
    display_name: str
    task_profiles: list[str]
    board: Board
    identity: Literal["native", "composite"]
    min_own_pair_history_weeks: int = 0
    min_donor_history_weeks: int = 0
    required_tables: list[str] = Field(default_factory=lambda: ["observations", "offers", "items", "locations"])
    required_features: list[str] = Field(default_factory=list)
    supports_new_location: bool = True
    point_statistic: PointStatistic = "mean"
    supports_quantiles: bool = False
    supports_probability_zero: bool = False
    compute: str = "cpu-light"
    optional_extra: str | None = None
    python_modules: list[str] = Field(default_factory=list)
    rights: Rights
    history_rules: str = ""
    used_features: list[str] = Field(default_factory=list)
    description: str = ""


class ModelArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_schema_version: Literal["1.0"] = "1.0"
    method_id: str
    variant_id: str
    method_version: str
    config: dict[str, Any]
    params: dict[str, Any] = Field(default_factory=dict)
    fit_cutoff: str
    n_training_launches: int
    training_data_hash: str
    notes: str = ""


class RegistryEntryReport(BaseModel):
    """One row of method_support.json."""

    model_config = ConfigDict(extra="forbid")
    method_id: str
    version: str
    family: str
    display_name: str
    board: Board
    identity: Literal["native", "composite"]
    implementation_state: ImplementationState
    execution_state: ExecutionState
    eligibility_state: EligibilityState | None
    optional_extra: str | None
    point_statistic: PointStatistic
    rights: Rights
    history_rules: str
    used_features: list[str]
    reason: str
    remedy: str
    affected_requests: int = 0
