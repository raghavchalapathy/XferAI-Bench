# Harness rules (seed, 2026-10-24)

## Data preparation
- One pipeline is shared by complete, sample and synthetic data. Use Polars plus uv and Rust-backed libraries by default. Use PySpark only where data size needs it.
- PySpark: no `toPandas`. Use native functions only. Avoid multi-step aggregations; ask the user first. Prefer simple steps.
- Flag data issues (duplicate keys, negative units) instead of silently fixing them.

## Models
- Prefer scalable libraries (for example SynapseML LightGBM on Spark). Run locally on sample or synthetic data; run complete data on a cluster. This applies to every family.
- Offline, weight-based models are adapters that report `config_required`. The default path never downloads anything.

## Retail rules (carried over)
- Rate fallback: item -> subcategory -> product type.
- Seasonality: category -> product type.
- B2 = H x similar-FPG per-household rate. B3 = B2 shrunk toward the national rate.
- Objective: 0.5*WMAPE(PAIR0-E) + 0.5*WMAPE(PAIR0-N). Cold-start only. The evaluator logic and hash are protected.

## Excluded
POP (rejected), VISUELLE (blocked), TimeGPT (dropped), Moirai and TimesFM 3.0 (non-commercial).
