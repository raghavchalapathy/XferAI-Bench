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
| `B2` | `H x r_B2 x S(w)` | `r_B2 = (n x r_analog + kappa x r_item) / (n + kappa)`, `r_analog` = inverse-distance-weighted rate of the `k` most similar same-item donor FPGs (distance on demographic shares, log households, region). Grid `k in {3, 8}`, `kappa in {1, 4}` chosen on validation. Falls back to B1 when no comparable donor exists. |
| `B2.raw_units` | weighted mean donor units `x S(w)` | Ablation: the same analogs without household adjustment. Not a recommended recipe. |
| `M1` | `H x P` | Business rule; requires a declared `P` with unit `units_per_household_per_week`. |
| `M2` | `H x P x S(w)` | `S` applied once; no anchor-week division; demographic affinity not re-applied. |
| `M3` | - | `config_required`: the business ramp/blend/calibration rule was not specified, so **nothing is substituted**. Supply a recipe matching `xferbench.methods.custom.M3RecipeSpec`; the executing adapter is Milestone C. Requesting `--methods M3` exits with code 3. |

Each recipe uses `S` at most once, so seasonality is never double counted.

## Planned adapters

| Milestone | Methods |
|---|---|
| B | `M4.lightgbm`, `M4.xgboost`, `M4.catboost`, `M5.hurdle`, `M6.deepar_count`, `M7.two_tower_count`, `M9.graph_transfer` |
| C | `M3` executor, `M8.prior_allocation`, `E1.convex_blend`, foundation donor priors (`FM.*`), `SVC.timegpt` (opt-in only), warm-reference cold composites |

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
`SVC.timegpt` is `service_required` (paid external API, data egress). Nothing downloads weights or calls a
service by default. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
