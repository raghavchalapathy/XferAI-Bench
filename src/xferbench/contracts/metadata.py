"""Dataset metadata contract (metadata.json)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from xferbench.contracts.tables import TABLES

METADATA_SCHEMA_VERSION = "1.0"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatasetInfo(_Strict):
    id: str
    version: str
    description: str = ""
    synthetic: bool = False
    expected_hash: str | None = Field(
        default=None, description="If set, loading fails unless the canonical content hash matches."
    )
    generator: dict[str, object] | None = None


class TimeSpec(_Strict):
    timezone: str = "America/Los_Angeles"
    frequency: Literal["weekly"] = "weekly"
    week_start: Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] = "Monday"
    interval: Literal["[start,end)"] = "[start,end)"
    reporting_delay_days: int = Field(7, ge=0, le=365)
    horizon_weeks: int = Field(52, ge=1, le=156)
    origin_rule: Literal["first_offer_week"] = "first_offer_week"
    partial_week_policy: Literal["score_as_observed_no_origin_advance"] = "score_as_observed_no_origin_advance"
    dates_interpretation: str = "Local calendar dates; known_at means available from 00:00 local on that date."


class TargetSpec(_Strict):
    column: str = "units"
    name: str = "observed_unit_sales"
    unit: str = "item_units"
    nonnegative: bool = True
    returns_policy: str = "gross units; no returns in this dataset"
    aggregation: Literal["sum_weekly"] = "sum_weekly"


class TableSource(_Strict):
    path: str
    format: Literal["csv", "parquet"]
    columns: dict[str, str] = Field(
        default_factory=dict, description="canonical column -> source column; omitted means same name."
    )
    extra_columns: list[str] = Field(default_factory=list, description="Additional declared source columns kept.")


class HouseholdSpec(_Strict):
    column: str = "households"
    unit: str = "households"
    population_definition: str = "non-overlapping serviceable households"
    overlap_policy: Literal["non_overlapping"] = "non_overlapping"


class PropensitySpec(_Strict):
    feature_name: str = "propensity_rate"
    unit: Literal["units_per_household_per_week"] = "units_per_household_per_week"
    season_neutral: bool = True
    includes_demographic_affinity: bool = True
    provenance: str = "origin-valid estimate from permitted pre-origin data"


class SeasonalitySpec(_Strict):
    estimator: Literal["donor_category_ratio_v1"] = "donor_category_ratio_v1"
    unit: str = "dimensionless"
    normalization: str = "mean one over the 52-position annual cycle"
    max_cycles: int = Field(3, ge=1, le=10)
    smoothing_window: int = Field(3, ge=1, le=9)


class FeatureSpec(_Strict):
    households: HouseholdSpec = Field(default_factory=HouseholdSpec)
    propensity: PropensitySpec | None = Field(default_factory=PropensitySpec)
    seasonality: SeasonalitySpec = Field(default_factory=SeasonalitySpec)
    demographic_share_columns: list[str] = Field(default_factory=list)
    item_rank_feature: str | None = "item_prelaunch_rank"
    item_affinity_prefix: str | None = "item_affinity_"


class DonorPolicy(_Strict):
    scope: str = "all origin-valid observations at non-held-out pairs and locations"
    exclusions: Literal["stage_holdout_pairs_and_new_fpgs"] = "stage_holdout_pairs_and_new_fpgs"
    consistent_exposure_window_weeks: int = Field(52, ge=4, le=156)
    consistent_exposure_min_fraction: float = Field(0.9, gt=0, le=1)
    national_aggregate_note: str = (
        "National aggregates are computed by the engine from observations so exclusions are enforceable."
    )


class StageWindow(_Strict):
    origin_start: str
    origin_end: str


class CohortSpec(_Strict):
    stages: dict[str, StageWindow]
    selection_weights: dict[str, float] = Field(default_factory=lambda: {"PAIR0-E": 0.5, "PAIR0-N": 0.5})
    ranked_qualifications: list[str] = Field(default_factory=lambda: ["qualified"])
    ranked_launch_types: list[str] = Field(default_factory=lambda: ["natural"])
    test_fit_stages: list[str] = Field(
        default_factory=lambda: ["train", "validation"],
        description="Cohorts whose (already available) labels may train test-stage fits after selection is frozen.",
    )

    @field_validator("stages")
    @classmethod
    def _need_stages(cls, v: dict[str, StageWindow]) -> dict[str, StageWindow]:
        missing = {"train", "validation", "test"} - set(v)
        if missing:
            raise ValueError(f"cohorts.stages must define train, validation and test; missing {sorted(missing)}")
        return v

    @field_validator("selection_weights")
    @classmethod
    def _weights(cls, v: dict[str, float]) -> dict[str, float]:
        if abs(sum(v.values()) - 1.0) > 1e-9 or any(w < 0 for w in v.values()):
            raise ValueError("selection_weights must be nonnegative and sum to 1")
        return v


class MetricSpec(_Strict):
    primary: Literal["WMAPE"] = "WMAPE"
    definitions: dict[str, str] = Field(
        default_factory=lambda: {
            "WMAPE": "sum(abs(F-A))/sum(A) over the fixed eligible population",
            "Bias": "sum(F)/sum(A)-1 (signed)",
            "MAE": "mean(abs(F-A))",
        }
    )
    zero_denominator: str = "undefined: JSON null with reason; N/A in reports; no epsilon"
    eligible_weeks: Literal["measured_offered_weeks"] = "measured_offered_weeks"
    failure_policy: Literal["unrankable"] = "unrankable"


class ResourceLimits(_Strict):
    max_run_seconds: float | None = Field(None, gt=0)
    max_fit_seconds_per_method: float | None = Field(None, gt=0)


class Rights(_Strict):
    data_owner: str
    permitted_use: str
    input_license: str = "not declared"


class Privacy(_Strict):
    runtime_network: Literal["off"] = "off"
    service_calls: Literal["off", "opt_in"] = "off"
    show_raw_rows_in_report: bool = False


class Metadata(_Strict):
    schema_version: Literal["1.0"] = "1.0"
    dataset: DatasetInfo
    domain_plugin: str = "retail"
    task_profile: Literal["retail_pair_zero_v1"] = "retail_pair_zero_v1"
    entity_roles: dict[str, str] = Field(default_factory=lambda: {"item": "item_id", "location": "fpg_id"})
    request_key: list[str] = Field(default_factory=lambda: ["item_id", "fpg_id", "origin", "horizon_week"])
    layout: Literal["multi_table"] = "multi_table"
    time: TimeSpec = Field(default_factory=TimeSpec)
    target: TargetSpec = Field(default_factory=TargetSpec)
    tables: dict[str, TableSource]
    semantics: dict[str, str] = Field(
        default_factory=lambda: {
            "missing": "null units with observation_state='missing'; never zero",
            "observed_zero": "offered, measured week with zero sales",
            "never_offered": "no offers row for the pair-week",
            "stockout": "observation_state='observed_censored'; sales observed, demand unknown",
            "partial_exposure": "offered_days<7; origin stays at the week containing first offer",
        }
    )
    features: FeatureSpec = Field(default_factory=FeatureSpec)
    donor_policy: DonorPolicy = Field(default_factory=DonorPolicy)
    cohorts: CohortSpec
    metrics: MetricSpec = Field(default_factory=MetricSpec)
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    rights: Rights
    privacy: Privacy = Field(default_factory=Privacy)

    @field_validator("tables")
    @classmethod
    def _tables(cls, v: dict[str, TableSource]) -> dict[str, TableSource]:
        unknown = set(v) - set(TABLES)
        if unknown:
            raise ValueError(f"unknown logical tables {sorted(unknown)}; allowed: {sorted(TABLES)}")
        missing = [n for n, s in TABLES.items() if s.required_table and n not in v]
        if missing:
            raise ValueError(f"required logical tables missing: {missing}")
        for name, src in v.items():
            canon = set(TABLES[name].column_names)
            bad = set(src.columns) - canon
            if bad:
                raise ValueError(f"tables.{name}.columns maps unknown canonical columns {sorted(bad)}")
            if "_synthetic_truth" in Path(src.path).parts:
                raise ValueError(f"tables.{name}.path points into hidden synthetic truth; models may not read it")
        return v


def load_metadata(path: Path) -> Metadata:
    from xferbench.util import read_json

    return Metadata.model_validate(read_json(path))


def metadata_json_schema() -> dict:
    return Metadata.model_json_schema()
