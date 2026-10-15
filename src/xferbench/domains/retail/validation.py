"""Retail data validation: keys, joins, units, shares, exposure, timing and cold-pair rules."""

from __future__ import annotations

import numpy as np
import pandas as pd

from xferbench.calendar import WEEK, WEEKDAYS
from xferbench.contracts.tables import TABLES
from xferbench.data.io import Dataset
from xferbench.data.issues import Issue, Severity

MAX_ROW_IDS = 10


def _row_ids(df: pd.DataFrame, cols: list[str]) -> list[str]:
    out = []
    for row in df[cols].head(MAX_ROW_IDS).itertuples(index=False):
        out.append(
            "|".join(
                "" if pd.isna(v) else (v.date().isoformat() if isinstance(v, pd.Timestamp) else str(v)) for v in row
            )
        )
    return out


def _flag(
    issues: list[Issue],
    mask: pd.Series | np.ndarray,
    df: pd.DataFrame,
    severity: Severity,
    code: str,
    table: str,
    column: str | None,
    message: str,
    suggestion: str = "",
) -> None:
    mask = pd.Series(mask, index=df.index) if not isinstance(mask, pd.Series) else mask
    n = int(mask.sum())
    if n:
        key = [c for c in TABLES[table].key if c in df.columns] if table in TABLES else list(df.columns[:3])
        issues.append(
            Issue(
                severity,
                code,
                f"{message} ({n} rows)",
                table,
                column,
                _row_ids(df[mask], key),
                n,
                suggestion,
            )
        )


