# Data story: synthetic retail cold pairs (tiny, seed 42)

> **Synthetic data demonstrates software behavior, not real-world model superiority.**
> Nothing in this dataset is a measurement of any real company, product or market.

## The question being benchmarked

A retailer sells existing items in many **FPGs** (Forecast Pixel Groups: company demand areas, not
automatically H3 cells). When an item is offered for the first time at a location, there is **zero**
sales history for that item-location *pair*. We forecast its weekly unit sales for the next
52 weeks, starting at the week of first offer (the *cold origin*).

Two scenarios carry equal weight and are always reported separately:

* **PAIR0-E** - the location is established: other items already sell there.
* **PAIR0-N** - the location is entirely new: it opens at the origin, so *no* transactions exist there.

## One item

Item `000103` is in category **winter_care_a** (seasonal), product type
`winter_care`. Before its validation launch it had already sold at 6 other FPGs;
that same-item history elsewhere is what baselines may use. Item IDs look numeric but are strings:
`000103` keeps its leading zeros in CSV and Parquet.

## One established FPG

FPG `F005` (region south) has 2231 households (H) and demographic
shares: families 0.12, young_adults 0.15, seniors 0.51, students 0.22. Item `000103` launched there on 2023-03-20 (launch `L-VAL-0023`).
The company propensity feature for that pair at origin is P = 0.000047 expected weekly units per
household, so the business rule M1 = H x P = 0.10 units/week.

## One entirely new FPG

FPG `N-VAL-01` opened on 2023-03-20 with 12822 households. Its
attributes (households, shares, region) were published 28 days before opening, so they are legitimately
known at origin. It has no sales history at all; held-out new FPGs are also excluded from every donor
and national aggregate during their stage.

## Tables, units and what each state means

| State | Meaning | How it appears |
|---|---|---|
| never offered | the item was not sold at that FPG that week | **no row** in `offers` or `observations` |
| observed zero | offered and measured, sold nothing | `units = 0`, `observation_state = observed` |
| stockout-censored | offered, stock ran out, sales are a lower bound on demand | `observed_censored`, `offers.stockout_state = stockout` |
| missing | offered but not measured | `units` empty/null, `observation_state = missing` |

Counts in this dataset: {'observed': 33333, 'observed_censored': 1013, 'missing': 379}. Missing values are never zero-filled.

Units: `units` = item units per week; `households` = households; P = units per household per week
(season-neutral, *not* a probability); seasonal index S is dimensionless with annual mean one.
Each week is the half-open interval [Monday, next Monday). A week's sales become known
7 days after it ends (`known_at`); about 2% of
weeks report two weeks later still. A model at origin *o* may only use weeks that ended and were known by *o*.

## Planted processes (hidden from models)

* Each item has a hidden per-household rate, an activity probability (sparse weeks), a modest trend and a
  category seasonal curve with mean one (garden_a, garden_b, gift_sets_a, household_a, household_b, pantry_a, pantry_b, winter_care_a, winter_care_b).
* Each pair has a hidden affinity driven by demographic shares x item/category loadings plus noise;
  about 6% of launched pairs are near-dead (often all-zero for 52 weeks).
* Demand is gamma-Poisson (negative binomial, shape 1.2) with sparse national bursts.
  Observed sales are binomially thinned on stockout weeks; latent demand is kept separately.
* A single global scale was calibrated so the *expected* zero fraction of training-period offered
  weeks is 0.800 (target 0.8); the realized
  training-period zero fraction is 0.805. Validation and test
  outcomes were not used and nothing was rewritten.
* P, item rank and item-cluster affinity are **noisy estimates computed from origin-valid observed data**
  (ridge regression of donor rates on shares, plus multiplicative noise), not the hidden rates.

Hidden truth lives in `_synthetic_truth/` (latent demand, true rates, affinities, seasonal curves, bursts).
Metadata never points there, and the loader refuses such paths.

## Cohorts

Launch counts per stage: {'train': {'launches': 22, 'ranked': 22, 'PAIR0-E': 10, 'PAIR0-N': 12, 'edge_fixtures': 0, 'incomplete_labels': 0}, 'validation': {'launches': 16, 'ranked': 16, 'PAIR0-E': 8, 'PAIR0-N': 8, 'edge_fixtures': 0, 'incomplete_labels': 0}, 'test': {'launches': 22, 'ranked': 16, 'PAIR0-E': 8, 'PAIR0-N': 8, 'edge_fixtures': 6, 'incomplete_labels': 0}}. Training origins fall in 2021, validation in 2023, test in Q1 2025;
every 52-week label used for fitting is available before each later origin (checked in `splits.json`).
Edge fixtures (partial launch week, heavy stockouts, missing target weeks, missing P, unseen category,
unknown location attributes) form a separate unranked board so they never distort the main leaderboard.

## Replacing this with your data

Keep the same logical tables, point `metadata.json` at your files and map your column names. See
`docs/REAL_DATA.md`. Your accuracy benchmark needs historical launches whose 52 weeks of actuals are complete.
