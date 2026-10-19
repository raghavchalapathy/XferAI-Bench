# Metadata and column mapping

`metadata.json` tells Xfer Benchmark where your tables are, what each column means and which rules apply.
It is **declarative and strict**: unknown keys are rejected, and no code, formula or expression in it is ever
executed. The JSON schema is in [`schemas/metadata.schema.json`](../schemas/metadata.schema.json)
(regenerate with `xferbench schemas --out schemas`). Every canonical column is described in
[`schemas/FIELD_DICTIONARY.md`](../schemas/FIELD_DICTIONARY.md).

## Getting a starting file

```bash
xferbench init --path ./my-bench          # metadata.json + selection-policy.json templates
xferbench metadata wizard --data ./my-bench/data --out ./my-bench/metadata.json
```

The wizard lists your CSV/Parquet files, shows each file's columns with sample values, asks you to pick the
source column for every canonical column (suggesting exact name matches), asks which columns are demographic
shares, and asks you to **confirm** that the propensity feature `P` is expected weekly units per household
(not a probability) before enabling the M1/M2 business rules. It then validates the data and reports whether
each stage has complete 52-week labels.

## Structure

| Section | What it declares |
|---|---|
| `dataset` | `id`, `version`, `description`, `synthetic`, optional `expected_hash` (load fails if data changed) |
| `time` | timezone, `week_start` (default Monday), half-open `[start,end)` weeks, `reporting_delay_days` (default 7), `horizon_weeks` (52), origin rule `first_offer_week` |
| `target` | `units` column, gross weekly item units, nonnegative |
| `tables` | per logical table: `path` (relative to the metadata file), `format` (`csv` or `parquet`), `columns` mapping canonical -> source name, `extra_columns` |
| `features` | households definition, propensity spec (or `null` to disable M1/M2), seasonality estimator settings, `hierarchy` (see below), `demographic_share_columns` |
| `donor_policy` | consistent-exposure window (52 weeks) and minimum measured fraction (0.9) |
| `cohorts` | origin windows for `train`, `validation`, `test`; scenario selection weights; which launches are ranked; which stages may be used to fit for the test |
| `metrics`, `resource_limits`, `rights`, `privacy` | metric definitions and zero-denominator rule; optional budgets; data owner and permitted use; network is always off |

### `features.hierarchy` (retail)

When an item has no history at a Forecast Pixel Group (FPG), rates and seasonal shapes are borrowed from a broader level.
One shared component applies this to every method, using only data available at the forecast origin, and
records the level used (`rate_level`, `season_level` in forecasts; `hierarchy_summary` in the run manifest).

| Key | Default | Meaning |
|---|---|---|
| `rate_levels` | `["item", "subcategory", "product_type"]` | fallback order for the per-household rate |
| `season_levels` | `["category", "product_type"]` | fallback order for the mean-one seasonal profile |
| `min_rate_support_fpgs` | `3` | a rate level is used only if at least this many FPGs support it |
| `min_season_support_items` | `2` | a seasonal level is used only if at least this many items support it |

`subcategory` is an optional `items` column; without it the rate falls back from item to product type.

## Tables

Required: `observations`, `offers`, `items`, `locations`, `launches`. Optional: `origin_features`
(origin-dated snapshots such as the propensity `P`), `donors`, `future_covariates`.

| Table | Key | Meaning |
|---|---|---|
| `observations` | item, fpg, week_start | weekly units with `observation_state` = `observed`, `observed_censored` (stockout, a lower bound) or `missing` (unmeasured, units null). Zero is a real observation. `known_at` is when the value became available. |
| `offers` | item, fpg, week_start | whether and how many days the item was offered, available days, `exposure_fraction = offered_days/7`, `stockout_state` |
| `items` | item, effective_from | category, product type, seasonality class, versioned with `effective_from`/`known_at` |
| `locations` | fpg, effective_from | region, `fpg_open_at`, non-overlapping `households`, optional demographic share columns (sum to 1, or all null = unknown) |
| `launches` | launch_id | the cold-pair launch events to score: item, fpg, `first_offer_at`, `first_offer_week`, `origin` (= first offer week), `scenario` (PAIR0-E / PAIR0-N), `qualification`, `launch_type` |

## Mapping differently named columns

```json
"tables": {
  "observations": {
    "path": "raw/weekly_sales.csv",
    "format": "csv",
    "columns": {"item_id": "sku", "fpg_id": "site_group", "week_start": "wk", "units": "qty"}
  }
}
```

Only renamed columns need an entry. Identifiers are always read as strings (leading zeros preserved; a numeric
ID column in Parquet is converted with a warning). Dates must be ISO `YYYY-MM-DD`. CSV and Parquet versions of
the same data load to the same canonical tables and the same dataset hash.

## Propensity `P`

`features.propensity` must describe **expected weekly units per household**, season-neutral, known at the
origin. If your `P` is a purchase probability or index, do not declare it; set `"propensity": null` and M1/M2
are reported as `missing_features` rather than run on the wrong unit.