def validate_retail(ds: Dataset) -> list[Issue]:
    md = ds.metadata
    issues: list[Issue] = list(ds.load_issues)
    t = ds.tables
    wd = WEEKDAYS[md.time.week_start]

    for name, df in t.items():
        spec = TABLES[name]
        key = [k for k in spec.key if k in df.columns]
        _flag(
            issues,
            df.duplicated(key, keep=False),
            df,
            "error",
            "duplicate_key",
            name,
            ",".join(key),
            "duplicate primary key",
            "Deduplicate the source rows or fix the column mapping.",
        )
        for col in spec.columns:
            if col.name in df.columns and col.required and not col.nullable:
                _flag(
                    issues,
                    df[col.name].isna(),
                    df,
                    "error",
                    "null_in_required",
                    name,
                    col.name,
                    "required value is null",
                    "Supply the value; nulls are never imputed.",
                )
            if col.allowed and col.name in df.columns:
                bad = df[col.name].notna() & ~df[col.name].isin(col.allowed)
                _flag(
                    issues,
                    bad,
                    df,
                    "error",
                    "invalid_enum",
                    name,
                    col.name,
                    f"value not in {list(col.allowed)}",
                    "Map source codes to the allowed values.",
                )
        for wcol in ("week_start",):
            if wcol in df.columns:
                _flag(
                    issues,
                    df[wcol].notna() & (df[wcol].dt.weekday != wd),
                    df,
                    "error",
                    "week_boundary",
                    name,
                    wcol,
                    f"week_start is not a {md.time.week_start}",
                    "Align weeks to the declared boundary in metadata.time.week_start.",
                )
                if "week_end" in df.columns:
                    _flag(
                        issues,
                        (df["week_end"] - df[wcol]) != WEEK,
                        df,
                        "error",
                        "interval_length",
                        name,
                        "week_end",
                        "week_end must equal week_start + 7 days (half-open interval)",
                    )
                if "known_at" in df.columns and "week_end" in df.columns:
                    _flag(
                        issues,
                        df["known_at"] < df["week_end"],
                        df,
                        "error",
                        "known_before_interval_end",
                        name,
                        "known_at",
                        "known_at precedes the end of the measured interval",
                        "known_at must be when the value became available, not the week start.",
                    )

    obs = t["observations"]
    _flag(
        issues,
        obs["units"].notna() & (obs["units"] < 0),
        obs,
        "error",
        "negative_units",
        "observations",
        "units",
        "negative units",
        "Declare a returns policy; negative net units are not supported in v1.",
    )
    _flag(
        issues,
        obs["units"].notna() & ~np.isfinite(obs["units"].fillna(0)),
        obs,
        "error",
        "nonfinite_units",
        "observations",
        "units",
        "non-finite units",
    )
    _flag(
        issues,
        (obs["observation_state"] == "missing") & obs["units"].notna(),
        obs,
        "error",
        "missing_with_value",
        "observations",
        "units",
        "missing observation carries a value",
    )
    _flag(
        issues,
        (obs["observation_state"] != "missing") & obs["units"].isna(),
        obs,
        "error",
        "measured_without_value",
        "observations",
        "units",
        "observed row has null units",
        "Use observation_state='missing' for unmeasured weeks; never zero-fill.",
    )

    off = t["offers"]
    _flag(
        issues,
        ~off["offered_days"].between(0, 7),
        off,
        "error",
        "invalid_days",
        "offers",
        "offered_days",
        "offered_days outside 0..7",
    )
    _flag(
        issues,
        off["available_days"].notna() & (off["available_days"] > off["offered_days"]),
        off,
        "error",
        "available_exceeds_offered",
        "offers",
        "available_days",
        "available_days > offered_days",
    )
    _flag(
        issues,
        (off["exposure_fraction"] - off["offered_days"] / 7).abs() > 1e-6,
        off,
        "error",
        "exposure_mismatch",
        "offers",
        "exposure_fraction",
        "exposure_fraction != offered_days/7",
    )
    _flag(
        issues,
        (off["offer_state"] == "not_offered") & (off["offered_days"] > 0),
        off,
        "error",
        "offer_state_days_conflict",
        "offers",
        "offer_state",
        "not_offered row with offered_days > 0",
    )

    key = ["item_id", "fpg_id", "week_start"]
    off_u = off.drop_duplicates(key)
    joined = obs[key].merge(off_u[[*key, "offer_state"]], on=key, how="left")
    _flag(
        issues,
        (joined["offer_state"] != "offered").to_numpy(),
        obs,
        "error",
        "observation_without_offer",
        "observations",
        "offer_state",
        "observation for a week that is not offered",
        "Every measured week must have an offers row with offer_state='offered'.",
    )
    censored = obs.merge(off_u[[*key, "stockout_state"]], on=key, how="left")
    _flag(
        issues,
        (
            (censored["observation_state"] == "observed_censored") & (censored["stockout_state"] != "stockout")
        ).to_numpy(),
        obs,
        "warning",
        "censored_without_stockout",
        "observations",
        "observation_state",
        "observed_censored row whose offer row is not flagged stockout",
    )

    items, locs = t["items"], t["locations"]
    _flag(
        issues,
        ~(locs["households"] > 0),
        locs,
        "error",
        "nonpositive_households",
        "locations",
        "households",
        "households must be > 0",
    )
    shares = md.features.demographic_share_columns
    if shares:
        sh = locs[shares]
        known = sh.notna().all(axis=1)
        partial = sh.notna().any(axis=1) & ~known
        _flag(
            issues,
            partial,
            locs,
            "error",
            "partial_shares",
            "locations",
            ",".join(shares),
            "some but not all demographic shares are null",
            "Provide all shares or leave all null (unknown).",
        )
        _flag(
            issues,
            known & ((sh < 0) | (sh > 1)).any(axis=1),
            locs,
            "error",
            "share_range",
            "locations",
            ",".join(shares),
            "demographic share outside [0,1]",
        )
        _flag(
            issues,
            known & ((sh.sum(axis=1) - 1).abs() > 1e-6),
            locs,
            "error",
            "share_sum",
            "locations",
            ",".join(shares),
            "demographic shares do not sum to 1",
            "Shares must partition households.",
        )
        n_unknown = int((~known).sum())
        if n_unknown:
            issues.append(
                Issue(
                    "info",
                    "unknown_shares",
                    f"{n_unknown} location versions have unknown shares; "
                    "similarity-based recipes will fall back explicitly",
                    "locations",
                    None,
                    _row_ids(locs[~known], ["fpg_id", "effective_from"]),
                    n_unknown,
                )
            )

    for name, df in (("observations", obs), ("offers", off)):
        _flag(
            issues,
            ~df["item_id"].isin(items["item_id"]),
            df,
            "error",
            "unknown_item",
            name,
            "item_id",
            "item_id not present in items",
        )
        _flag(
            issues,
            ~df["fpg_id"].isin(locs["fpg_id"]),
            df,
            "error",
            "unknown_location",
            name,
            "fpg_id",
            "fpg_id not present in locations",
        )

    issues += _validate_launches(ds)
    issues += _validate_features(ds)
    return issues


