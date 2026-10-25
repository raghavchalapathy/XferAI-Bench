"""Versioned method registry. Registration is not implementation: states are tracked separately.

* implementation_state: implemented | experimental | unimplemented | config_required
* execution_state:      success | not_run | not_installed | failed   (set by a run)
* eligibility_state:    compatible | unsupported_history | missing_features | license_blocked | service_required
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import entry_points

from xferbench.contracts.methods import (
    CapabilitySpec,
    EligibilityState,
    ImplementationState,
    RegistryEntryReport,
    Rights,
)
from xferbench.data.io import Dataset
from xferbench.models.base import Method

REGISTRY_VERSION = "2026.10.16-e"


@dataclass(frozen=True)
class RegistryEntry:
    spec: CapabilitySpec
    implementation_state: ImplementationState
    factory: Callable[[], Method] | None = None
    static_eligibility: EligibilityState | None = None
    reason: str = ""
    remedy: str = ""
    milestone: str = "A"
    profiles: tuple[str, ...] = field(default=("all",))
    research_only: bool = False  # non-commercial / research-only rights: opt-in only, never a default


def _rights(
    code_license: str,
    code_source: str,
    *,
    revision: str | None = None,
    weights: str = "none",
    weights_revision: str | None = None,
    commercial: str = "permitted",
    notes: str = "",
    service: str | None = None,
) -> Rights:
    return Rights(
        code_license=code_license,
        code_source=code_source,
        code_revision=revision,
        weights=weights,
        weights_revision=weights_revision,
        commercial_use=commercial,
        notes=notes,  # type: ignore[arg-type]
        service_terms=service,
    )


def _planned(
    method_id: str,
    family: str,
    name: str,
    board: str,
    identity: str,
    extra: str | None,
    modules: list[str],
    rights: Rights,
    milestone: str,
    description: str,
    *,
    eligibility: EligibilityState | None = None,
    reason: str | None = None,
    remedy: str | None = None,
    history: str = "",
    statistic: str = "mean",
    state: ImplementationState = "unimplemented",
    research_only: bool = False,
) -> RegistryEntry:
    spec = CapabilitySpec(
        method_id=method_id,
        version="0.0.0",
        family=family,
        display_name=name,
        task_profiles=["retail_pair_zero_v1"],
        board=board,
        identity=identity,  # type: ignore[arg-type]
        optional_extra=extra,
        python_modules=modules,
        rights=rights,
        description=description,
        history_rules=history,
        point_statistic=statistic,  # type: ignore[arg-type]
    )
    return RegistryEntry(
        spec=spec,
        implementation_state=state,
        static_eligibility=eligibility,
        milestone=milestone,
        research_only=research_only,
        reason=reason or f"adapter not implemented yet (planned for Milestone {milestone})",
        remedy=remedy or f"implement and test the adapter in Milestone {milestone}; no score is reported until then",
    )


def _builtin() -> list[RegistryEntry]:
    from xferbench.models.foundation_models.donor_prior import FMChronos2, FMChronosBolt, FMTimesFM25, M6DeepARCount
    from xferbench.models.machine_learning.lightgbm_pairs import M4LightGBM
    from xferbench.models.stats.rates import (
        B0NationalRate,
        B1NationalSeasonal,
        B2AnalogRate,
        B3AnalogRate,
        M1FlatRule,
        M2SeasonalRule,
    )

    core = ("core", "all")
    entries = [
        RegistryEntry(cls.spec, "implemented", cls, profiles=core)
        for cls in (B0NationalRate, B1NationalSeasonal, B2AnalogRate, B3AnalogRate, M1FlatRule, M2SeasonalRule)
    ]
    entries.append(
        RegistryEntry(
            M4LightGBM.spec,
            "implemented",
            M4LightGBM,
            milestone="B",
            profiles=core,
            reason="",
            remedy="",
        )
    )
    for cls, prof in (
        (FMChronos2, ("foundation", "all")),
        (FMChronosBolt, ("foundation", "all")),
        (FMTimesFM25, ("foundation", "all")),
        (M6DeepARCount, ("neural", "all")),
    ):
        entries.append(
            RegistryEntry(
                cls.spec,
                "experimental",
                cls,
                milestone="B" if cls is M6DeepARCount else "C",
                profiles=prof,
                reason="licence-pinned, not Reviewer-approved for PAIR0; real backend documented-only",
                remedy=f"install the '{cls.spec.optional_extra}' extra and cache the pinned weights to run it",
            )
        )
    own = _rights("Apache-2.0", "xferbench (this package)")
    lgbm = _rights(
        "MIT",
        "https://github.com/lightgbm-org/LightGBM",
        revision="5831ee577776949d26d21efa581ec904bda80483 (observed pin, untested)",
    )
    nf = _rights(
        "Apache-2.0",
        "https://github.com/Nixtla/neuralforecast",
        revision="6c11accfbcfdd62a40ef69a7c81e3d9c7f272682 (observed pin, untested)",
    )
    sf = _rights("Apache-2.0", "https://github.com/Nixtla/statsforecast")
    ptf = _rights(
        "MIT",
        "https://github.com/sktime/pytorch-forecasting",
        revision="24a4d5cfe91f2badeada4eb70be758ffc63d29bb (observed pin, untested)",
    )
    warm = (
        "Native recipe requires own-series history; cannot enter the strict C0 board. A separately named "
        "donor-forecast + allocation cold composite may be registered in Milestone C."
    )
    entries += [
        _planned(
            "M3",
            "business_rule",
            "User ramp/blend/calibration rule",
            "cold_c0",
            "native",
            None,
            [],
            own,
            "C",
            "Original ramp/blend/calibration rule is unspecified.",
            state="config_required",
            reason="M3 formula unspecified: no substitute is invented",
            remedy="supply a recipe file matching xferbench.models.custom.M3RecipeSpec with its documented "
            "source; the executing adapter is Milestone C",
        ),
        _planned(
            "M4.xgboost",
            "boosting",
            "Global XGBoost (count objective)",
            "cold_c0",
            "native",
            "boosting",
            ["xgboost"],
            _rights("Apache-2.0", "https://github.com/dmlc/xgboost"),
            "B",
            "Pooled feature model with an explicitly configured count objective.",
        ),
        _planned(
            "M4.catboost",
            "boosting",
            "Global CatBoost (count objective)",
            "cold_c0",
            "native",
            "boosting",
            ["catboost"],
            _rights("Apache-2.0", "https://github.com/catboost/catboost"),
            "B",
            "Pooled feature model with an explicitly configured count objective.",
        ),
        _planned(
            "M5.hurdle",
            "boosting",
            "Hurdle: P(sale>0) x E[units|sale>0]",
            "cold_c0",
            "composite",
            "boosting",
            ["lightgbm"],
            lgbm,
            "B",
            "Explicit two-model construction with calibration and fallbacks.",
        ),
        _planned(
            "M7.two_tower_count",
            "neural",
            "Two-tower item/location feature encoder + count head",
            "cold_c0",
            "native",
            "neural",
            ["torch"],
            _rights("BSD-3-Clause (PyTorch)", "https://github.com/pytorch/pytorch"),
            "B",
            "Experimental internal recipe; not a reproduced industry paper.",
        ),
        _planned(
            "M8.prior_allocation",
            "composite",
            "Donor/national prior + explicit allocation",
            "cold_composite",
            "composite",
            None,
            [],
            own,
            "C",
            "Reusable prior forecaster + feature/exposure allocator.",
        ),
        _planned(
            "M9.graph_transfer",
            "graph",
            "Bounded feature/graph transfer (origin-valid edges)",
            "cold_c0",
            "native",
            None,
            [],
            own,
            "B",
            "No target-FPG transaction edges for PAIR0-N; not a GEANN reproduction.",
        ),
        _planned(
            "E1.convex_blend",
            "ensemble",
            "Validation-fitted nonnegative convex blend",
            "cold_c0",
            "composite",
            None,
            [],
            own,
            "C",
            "Weights fitted on validation only, equal E/N importance, frozen before test.",
        ),
        _planned(
            "REF.tft",
            "warm_reference",
            "Temporal Fusion Transformer",
            "warm_reference",
            "native",
            "neural",
            ["pytorch_forecasting"],
            ptf,
            "C",
            "Warm/donor reference.",
            eligibility="unsupported_history",
            reason=warm,
            history="requires own-series history",
        ),
        _planned(
            "REF.nbeats",
            "warm_reference",
            "N-BEATS (no covariates)",
            "warm_reference",
            "native",
            "neural",
            ["neuralforecast"],
            nf,
            "C",
            "Plain N-BEATS has no covariates.",
            eligibility="unsupported_history",
            reason=warm,
            history="requires own-series history",
        ),
        _planned(
            "REF.nbeatsx",
            "warm_reference",
            "N-BEATSx (exogenous)",
            "warm_reference",
            "native",
            "neural",
            ["neuralforecast"],
            nf,
            "C",
            "Distinct from N-BEATS.",
            eligibility="unsupported_history",
            reason=warm,
            history="requires own-series history",
        ),
        _planned(
            "REF.nhits",
            "warm_reference",
            "N-HiTS",
            "warm_reference",
            "native",
            "neural",
            ["neuralforecast"],
            nf,
            "C",
            "Long-horizon reference.",
            eligibility="unsupported_history",
            reason=warm,
            history="requires own-series history",
        ),
        _planned(
            "REF.croston_sba",
            "intermittent",
            "Croston-SBA",
            "warm_reference",
            "native",
            "intermittent",
            ["statsforecast"],
            sf,
            "C",
            "Intermittent-demand reference.",
            eligibility="unsupported_history",
            reason=warm,
            history="requires own-series history",
        ),
        _planned(
            "REF.tsb",
            "intermittent",
            "TSB",
            "warm_reference",
            "native",
            "intermittent",
            ["statsforecast"],
            sf,
            "C",
            "Intermittent-demand reference.",
            eligibility="unsupported_history",
            reason=warm,
            history="requires own-series history",
        ),
        _planned(
            "FM.timesfm3",
            "foundation",
            "TimesFM 3",
            "donor_only",
            "composite",
            "foundation",
            ["timesfm"],
            _rights(
                "Apache-2.0",
                "https://github.com/google-research/timesfm",
                weights="google/timesfm-3.0-pytorch (non-commercial, non-production license)",
                weights_revision="43046b85ec22d584a13f8098c2ed39c889e129c2",
                commercial="restricted",
            ),
            "C",
            "Research/reference only under reviewed grant.",
            eligibility="license_blocked",
            statistic="quantile",
            reason="downloaded weights carry a non-commercial, non-production license",
            remedy="obtain and record an exact commercial grant, or run in a documented research context",
            research_only=True,
        ),
        _planned(
            "FM.moirai2",
            "foundation",
            "Moirai 2.0 R-small",
            "donor_only",
            "composite",
            "foundation",
            ["uni2ts"],
            _rights(
                "Apache-2.0",
                "https://github.com/SalesforceAIResearch/uni2ts",
                weights="Salesforce/moirai-2.0-R-small (CC-BY-NC-4.0, research only)",
                weights_revision="30f43ff08c8494f4943ae1521e9d4e94a0fbb389",
                commercial="restricted",
            ),
            "C",
            "Research reference.",
            eligibility="license_blocked",
            statistic="quantile",
            reason="weights are CC-BY-NC-4.0 / research only; open code does not grant weight rights",
            remedy="verify a permitted grant for the exact checkpoint before any run",
            research_only=True,
        ),
        _planned(
            "FM.tabpfn_ts",
            "foundation",
            "TabPFN-TS",
            "donor_only",
            "composite",
            "foundation",
            ["tabpfn_time_series"],
            _rights(
                "Apache-2.0 (wrapper)",
                "https://github.com/PriorLabs/tabpfn-time-series",
                weights="Prior-Labs/tabpfn_2_5 (TABPFN-2.5 License v1.1, non-commercial/non-production; licence sha256 "
                "ac1d23429431a622b91c73db741868e69a0140d401ebb20b9e869a835e036e28)",
                weights_revision="6c45f3a6d0d07c6c5f62572e04a0c2929de91b8b",
                notes="TabPFN 3.5 licence unread: no 3.5 weights are pulled until a licence read is reviewed",
                commercial="restricted",
            ),
            "C",
            "Wrapper drops static/past-only covariates.",
            eligibility="license_blocked",
            statistic="quantile",
            reason="TabPFN-2.5 weights are non-commercial/non-production (licence v1.1 s1c, s2b, s2d); TabPFN 3.5 licence unread",
            remedy="pin a checkpoint with a verified grant and review its obligations",
            research_only=True,
        ),
        _planned(
            "EXT.pop",
            "external",
            "POP (research-only external adapter)",
            "donor_only",
            "composite",
            None,
            [],
            _rights(
                "CC-BY-NC-SA-4.0",
                "https://github.com/HumaticsLAB/POP",
                revision="d0a6896",
                commercial="restricted",
                notes="internal_research_only; ShareAlike: derivatives must stay CC-BY-NC-SA-4.0, outside the Apache-2.0 core",
            ),
            "C",
            "Optional external adapter for internal literature benchmarking only.",
            eligibility="license_blocked",
            reason="code is CC-BY-NC-SA-4.0 (non-commercial, ShareAlike); internal research only",
            remedy="opt in with --allow-research-only; outputs are labeled internal research only",
            research_only=True,
        ),
    ]
    return entries


_EXTRA: list[RegistryEntry] = []


def register_method(entry: RegistryEntry) -> None:
    """Register an extension method (used by tests and trusted plugins)."""
    _EXTRA[:] = [e for e in _EXTRA if e.spec.method_id != entry.spec.method_id]
    _EXTRA.append(entry)


def unregister_method(method_id: str) -> None:
    _EXTRA[:] = [e for e in _EXTRA if e.spec.method_id != method_id]


def _entry_point_entries() -> list[RegistryEntry]:
    trusted = {x.strip() for x in os.environ.get("XFERBENCH_TRUSTED_PLUGINS", "").split(",") if x.strip()}
    out: list[RegistryEntry] = []
    if not trusted:
        return out
    for ep in entry_points(group="xferbench.methods"):
        if ep.name in trusted:
            obj = ep.load()
            out.append(obj() if callable(obj) and not isinstance(obj, RegistryEntry) else obj)
    return out


def all_entries() -> list[RegistryEntry]:
    entries = _builtin() + _entry_point_entries()
    ids = {e.spec.method_id for e in entries}
    entries += [e for e in _EXTRA if e.spec.method_id not in ids]
    return entries


# Backward-compatible method-id aliases (old id -> current id).
METHOD_ALIASES: dict[str, str] = {}  # B2.raw_units was retired (not aliased: B2 now means a different recipe)


def get_entry(method_id: str) -> RegistryEntry:
    method_id = METHOD_ALIASES.get(method_id, method_id)
    for e in all_entries():
        if e.spec.method_id == method_id:
            return e
    raise KeyError(method_id)


def research_only_ids() -> set[str]:
    return {e.spec.method_id for e in all_entries() if e.research_only}


def entries_for_profile(profile: str, allow_research_only: bool = False) -> list[RegistryEntry]:
    """Default method sets never include research-only entries unless explicitly allowed."""
    pool = [e for e in all_entries() if allow_research_only or not e.research_only]
    if profile == "all":
        return pool
    out = [e for e in pool if profile in e.profiles]
    if not out:
        known = sorted({p for e in all_entries() for p in e.profiles})
        raise KeyError(f"unknown method profile '{profile}'; known profiles: {known}")
    return out


# How to install an optional extra, as printed in "not run" lines, leaderboards and reports. The setup scripts
# install the lightgbm extra by default; --no-lightgbm opts out, and --with-lightgbm (or the default) puts it back.
INSTALL_HINTS = {
    "lightgbm": "re-run `bash xferAI_setup.sh --with-lightgbm` (Windows: `xferAI_setup.ps1 -WithLightgbm`), "
    "or `uv sync --locked --extra dev --extra lightgbm`",
}


def install_hint(extra: str | None) -> str:
    if extra and extra in INSTALL_HINTS:
        return INSTALL_HINTS[extra]
    return f"install the '{extra}' extra into this environment"


def modules_installed(modules: list[str]) -> list[str]:
    return [m for m in modules if importlib.util.find_spec(m) is None]


def assess(entry: RegistryEntry, dataset: Dataset | None = None) -> RegistryEntryReport:
    """Preflight report for one entry (before any execution)."""
    spec = entry.spec
    eligibility: EligibilityState | None = entry.static_eligibility
    reason, remedy = entry.reason, entry.remedy
    missing_modules = modules_installed(spec.python_modules)
    runnable = entry.implementation_state in ("implemented", "experimental")
    execution = "not_installed" if missing_modules and runnable else "not_run"
    if runnable and dataset is not None and eligibility is None:
        missing_tables = [t for t in spec.required_tables if not dataset.has(t)]
        missing_feats = []
        if "propensity_rate" in spec.required_features:
            prop = dataset.metadata.features.propensity
            of = dataset.tables.get("origin_features")
            if prop is None or of is None or (of["feature_name"] == prop.feature_name).sum() == 0:
                missing_feats.append("propensity_rate")
        if missing_tables or missing_feats:
            eligibility = "missing_features"
            reason = f"missing tables {missing_tables} / features {missing_feats}"
            remedy = "map the required table/feature in metadata, or leave this recipe disabled"
        else:
            eligibility = "compatible"
            reason, remedy = "", ""
    if missing_modules and runnable:
        reason = f"optional modules not installed: {missing_modules}"
        remedy = install_hint(spec.optional_extra)
    return RegistryEntryReport(
        method_id=spec.method_id,
        version=spec.version,
        family=spec.family,
        display_name=spec.display_name,
        board=spec.board,
        identity=spec.identity,
        implementation_state=entry.implementation_state,
        execution_state=execution,
        eligibility_state=eligibility,
        optional_extra=spec.optional_extra,  # type: ignore[arg-type]
        point_statistic=spec.point_statistic,
        rights=spec.rights,
        history_rules=spec.history_rules,
        used_features=spec.used_features,
        reason=reason,
        remedy=remedy,
    )
