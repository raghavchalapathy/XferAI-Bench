# Evaluation: splits, leakage rules, metrics and selection

## Calendar

Weeks are half-open `[week_start, week_start + 7 days)` starting on the declared weekday (Monday by
default), in the declared local timezone. With a 7-day reporting delay, a week is usable at origin `o` only if
it ended on or before `o` **and** its `known_at` is on or before `o`; the latest usable week therefore starts
at `o - 14 days`. The forecast for horizon week `h` (1..52) covers `[o + 7(h-1), o + 7h)`.

## Splits

`xferbench split` assigns natural launches to the `train`, `validation` and `test` origin windows declared in
metadata and writes `splits.json` with a content hash. For every launch it computes the target end and the
date the full 52-week label becomes available, and records these checks (the run refuses a split with any
failed check, and refuses a split whose hash does not verify):

| Check | Meaning |
|---|---|
| `chronological_stage_windows` | train ends before validation starts, validation before test |
| `c0_zero_own_pair_history` | no observation of the target pair before its origin |
| `new_fpg_zero_transactions` | PAIR0-N FPGs have no transactions at all before origin |
| `new_fpg_cohorts_disjoint` | a new FPG belongs to one stage only |
| `fit_labels_available_before_origin` | every label used to fit for a stage was reported before that stage's first origin |
| `scored_labels_complete` | every scored launch has its 52 weeks reported by the scoring cutoff |
| `selection_frozen_before_test` | the validation scoring cutoff precedes the first test origin |

For the validation stage, methods may fit on train launches; for the test stage, on train and validation
launches whose labels are available before the first test origin.

## Leakage rules

An origin context contains only: observations and offers that ended and were known by the origin; item and
location attribute versions effective and known by then; origin features and future covariates issued for
that origin and known by then. The stage's held-out pairs and **all** of its new FPGs are removed from every
context and every aggregate (national rates, seasonal profiles, analog donors), so a PAIR0-N location can
never inform its own forecast through a donor. Tests mutate future values and confirm contexts and
forecasts are unchanged.

## Eligible population

Fixed per board **before** any forecast is examined: every measured target week (`observed` or
`observed_censored`) of every request. Missing weeks are excluded for every method alike; weeks that were not
offered are not targets. The population hash is stored in the manifest.

## Metrics

- `WMAPE = sum(|F - A|) / sum(A)` over the eligible population. Lower is better.
- `Bias = sum(F) / sum(A) - 1`. Positive means over-forecast.
- If `sum(A) = 0`, both are **undefined**: JSON `null` with a reason, `N/A` in the report. No epsilon.
- Coverage is the share of eligible weeks with a valid (`success` or `fallback`) forecast. Below 100%, the
  metrics are undefined and the variant is unrankable; metrics are never computed on a convenient subset.
- The objective is `0.5 x WMAPE(PAIR0-E) + 0.5 x WMAPE(PAIR0-N)`. Both scenarios are always reported.
- Slices: horizon buckets 1-4, 5-13, 14-26, 27-52; category; region; intermittency (by realised zero share);
  availability (stockout weeks vs in stock). Intermittency and availability are outcome-defined diagnostics
  and are never used for selection.

## Validation selection

`xferbench select` applies a preregistered policy (default below, schema in
`schemas/selection-policy.schema.json`) to a **complete validation run only**:

```json
{"objective": "equal_scenario_wmape", "scenario_weights": {"PAIR0-E": 0.5, "PAIR0-N": 0.5},
 "max_abs_bias": 0.5, "min_coverage": 1.0, "max_total_seconds": null,
 "undefined_metric_rule": "ineligible", "board": "cold_c0"}
```

A variant is eligible only if, in **each** scenario, coverage meets the minimum, WMAPE is defined, and
`|Bias| <= max_abs_bias`. Per method family the eligible variant with the lowest objective is frozen; the
overall lowest is the recommendation. `selection.json` records the policy hash, validation manifest hash,
dataset and split hashes and the selection cutoff. The test run verifies these and scores only the frozen
variants.

## Interpretation limits

- Synthetic results demonstrate software behaviour, not model superiority.
- Small cohorts are noisy; sample counts are shown next to every slice.
- Paired block-bootstrap uncertainty is not computed in Milestone A.
- Ranked rows share dataset, population, split, origins, horizon, target, aggregation, metrics and
  information budget. `xferbench compare` refuses to rank runs that differ in any of these.
- The report helps choose methods for further validation; it does not certify production readiness.
