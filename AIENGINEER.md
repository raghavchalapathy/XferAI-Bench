# AIENGINEER.md

Per-domain knowledge base and engineering choices.

## Retail (current domain)
- Task: cold-start forecast for an existing item at a new FPG, 52 weekly forecasts, PAIR0-E and PAIR0-N.
- Rate fallback: item -> subcategory -> product type. Seasonality: category -> product type.
- Analogs: B2 = H x similar-FPG per-household rate; B3 = B2 shrunk toward the national rate.
- Global gradient boosting (LightGBM) is the default ML family, following the M5 findings (Makridakis et al. 2022, https://doi.org/10.1016/j.ijforecast.2021.11.013). Pretrained time-series models (for example Chronos, https://arxiv.org/abs/2403.07815) are opt-in adapters.

## Healthcare
Placeholder. No content yet.

## Other domains
Placeholder. No content yet.

## Libraries and upgrades
- Dataframes: Polars (Rust-backed) by default for new code; pandas remains where existing code uses it. Use uv for environments.
- Scale-out: PySpark (optional `distributed` extra) with native functions only, no `toPandas`. Use SynapseML LightGBM for complete data on a cluster.
- Upgrades: pin in `constraints/core.txt`, then run ruff, mypy (including `--platform win32`) and pytest on Python 3.11 and 3.13 before changing a pin.