def _validate_launches(ds: Dataset) -> list[Issue]:
    issues: list[Issue] = []
    md = ds.metadata
    la = ds["launches"]
    obs, off, locs = ds["observations"], ds["offers"], ds["locations"]
    wd = WEEKDAYS[md.time.week_start]
    floor = la["first_offer_at"] - pd.to_timedelta((la["first_offer_at"].dt.weekday - wd) % 7, unit="D")
    _flag(
        issues,
        floor != la["first_offer_week"],
        la,
        "error",
        "first_offer_week",
        "launches",
        "first_offer_week",
        "first_offer_week is not the week containing first_offer_at",
    )
    _flag(
        issues,
        la["origin"] != la["first_offer_week"],
        la,
        "error",
        "origin_rule",
        "launches",
        "origin",
        "origin must equal first_offer_week (cold origin is not advanced past interim sales)",
    )
    pair_map = la.groupby("pair_id")[["item_id", "fpg_id"]].nunique()
    bad_pairs = pair_map[(pair_map > 1).any(axis=1)].index
    _flag(
        issues,
        la["pair_id"].isin(bad_pairs),
        la,
        "error",
        "pair_id_inconsistent",
        "launches",
        "pair_id",
        "pair_id maps to multiple item/location combinations",
    )
    _flag(
        issues,
        la.duplicated(["item_id", "fpg_id"], keep=False),
        la,
        "error",
        "duplicate_launch",
        "launches",
        "pair_id",
        "the same item-location pair has more than one launch event",
        "A pair can only have one zero-history launch; later re-launches are not C0.",
    )
    _flag(
        issues,
        ~la["item_id"].isin(ds["items"]["item_id"]),
        la,
        "error",
        "unknown_item",
        "launches",
        "item_id",
        "launch item not in items",
    )
    _flag(
        issues,
        ~la["fpg_id"].isin(locs["fpg_id"]),
        la,
        "error",
        "unknown_location",
        "launches",
        "fpg_id",
        "launch location not in locations",
    )

    first_obs = obs.groupby(["item_id", "fpg_id"])["week_start"].min().rename("first_obs_week")
    first_off = off[off["offer_state"] == "offered"].groupby(["item_id", "fpg_id"])["week_start"].min()
    m = la.join(first_obs, on=["item_id", "fpg_id"]).join(first_off.rename("first_offer_row"), on=["item_id", "fpg_id"])
    _flag(
        issues,
        m["first_obs_week"].notna() & (m["first_obs_week"] < m["origin"]),
        la,
        "error",
        "c0_violation",
        "launches",
        "origin",
        "own-pair observations exist before the cold origin (not zero-history)",
        "Imported observed-zero history is still history; such pairs cannot be C0 launches.",
    )
    _flag(
        issues,
        m["first_offer_row"].notna() & (m["first_offer_row"] < m["origin"]),
        la,
        "error",
        "offered_before_launch",
        "launches",
        "first_offer_at",
        "pair was offered before its declared first offer",
    )

    fpg_first = obs.groupby("fpg_id")["week_start"].min()
    n_mask = la["scenario"] == "PAIR0-N"
    fpg_first_l = la["fpg_id"].map(fpg_first)
    _flag(
        issues,
        n_mask & fpg_first_l.notna() & (fpg_first_l < la["origin"]),
        la,
        "error",
        "new_fpg_has_history",
        "launches",
        "fpg_id",
        "PAIR0-N location has transactions before origin (not an entirely new FPG)",
    )
    e_mask = la["scenario"] == "PAIR0-E"
    _flag(
        issues,
        e_mask & (fpg_first_l.isna() | (fpg_first_l >= la["origin"])),
        la,
        "error",
        "established_fpg_without_history",
        "launches",
        "fpg_id",
        "PAIR0-E location has no other-item history before origin",
        "Relabel as PAIR0-N or fix the location.",
    )
    item_first = obs.groupby("item_id")["week_end"].min()
    _flag(
        issues,
        ~(la["item_id"].map(item_first) <= la["origin"]),
        la,
        "error",
        "item_not_existing",
        "launches",
        "item_id",
        "item has no national history before origin; this profile covers existing items",
    )
    return issues


def _validate_features(ds: Dataset) -> list[Issue]:
    issues: list[Issue] = []
    md = ds.metadata
    of = ds.tables.get("origin_features")
    prop = md.features.propensity
    if prop is not None:
        if of is None:
            issues.append(
                Issue(
                    "warning",
                    "propensity_table_absent",
                    "metadata declares propensity P but no origin_features table is mapped; "
                    "M1/M2 will be rejected as missing_features",
                    "origin_features",
                )
            )
        else:
            p = of[of["feature_name"] == prop.feature_name]
            if p.empty:
                issues.append(
                    Issue(
                        "warning",
                        "propensity_absent",
                        f"no '{prop.feature_name}' rows",
                        "origin_features",
                        "feature_name",
                    )
                )
            _flag(
                issues,
                p["unit"] != prop.unit,
                p,
                "error",
                "propensity_unit",
                "origin_features",
                "unit",
                f"P unit must be '{prop.unit}' (expected weekly units per household, not a probability)",
            )
            _flag(
                issues,
                p["value"].notna() & (p["value"] < 0),
                p,
                "error",
                "negative_propensity",
                "origin_features",
                "value",
                "negative propensity",
            )
            if not prop.season_neutral:
                issues.append(
                    Issue(
                        "error",
                        "propensity_not_season_neutral",
                        "M1/M2 require season-neutral P; declare a different recipe instead",
                        "origin_features",
                    )
                )
    if of is not None:
        _flag(
            issues,
            of["known_at"] > of["origin"],
            of,
            "warning",
            "feature_known_after_origin",
            "origin_features",
            "known_at",
            "feature snapshot not known at its origin; it will be invisible to models",
        )
    fc = ds.tables.get("future_covariates")
    if fc is not None:
        _flag(
            issues,
            fc["known_at"] > fc["origin"],
            fc,
            "warning",
            "covariate_known_after_origin",
            "future_covariates",
            "known_at",
            "future covariate not known at origin; it will be ignored",
        )
        _flag(
            issues,
            fc["forecast_week"] < fc["origin"],
            fc,
            "error",
            "covariate_before_origin",
            "future_covariates",
            "forecast_week",
            "future covariate refers to a week before origin",
        )
    return issues
