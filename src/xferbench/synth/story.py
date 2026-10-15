"""Beginner-readable DATA_STORY.md generated from the actual synthetic dataset."""

from __future__ import annotations

import pandas as pd

from xferbench.contracts.splits import SplitManifest
from xferbench.data.io import Dataset
from xferbench.synth.presets import SynthConfig


def _fmt(x: float | None, digits: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def data_story(cfg: SynthConfig, ds: Dataset, split: SplitManifest, info: dict, report: dict) -> str:
    obs, items, locs = ds["observations"], ds["items"], ds["locations"]
    of = ds.tables.get("origin_features")
    val = split.stages["validation"]
    e = next((r for r in val.launches if r.ranked and r.scenario == "PAIR0-E"), None)
    n = next((r for r in val.launches if r.ranked and r.scenario == "PAIR0-N"), None)
    ex_item = e.item_id if e else items["item_id"].iloc[0]
    it = items[items["item_id"] == ex_item].iloc[-1]
    item_obs = obs[obs["item_id"] == ex_item]
    item_fpgs_before = item_obs[item_obs["week_end"] <= pd.Timestamp(e.origin)]["fpg_id"].nunique() if e else 0
    est = locs[locs["fpg_id"] == (e.fpg_id if e else locs["fpg_id"].iloc[0])].sort_values("effective_from").iloc[-1]
    new = locs[locs["fpg_id"] == (n.fpg_id if n else locs["fpg_id"].iloc[-1])].sort_values("effective_from").iloc[-1]
    p_row = None
    if of is not None and e is not None:
        m = of[(of["feature_name"] == "propensity_rate") & (of["item_id"] == e.item_id) & (of["fpg_id"] == e.fpg_id)]
        p_row = float(m["value"].iloc[0]) if len(m) else None
    states = obs["observation_state"].value_counts().to_dict()
    cal = report["calibration"]
    shares = [c for c in ds.metadata.features.demographic_share_columns]
    share_txt = ", ".join(f"{c.removeprefix('share_')} {est[c]:.2f}" for c in shares)
    counts = {s: st.counts for s, st in split.stages.items()}

    return f"""# Data story: synthetic retail cold pairs ({cfg.preset}, seed {cfg.seed})

> **Synthetic data demonstrates software behavior, not real-world model superiority.**
> Nothing in this dataset is a measurement of any real company, product or market.

## The question being benchmarked

A retailer sells existing items in many **FPGs** (Forecast Pixel Groups: company demand areas, not
automatically H3 cells). When an item is offered for the first time at a location, there is **zero**
sales history for that item-location *pair*. We forecast its weekly unit sales for the next
{ds.metadata.time.horizon_weeks} weeks, starting at the week of first offer (the *cold origin*).

Two scenarios carry equal weight and are always reported separately:

* **PAIR0-E** - the location is established: other items already sell there.
* **PAIR0-N** - the location is entirely new: it opens at the origin, so *no* transactions exist there.

## One item

Item `{ex_item}` is in category **{it["category"]}** ({it["seasonality_class"]}), product type
`{it["product_type"]}`. Before its validation launch it had already sold at {item_fpgs_before} other FPGs;
that same-item history elsewhere is what baselines may use. Item IDs look numeric but are strings:
`{ex_item}` keeps its leading zeros in CSV and Parquet.

## One established FPG

FPG `{est["fpg_id"]}` (region {est["region"]}) has {est["households"]:.0f} households (H) and demographic
shares: {share_txt}. Item `{ex_item}` launched there on {e.origin if e else "n/a"} (launch `{e.launch_id if e else "n/a"}`).
The company propensity feature for that pair at origin is P = {_fmt(p_row, 6)} expected weekly units per
household, so the business rule M1 = H x P = {_fmt(p_row * est["households"] if p_row else None, 2)} units/week.

## One entirely new FPG

FPG `{new["fpg_id"]}` opened on {n.origin if n else "n/a"} with {new["households"]:.0f} households. Its
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

Counts in this dataset: {states}. Missing values are never zero-filled.

Units: `units` = item units per week; `households` = households; P = units per household per week
(season-neutral, *not* a probability); seasonal index S is dimensionless with annual mean one.
Each week is the half-open interval [Monday, next Monday). A week's sales become known
{ds.metadata.time.reporting_delay_days} days after it ends (`known_at`); about {cfg.late_report_prob:.0%} of
weeks report two weeks later still. A model at origin *o* may only use weeks that ended and were known by *o*.

## Planted processes (hidden from models)

* Each item has a hidden per-household rate, an activity probability (sparse weeks), a modest trend and a
  category seasonal curve with mean one ({", ".join(c for c in sorted(items["category"].unique()))}).
* Each pair has a hidden affinity driven by demographic shares x item/category loadings plus noise;
  about {cfg.dead_pair_fraction:.0%} of launched pairs are near-dead (often all-zero for 52 weeks).
* Demand is gamma-Poisson (negative binomial, shape {cfg.nb_shape}) with sparse national bursts.
  Observed sales are binomially thinned on stockout weeks; latent demand is kept separately.
* A single global scale was calibrated so the *expected* zero fraction of training-period offered
  weeks is {cal["expected_zero_fraction_calibration"]:.3f} (target {cfg.target_zero_fraction}); the realized
  training-period zero fraction is {cal["realized_zero_fraction_calibration"]:.3f}. Validation and test
  outcomes were not used and nothing was rewritten.
* P, item rank and item-cluster affinity are **noisy estimates computed from origin-valid observed data**
  (ridge regression of donor rates on shares, plus multiplicative noise), not the hidden rates.

Hidden truth lives in `_synthetic_truth/` (latent demand, true rates, affinities, seasonal curves, bursts).
Metadata never points there, and the loader refuses such paths.

## Cohorts

Launch counts per stage: {counts}. Training origins fall in 2021, validation in 2023, test in Q1 2025;
every 52-week label used for fitting is available before each later origin (checked in `splits.json`).
Edge fixtures (partial launch week, heavy stockouts, missing target weeks, missing P, unseen category,
unknown location attributes) form a separate unranked board so they never distort the main leaderboard.

## Replacing this with your data

Keep the same logical tables, point `metadata.json` at your files and map your column names. See
`docs/REAL_DATA.md`. Your accuracy benchmark needs historical launches whose 52 weeks of actuals are complete.
"""
