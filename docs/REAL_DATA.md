# Replacing synthetic data with your own

The synthetic data and your data go through exactly the same code path. Replacing it requires **no model
code changes**; you supply tables and a metadata file.

## What your history must contain

1. **Completed historical launches.** Each scored launch needs 52 weeks of outcomes after its origin, and
   those outcomes must have been reported (`known_at`) before the stage's scoring cutoff. `xferbench split`
   computes availability per launch and fails a stage whose labels are incomplete.
2. **True zero own-pair history.** A launch's item-FPG pair must have no observation rows before its origin
   (an imported observed-zero row is still history). PAIR0-N FPGs must have no transactions at all before the
   origin.
3. **Exposure.** Offer rows for every measured week. Use `observation_state = missing` (units null) for weeks
   you cannot measure; never zero-fill. Mark stockouts with `stockout_state` and `observed_censored`.
4. **Origins.** `origin` equals the week containing `first_offer_at`. Partial first weeks are scored as
   observed; the origin is not moved past interim sales.
5. **Timing.** Every row has `known_at`; attribute changes are versioned (`effective_from`, `known_at`).
   Values corrected later must carry the later `known_at`.
6. **Donors.** Other items at the target FPG (PAIR0-E) and the same item at other FPGs provide the transfer
   signal. Households must be non-overlapping per FPG.

## Multi-table layout (recommended)

Export five CSV or Parquet files with the columns in [`schemas/FIELD_DICTIONARY.md`](../schemas/FIELD_DICTIONARY.md),
then run:

```bash
xferbench metadata wizard --data ./mydata --out ./mydata/metadata.json
xferbench validate --metadata ./mydata/metadata.json
xferbench split --metadata ./mydata/metadata.json --out ./mydata/splits.json
```

Start from `examples/retail_synthetic/metadata.csv.example.json` and the 40-row previews in
`examples/retail_synthetic/sample/` to see the exact expected shape.

## One wide file

Milestone A reads the multi-table layout only (`layout: multi_table`). If you have one wide weekly file, split
it first; for example with pandas:

```python
import pandas as pd

wide = pd.read_csv("weekly_wide.csv", dtype={"sku": str, "site_group": str})
obs = wide[["sku", "site_group", "wk", "qty", "state", "reported_on"]].rename(columns={
    "sku": "item_id", "site_group": "fpg_id", "wk": "week_start", "qty": "units",
    "state": "observation_state", "reported_on": "known_at"})
obs["week_end"] = (pd.to_datetime(obs["week_start"]) + pd.Timedelta(days=7)).dt.date
obs.to_csv("mydata/observations.csv", index=False)
# offers, items, locations and launches are built the same way from their columns
```

A native wide-file reader is planned for Milestone D.

## Scored evaluation versus forecast-only

Scoring needs completed outcomes. For launches that are still in their first year (no complete labels), do
not put them in a scored stage: `split` reports them as `NOT SCOREABLE` and the run is refused. A
forecast-only workflow (produce forecasts for future launches with a frozen selection, no metrics) is planned
for Milestone D.

## Missing fields

| Missing | Effect |
|---|---|
| demographic shares | if no share columns are declared, B2 similarity uses log households and region; if the target FPG's shares are null, B2 falls back to B1 with a visible reason; donors with null shares are skipped |
| `P` (propensity) | set `features.propensity` to `null`; M1/M2 are reported as `missing_features` |
| `origin_features` table | M1/M2 not run; baselines unaffected |
| category | seasonal profile falls back to flat, recorded as `fallback` |
| households | the request fails visibly (no forecast) |

## Privacy

Reports show aggregates and no raw data rows; `data_quality.json` lists at most ten offending row keys per
validation issue.
`privacy.show_raw_rows_in_report` defaults to `false`. Nothing is uploaded. Keep real data out of the
repository (`.gitignore` excludes run outputs).
