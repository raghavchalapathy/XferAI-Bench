# Methods

The full, generated compatibility table is [METHOD_SUPPORT.md](../METHOD_SUPPORT.md)
(`xferbench list-methods --all --format markdown`). This page explains the recipes that run today and how the
registry states work.

## Registry states

Three states are kept separate and are never collapsed into a single "supported" flag:

- `implementation_state`: `implemented`, `experimental`, `unimplemented`, `config_required`.
- `execution_state` (per run): `success`, `not_run`, `not_installed`, `failed`.
- `eligibility_state`: `compatible`, `unsupported_history`, `missing_features`, `license_blocked`,
  `service_required`; for implemented recipes it is checked against your dataset during preflight.

Registration is not implementation. Unimplemented entries appear in every run's `method_support.json` and
report with a reason and remedy and never receive a score.

## Implemented recipes (Milestone A)

Notation: `H` = target FPG households at origin, `r` = season-neutral weekly units per household,
`S(w)` = mean-one seasonal index for the item's category at forecast week `w`, `P` = origin propensity
(units per household per week). All quantities come only from the origin context. All recipes report the
**mean** as their point statistic.

| ID | Forecast | Notes |
|---|---|---|
| `B0` | `H x r_item` | `r_item` = sum(units) / sum(households x measured weeks) over same-item donor pairs measured in at least 90% of the trailing 52 usable weeks. If no pair qualifies, all measured donor weeks are used and the row is a visible `fallback`. |
| `B1` | `B0 x S(w)` | `S` estimated per complete 52-week cycle from donor category history (rate per measured household, divided by that cycle's mean), averaged over up to 3 cycles, circularly smoothed (window 3) and renormalised to mean exactly one. ISO week 53 is folded into 52. Flat `S` is a visible fallback. |
| `B2` | `H x r_analog x S(w)` | Target FPG households x `r_analog`, the inverse-distance-weighted per-household rate of the item in the `k` most similar same-item donor FPGs (distance on demographic shares, log households, region). No shrinkage. Grid `k in {3, 8}` chosen on validation. Falls back to B1 when no comparable donor exists. |
| `B3` | `H x r_B3 x S(w)` | B2 shrunk toward the national rate: `r_B3 = (n x r_analog + kappa x r_item) / (n + kappa)`. Grid `k in {3, 8}`, `kappa in {1, 4}`. Shown as an extra row next to the method order, not a step. |
| `M1` | `H x P` | Business rule; requires a declared `P` with unit `units_per_household_per_week`. |
| `M2` | `H x P x S(w)` | `S` applied once; no anchor-week division; demographic affinity not re-applied. |
| `M4.lightgbm` | pooled LightGBM (Poisson) | Optional extra: `pip install -e ".[lightgbm]"` (or the wider `boosting` extra), imported lazily; if absent the method is listed as `not_installed` and every other method runs. One row per (launch, horizon week); features only from the origin context: log households, log B0 level, log M1 level (if P exists), mean-one seasonal index, horizon week, ISO week, demographic shares. No own-pair lags. Trained on fit launches; labels on or after the fit cutoff are dropped. Fixed seed, single thread, 200 rounds. |
| `M3` | - | `config_required`: the business ramp/blend/calibration rule was not specified, so **nothing is substituted**. Supply a recipe matching `xferbench.models.custom.M3RecipeSpec`; the executing adapter is Milestone C. Requesting `--methods M3` exits with code 3. |

Each recipe uses `S` at most once, so seasonality is never double counted.

## Methods in order, each adding one idea

`xferbench steps --benchmark synthetic-tiny@1.1.0 --out ./steps` (or `--local-data PATH/metadata.json`) runs the
domain plugin's method sequence and adds a report section with WMAPE and Bias for each scenario separately.
For retail the sequence is:

| Step | Method | Idea added |
|---|---|---|
| 1 | `B0` | `H x r`, flat |
| 2 | `B1` | `x S(product type, w)`: seasonality (the item's category is its national product type) |
| 3 | `B2` | `H x` the item's per-household rate in the `k` FPGs with the most similar customer mix (no shrinkage) |
| extra | `B3` | B2 shrunk toward the national rate (extra row, not a step) |
| 4 | `M1` | `H x P`, flat: location propensity instead of the national rate |
| 5 | `M2` | `H x P x S`, mean-one `S`, no anchor-week division |
| 6 | `M3` | user rule; `config_required` until a recipe is supplied (shown with its reason, never invented) |
| 7 | `M4.lightgbm` | gradient-boosted trees on origin-built features |

Comparisons (delta = candidate - reference, per scenario): M1 vs B0, B3 vs B2 (shrinkage effect), B1 vs B0, M2 vs M1, M3 vs M2 (N/A while
M3 needs a recipe), M4 vs M2 (labelled "M3 pending recipe"). Each method's variant is chosen on validation
(no Bias gate in this diagnostic) and frozen before the test stage. Every B/M method uses the target FPG's households.
The old raw similar-FPG unit mean (`B2.raw_units`) is retired: it is not registered or displayed. Domain plugins declare the sequence via the
optional `method_order` / `method_comparisons` attributes.

## Planned adapters

| Milestone | Methods |
|---|---|
| B | `M4.xgboost`, `M4.catboost`, `M5.hurdle`, `M6.deepar_count`, `M7.two_tower_count`, `M9.graph_transfer` |
| C | `M3` executor, `M8.prior_allocation`, `E1.convex_blend`, foundation donor priors (`FM.*`), warm-reference cold composites |

Native warm-history methods (`REF.tft`, `REF.nbeats`, `REF.nbeatsx`, `REF.nhits`, `REF.croston_sba`, `REF.tsb`)
are `unsupported_history` on the strict zero-history board. A donor-forecast plus allocation composite would
be registered under a separate, clearly named ID, never under the native name.

## Native versus composite

`identity = native` means the method forecasts the target pair directly. `composite` means it forecasts a
donor or aggregate series and an explicit allocation step maps that to the pair; composites are labelled
as such and, where needed, use a separate board (`donor_only`, `cold_composite`).

## Licensing

Code licences, model weights and services are separate rights. `FM.timesfm3`, `FM.moirai2` and
`FM.tabpfn_ts` are `license_blocked` because their default weights are non-commercial or research-only;
TimeGPT is deferred by the user and not listed. Nothing downloads weights or calls a service by default. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Licence-pinned donor-prior composites (not Reviewer-recommended for PAIR0)

`FM.chronos2`, `FM.chronos_bolt` (tiny/mini/small/base), `FM.timesfm25` and `M6.deepar_count` are `experimental`,
`donor_only` composites: the backend forecasts the item's donor/national weekly rate per household from the
origin context only, then the forecast is multiplied by the target FPG's households. The target pair is never
given history. Code revisions are the R3 pins (chronos-forecasting 1224fafa, timesfm e51928e2, gluonts d60556ca);
HF weight revisions come from R3 pins.v2, still pending Reviewer review. Extras: `foundation` (Chronos),
`timesfm`, `neural` (DeepAR); none are installed or tested here, so the real backend calls are documented-only.
Weights load from the local HF cache only unless `XFERBENCH_ALLOW_WEIGHT_DOWNLOAD=1`. They are not in the `core`
profile; run with `--profile foundation` / `--profile neural` or `--methods`. Moirai, TabPFN-2.5 and POP stay behind
`--allow-research-only`. `M4.xgboost` / `M4.catboost` stay unimplemented (not covered by the R3 pins).

## Shared retail hierarchy (domain-configured)

One shared component (`src/xferbench/data_preparation/feature_engineering/hierarchy.py`) serves every method that needs a donor rate or a
seasonal profile. It is configured in the domain metadata (`FeatureSpec.hierarchy`) and only reads
origin-scoped data through `OriginContext`.

- Rate: item -> subcategory -> product_type. A level is used when it has at least `min_rate_support_fpgs` (3)
  supporting FPGs; otherwise the next level is tried.
- Seasonality: category -> product_type, with at least `min_season_support_items` (2) items.
- The level used is recorded per forecast row (`rate_level`, `season_level`) and summarised in the run manifest
  (`hierarchy_summary`). M1/M2 use propensity P and record `rate_level="propensity"`; P is never silently
  replaced by a hierarchy rate. `subcategory` is an optional column in the item table.
- Leakage tests: `tests/leakage/test_hierarchy.py`; every fallback step has a test.
