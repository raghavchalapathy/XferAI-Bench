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

## Scalable evaluation (REVIEWER FLAG)
`xferbench.scalable_eval` computes WMAPE(E), WMAPE(N) and the objective (0.5*WMAPE(E)+0.5*WMAPE(N)) as partial sums: Polars lazy `group_by`, or native PySpark aggregations that collect only the small aggregates (enforced by the AST lint `tests/unit/test_no_driver_collect.py`, with an explicit allowlist). It sits next to the protected evaluator and does not replace it. `src/xferbench/evaluation/` is unchanged and remains the reference. Parity is checked by `tests/unit/test_scalable_eval.py` (Polars always; Spark-local when `pyspark` and Java are installed, and in the `spark-parity` CI job), including the Reviewer's adversarial cases in `tests/review/` (duplicate forecast rows, NaN actuals) and by every experiment run (`results.json: scalable_eval_parity`). A Reviewer has to sign off before it is used for anything official.

## Library versions (dev venv, 2026-10-24)
Python 3.13.5 and 3.11.17; pandas 3.1.0; polars 2.0.0 (minimum in pyproject 1.3); numpy 2.5.4. `uv.lock` is the
resolved set (`uv sync`); `constraints/core.txt` plus pip remains supported.

## Polars swaps
- `domains/retail/plugin.py::_attach_slices` uses a Polars join + `group_by(...).last()` (`_as_of_attr`) in place
  of a per-request pandas loop. The loop is kept as `_attach_slices_reference`; parity tested in
  `tests/unit/test_polars_swaps.py` (evaluator outputs and scalable_eval unchanged). Benchmark:
  `python scripts/bench_polars_swaps.py` (synthetic timing only, median of repeats plus machine specs).
- Not swapped: the protected evaluator, `util.hash_frame` (dataset hashes depend on it), and code that is not a hot path.

## Scout note: Polars docs for CSV/Parquet prep and joins (PENDING REVIEWER)
Source: `factory/inbox/scout/odsc-west-2026/polars_note_for_builder_v1.md`, sha256 6b27d03785735b38059be0805f3b275ef77005020bb018b4c20435dee247932e (verified
2026-10-24). Not yet reviewed; do not treat as adopted guidance. Official Polars docs only:
- CSV: https://docs.pola.rs/user-guide/io/csv/
- Parquet: https://docs.pola.rs/user-guide/io/parquet/
- Lazy API: https://docs.pola.rs/user-guide/concepts/lazy-api/
- Joins (incl. `join_asof`): https://docs.pola.rs/user-guide/transformations/joins/
The docs version was not verified by Scout.
