"""Canonical logical tables for the retail cold-pair task.

CSV and Parquet inputs are both converted to these Arrow schemas before any validation,
feature construction or evaluation, so both formats share one code path.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pyarrow as pa

OBSERVATION_STATES = ("observed", "observed_censored", "missing")
OFFER_STATES = ("offered", "not_offered")
STOCKOUT_STATES = ("in_stock", "stockout", "unknown")
SCENARIOS = ("PAIR0-E", "PAIR0-N")
QUALIFICATIONS = ("qualified", "edge_fixture", "disqualified")
LAUNCH_TYPES = ("natural", "simulated")
FEATURE_SCOPES = ("pair", "item", "location", "category", "global")
AVAILABILITY_CLASSES = ("calendar", "planned", "forecast", "scenario")


@dataclass(frozen=True)
class Column:
    name: str
    type: pa.DataType
    required: bool = True
    nullable: bool = False
    description: str = ""
    unit: str | None = None
    allowed: tuple[str, ...] | None = None


@dataclass(frozen=True)
class TableSpec:
    name: str
    description: str
    columns: tuple[Column, ...]
    key: tuple[str, ...]
    required_table: bool = True
    cardinality: str = ""
    extra_columns_allowed: bool = False
    dynamic_prefixes: tuple[str, ...] = field(default=())

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(name)

    def arrow_schema(self, extra: dict[str, pa.DataType] | None = None) -> pa.Schema:
        fields = [pa.field(c.name, c.type, nullable=c.nullable or not c.required) for c in self.columns]
        for name, typ in (extra or {}).items():
            fields.append(pa.field(name, typ, nullable=True))
        return pa.schema(fields)


S, D, F, I = pa.string(), pa.date32(), pa.float64(), pa.int64()

TABLES: dict[str, TableSpec] = {
    "observations": TableSpec(
        name="observations",
        description="One row per offered item-location week with measured sales or an explicit missing record.",
        key=("item_id", "fpg_id", "week_start"),
        cardinality="Each row joins exactly one offers row with offer_state='offered'.",
        columns=(
            Column("item_id", S, description="Stable item identifier, preserved as a string."),
            Column("fpg_id", S, description="Forecast Pixel Group (company demand area) identifier."),
            Column("week_start", D, description="Inclusive interval start (declared week boundary)."),
            Column("week_end", D, description="Exclusive interval end; week_start + 7 days."),
            Column(
                "units",
                F,
                nullable=True,
                unit="item_units",
                description="Observed unit sales; null only when observation_state='missing'. Zero is a real observation.",
            ),
            Column(
                "observation_state",
                S,
                allowed=OBSERVATION_STATES,
                description="observed | observed_censored (stock-limited sales) | missing (no measurement).",
            ),
            Column("known_at", D, description="Date the measurement became available (reporting delay)."),
        ),
    ),
    "offers": TableSpec(
        name="offers",
        description="Offer and availability calendar per pair-week. Absence of a row means never offered.",
        key=("item_id", "fpg_id", "week_start"),
        cardinality="At most one row per pair-week; observations are a subset of offered rows.",
        columns=(
            Column("item_id", S),
            Column("fpg_id", S),
            Column("week_start", D),
            Column("week_end", D),
            Column("offer_state", S, allowed=OFFER_STATES),
            Column("offered_days", I, unit="days", description="Days in the interval the item was offered (0-7)."),
            Column(
                "available_days",
                I,
                nullable=True,
                unit="days",
                description="Days with sellable stock; null when unknown.",
            ),
            Column("exposure_fraction", F, unit="fraction", description="offered_days / 7."),
            Column("stockout_state", S, allowed=STOCKOUT_STATES),
            Column("known_at", D, description="Date the realized availability became known."),
        ),
    ),
    "items": TableSpec(
        name="items",
        description="Item attributes, versioned by effective_from/known_at.",
        key=("item_id", "effective_from"),
        columns=(
            Column("item_id", S),
            Column("category", S, nullable=True, description="Category (seasonality level); null means unknown."),
            Column("product_type", S, nullable=True, description="Product type (broadest hierarchy level)."),
            Column(
                "subcategory",
                S,
                required=False,
                nullable=True,
                description="Subcategory (finest group level of the rate fallback hierarchy).",
            ),
            Column(
                "seasonality_class",
                S,
                required=False,
                nullable=True,
                description="Declared business class, e.g. seasonal or replenishable.",
            ),
            Column("effective_from", D),
            Column("known_at", D),
        ),
    ),
    "locations": TableSpec(
        name="locations",
        description="FPG attributes including household exposure and demographic shares, versioned.",
        key=("fpg_id", "effective_from"),
        extra_columns_allowed=True,
        dynamic_prefixes=("share_",),
        columns=(
            Column("fpg_id", S),
            Column("region", S, nullable=True),
            Column("fpg_open_at", D, nullable=True, description="Date the FPG began trading; null if before history."),
            Column("households", F, unit="households", description="Non-overlapping serviceable households (H)."),
            Column("effective_from", D),
            Column("known_at", D),
        ),
    ),
    "launches": TableSpec(
        name="launches",
        description="Natural (or explicitly simulated) first-offer events of an existing item at a location.",
        key=("launch_id",),
        columns=(
            Column("launch_id", S),
            Column("pair_id", S),
            Column("item_id", S),
            Column("fpg_id", S),
            Column("first_offer_at", D, description="Exact first offer date."),
            Column("first_offer_week", D, description="Week start containing first_offer_at."),
            Column("fpg_open_at", D, nullable=True),
            Column("origin", D, description="Cold forecast origin; equals first_offer_week (no interim pair sales)."),
            Column("scenario", S, allowed=SCENARIOS),
            Column("qualification", S, allowed=QUALIFICATIONS),
            Column("launch_type", S, allowed=LAUNCH_TYPES),
            Column("cohort_id", S),
            Column(
                "fixture_kind",
                S,
                required=False,
                nullable=True,
                description="Edge-fixture label (partial_week, stockouts, missing_targets, ...).",
            ),
        ),
    ),
    "origin_features": TableSpec(
        name="origin_features",
        description="Origin snapshots of company features (e.g. propensity P, item rank, item-cluster affinity).",
        key=("feature_name", "scope", "item_id", "fpg_id", "scope_id", "origin"),
        columns=(
            Column("feature_name", S),
            Column("scope", S, allowed=FEATURE_SCOPES),
            Column("item_id", S, nullable=True),
            Column("fpg_id", S, nullable=True),
            Column("scope_id", S, nullable=True),
            Column("origin", D),
            Column("value", F, nullable=True),
            Column("unit", S),
            Column("known_at", D),
            Column("source_version", S),
        ),
        required_table=False,
    ),
    "donors": TableSpec(
        name="donors",
        description="Optional pre-aggregated national/donor item series with household coverage.",
        key=("item_id", "donor_scope_id", "week_start"),
        columns=(
            Column("item_id", S),
            Column("donor_scope_id", S),
            Column("week_start", D),
            Column("week_end", D),
            Column("units", F, nullable=True, unit="item_units"),
            Column("household_coverage", F, unit="household_weeks"),
            Column("known_at", D),
            Column("source_version", S),
        ),
        required_table=False,
    ),
    "future_covariates": TableSpec(
        name="future_covariates",
        description="Inputs about future weeks that were genuinely known/planned/issued at origin.",
        key=("feature_name", "item_id", "fpg_id", "scope_id", "origin", "forecast_week"),
        columns=(
            Column("feature_name", S),
            Column("item_id", S, nullable=True),
            Column("fpg_id", S, nullable=True),
            Column("scope_id", S, nullable=True),
            Column("origin", D),
            Column("forecast_week", D),
            Column("value", F, nullable=True),
            Column("availability_class", S, allowed=AVAILABILITY_CLASSES),
            Column("known_at", D),
            Column("source_version", S),
        ),
        required_table=False,
    ),
}

FORECAST_COLUMNS: dict[str, pa.DataType] = {
    "request_id": S,
    "launch_id": S,
    "item_id": S,
    "fpg_id": S,
    "scenario": S,
    "origin": D,
    "horizon_week": I,
    "forecast_week": D,
    "point_units": F,
    "raw_point_units": F,
    "status": S,
    "reason": S,
    "point_statistic": S,
    "method_id": S,
    "variant_id": S,
    "run_id": S,
}
FORECAST_STATUSES = ("success", "fallback", "failed", "skipped")


def field_dictionary_markdown() -> str:
    """Render the canonical field dictionary as Markdown."""
    lines = [
        "# Field dictionary",
        "",
        "Canonical logical tables. Customer files may use other column names; map them in",
        "`metadata.json` under `tables.<table>.columns` (canonical name -> source column).",
        "IDs are always strings. Dates are ISO `YYYY-MM-DD` local dates in the declared timezone.",
        "In CSV an empty cell is null; nulls are never converted to zero.",
        "",
    ]
    for spec in TABLES.values():
        req = "required" if spec.required_table else "optional"
        lines += [f"## `{spec.name}` ({req})", "", spec.description, ""]
        lines += [f"Primary key: `{', '.join(spec.key)}`.", ""]
        if spec.cardinality:
            lines += [f"Join cardinality: {spec.cardinality}", ""]
        if spec.dynamic_prefixes:
            lines += [
                f"Additional columns with prefixes {list(spec.dynamic_prefixes)} are declared in metadata "
                "(e.g. demographic share columns).",
                "",
            ]
        lines += ["| Column | Type | Required | Nullable | Unit | Allowed | Meaning |", "|---|---|---|---|---|---|---|"]
        for c in spec.columns:
            allowed = ", ".join(c.allowed) if c.allowed else ""
            lines.append(
                f"| `{c.name}` | {c.type} | {'yes' if c.required else 'no'} | {'yes' if c.nullable else 'no'} "
                f"| {c.unit or ''} | {allowed} | {c.description} |"
            )
        lines.append("")
    return "\n".join(lines)


def table_json_schemas() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for spec in TABLES.values():
        out[spec.name] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"xferbench canonical table: {spec.name}",
            "description": spec.description,
            "x-primary-key": list(spec.key),
            "x-required-table": spec.required_table,
            "x-dynamic-prefixes": list(spec.dynamic_prefixes),
            "type": "object",
            "properties": {
                c.name: {
                    "x-arrow-type": str(c.type),
                    "description": c.description,
                    **({"enum": list(c.allowed)} if c.allowed else {}),
                    **({"x-unit": c.unit} if c.unit else {}),
                    "x-nullable": c.nullable,
                }
                for c in spec.columns
            },
            "required": [c.name for c in spec.columns if c.required],
        }
    return out
