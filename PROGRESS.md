# Progress

Requirements: `reference/Xfer_Benchmark_Cursor_Prompt.txt` (full specification) and `reference/context/`.
The reference files are unchanged (all 12 SHA-256 hashes in `reference/HANDOFF_MANIFEST.json` verified on
2026-10-15). Note: the files sit directly in `reference/`, not in `reference/xfer-bench-cursor-handoff/`.

## Milestone A: complete (2026-10-15)

Vertical slice: installable package, synthetic retail data and metadata, origin contexts, frozen splits,
core baselines, fair evaluation, frozen validation selection, HTML report, tests and a verified wheel.

### Environment used

- macOS 26.2 arm64; Git 2.50.1.
- Python 3.11.5 (Anaconda) for the project venv `.venv/`; Python 3.13.0 (Homebrew) for a second clean check.
  Python 3.12 is not installed on this machine and is therefore not claimed as supported.
- All installs went into virtual environments (`.venv/` and `/tmp/xb-*`); the global Python was not changed.

### What exists

| Area | Location |
|---|---|
| Package (`xfer-bench`, import `xferbench`, CLI `xferbench`) | `src/xferbench/`, `pyproject.toml` (hatchling, Apache-2.0) |
| Contracts: tables, strict metadata, splits, selection, method capabilities | `src/xferbench/contracts/`, exported to `schemas/` |
| CSV/Parquet loading into canonical Arrow types, dataset hash | `src/xferbench/data/io.py` |
| Retail domain plugin: validation, splits, requests, targets, profile | `src/xferbench/domains/retail/` |
| Origin-scoped contexts with holdout exclusions | `src/xferbench/features/context.py` |
| Donor aggregates: pair/national rates, mean-one seasonal profiles | `src/xferbench/features/aggregates.py` |
| Baselines B0, B1, B2 (grid k x kappa), B2.raw_units, M1, M2; typed M3 hook | `src/xferbench/methods/` |
| Versioned registry (see METHOD_SUPPORT.md for current counts) with separate implementation/execution/eligibility states | `src/xferbench/methods/registry.py`, `METHOD_SUPPORT.md` |
| Evaluator (fixed population, undefined zero-denominator metrics, coverage rule, slices) | `src/xferbench/evaluation/` |
| Runner (preflight, 52-row contract, append-only outputs, budget/partial, exit codes) | `src/xferbench/orchestration/` |
| Synthetic generator (presets tiny/small/stress, edge fixtures, hidden truth, data story) | `src/xferbench/synth/` |
| Self-contained HTML report, Markdown summary, run comparison | `src/xferbench/reports/` |
| CLI: synth generate, validate, split, run, select, report, compare, list-methods, doctor, init, schemas, metadata wizard, demo | `src/xferbench/cli/main.py` |
| Docs | `README.md`, `docs/` (QUICKSTART, METADATA, REAL_DATA, METHODS, EVALUATION, EXTENDING, SETUP), `CONTRIBUTING.md` |
| Examples | `examples/retail_synthetic/` (metadata examples, selection policy, DATA_STORY, FIELD_DICTIONARY, 40-row CSV previews) |
| Packaging aids | `bootstrap.sh`, `bootstrap.ps1`, `constraints/core.txt`, `constraints/minimum.txt`, `.github/workflows/ci.yml` (prepared, not run) |

### Demo

```bash
cd /Users/raghav/Documents/RationalAI/InnovationLoops/products/XferAI/xferAI-bench
.venv/bin/xferbench demo --preset tiny --out ./xb-demo      # refuses a non-empty --out; pick a new folder
open ./xb-demo/report.html
```

Outputs of the last run (git-ignored): data and metadata in `xb-demo/data/` (`metadata.json` for Parquet,
`metadata.csv.json` for CSV, tables in `xb-demo/data/data/`, hidden truth in `xb-demo/data/_synthetic_truth/`),
`xb-demo/splits.json`, `xb-demo/validation-run/`, `xb-demo/selection.json`, `xb-demo/test-run/`, and the report
`xb-demo/report.html`.

Tiny demo facts (seed 42): dataset hash `c11c9c25...` identical for CSV and Parquet; generator zero-fraction
calibration 0.800 expected vs 0.805 realised on training-period offered weeks; 105 split checks passed;
validation 16 ranked launches (8 E / 8 N), test 16 ranked + 6 edge fixtures; about 10 s end to end.
Validation selection rejected `B2.raw_units` (PAIR0-N Bias -52%, limit +/-50%) and recommended `M2`; the
test run scored only the frozen `B0`, `B1`, `B2[k=3,kappa=1.0]`, `M1`, `M2`. These are synthetic software
demonstrations, not evidence about real data.

### Verification actually run

| Check | Result |
|---|---|
| `pytest` in `.venv` (Python 3.11.5): unit, integration, leakage | 75 passed |
| `ruff check`, `ruff format --check`, `mypy` (pydantic plugin) | clean |
| `python -m build` | `dist/xfer_bench-0.1.0-py3-none-any.whl`, `dist/xfer_bench-0.1.0.tar.gz` |
| Wheel into a fresh venv at `/tmp/xb-wheel-311` (Python 3.11.5), run from `/tmp` | installed from `site-packages`; `--help`, `--version`, `doctor`, full tiny demo, `validate` on the CSV metadata all exit 0; identical leaderboard to the source tree; no heavy/optional module imported |
| Wheel into `/tmp/xb-wheel-313` (Python 3.13.0) + sdist tests with `src/` removed | tiny demo exit 0; 75 passed against the installed wheel |
| Lowest declared versions (numpy 1.26.4, pandas 2.2.0, pyarrow 15.0.0, pydantic 2.6.4, typer 0.16.0, Jinja2 3.1.2) | 75 passed (this found and fixed a pandas 2.2 dtype warning and raised the Typer floor to 0.16) |
| `bootstrap.sh` with a wheel into a new venv; second call on the same folder | installs and runs doctor; second call refuses to modify the existing venv |
| `small` preset demo | exit 0, about 58 s, 1.2 GB max RSS |
| Report visual check in a browser | layout, charts, slice tables and method tables render; user labels escaped |

Spec test coverage: 1-9, 13, 15, 16 covered; 14 covered for an external method (registered at runtime and
via the runnable `docs/EXTENDING.md` example), not yet for an external domain plugin; 17 covered for budget
stop (partial, unranked), not for checkpoint retries. 10-12 concern adapters from Milestones B and C.

### Decisions made

- Variant IDs name only grid-varying parameters (for example `B2[k=3,kappa=1.0]`).
- Ruff line length 120, E501 not enforced for long user-facing strings; `ruff format` governs layout.
- `reference/` is git-ignored so the research kit is never versioned or pushed from this repo by accident.
- The full tiny dataset (5.4 MB) is not committed; `examples/` holds metadata, docs and 40-row previews,
  and the data is regenerated deterministically by `xferbench synth generate`.
- Git remote `origin` = https://github.com/raghavchalapathy/XferAI-Bench (public). Milestone A was pushed to
  `main` on 2026-10-15 at the owner's request; later changes are committed locally and pushed only after the
  owner confirms. Nothing is published to PyPI; no paid calls, downloads or telemetry.

## Milestone B (partial) and data classes: 2026-10-16 (local commits, not pushed)

Done on a Linux box (Python 3.11.17 via uv, LightGBM 4.7.0 in `.venv`):

- Benchmark data vs local data (`docs/DATA_CLASSES.md`): versioned, hashed built-in benchmarks
  (`synthetic-tiny@1.0.0`, `synthetic-small@1.0.0`, `xferbench benchmarks`); `--benchmark`, `--local-data`;
  legacy `--metadata` outside `benchmarks/` is treated as local with a warning; local outputs refused at
  non-ignored paths inside a git work tree; entity IDs in local reports replaced by salted hashes; compare refuses
  mixed classes; `.gitignore` covers `local/`, `runs/local/`, `*.local.*`. The separation layer is
  domain-generic (uses the plugin's `entity_columns`).
- `M4.lightgbm` implemented as a lazy optional extra (`.[lightgbm]`), with leakage, not-installed and contract tests.
- `xferbench steps`: methods in order, each adding one idea, declared by the domain plugin (retail: B0, B1,
  B2.raw_units, M1, M2, M3, M4.lightgbm). The registry `B2[k,kappa]` stays registered but is not run or shown there.
  Report section and `methods_in_order.json` with WMAPE and Bias per scenario and the deltas
  M1-B0, B1-B0, M2-M1, M3-M2 (N/A while M3 is config_required), M4-M2 (labelled "M3 pending recipe").
- Checks: pytest 94 passed, ruff check and format clean, mypy clean (57 files).
- First `steps` run on `synthetic-tiny@1.0.0` (SYNTHETIC; software behaviour only): B0, B1, B2.raw_units[k=3], M1, M2
  and M4.lightgbm ran; M3 shown as config_required with its reason. See the final report of 2026-10-16.

Still open in Milestone B: `M4.xgboost`, `M4.catboost`, `M5.hurdle`, `M6`, `M7`, `M9`; optional anchor-week M2
ablation not added (kept out to avoid any anchor division in the default path).

## Remaining work

### Milestone B: boosting, hurdle, neural and feature/graph adapters
- `M4.xgboost`, `M4.catboost` (count objectives; `M4.lightgbm` done 2026-10-16) and `M5.hurdle` on origin-built pair features,
  executed on the same synthetic protocol; handle single-class hurdle cases.
- `M6.deepar_count` (GluonTS, negative binomial, missing masks, new-FPG behaviour) and `M7.two_tower_count`.
- `M9.graph_transfer` with origin-valid edges and leakage tests for edges.
- Optional-extra install tests (`heavy` marker), honest `not_installed` handling, and `doctor` profiles.

### Milestone C: composites, foundation and service adapters
- M3 executor from a user-supplied `M3RecipeSpec` (still `config_required`; no formula was provided).
- `M8.prior_allocation`, `E1.convex_blend` (weights fitted on validation only, sum to one, frozen for test).
- Foundation donor priors (`FM.chronos2`, `FM.chronos_bolt`, `FM.timesfm25`) as labelled composites with
  explicit weight preparation; keep `FM.timesfm3`, `FM.moirai2`, `FM.tabpfn_ts` `license_blocked` unless a
  grant is recorded; `SVC.timegpt` opt-in only with credentials, egress permission and budget.
- Separately named cold composites for warm-reference methods; output-statistic (quantile vs mean) handling.
- Paired block-bootstrap uncertainty in the report.

### Milestone D: real-data ingestion and extensibility
- Verify ingestion of a differently named CSV/Parquet fixture through metadata mapping alone; native
  one-wide-file layout; forecast-only workflow for launches without complete labels.
- Tiny non-retail domain plugin with tests (spec test 14 for plugins).
- Resumable batching/checkpoints with identical, non-duplicated outputs on retry (spec test 17); bounded
  stress-preset run.

### Milestone E: polish and release readiness
- Run the prepared CI on Linux, macOS and Windows; extend the compatibility matrix with real results
  (including Python 3.12 if installed).
- Documentation and report review against the full specification; final wheel/sdist and clean-environment
  demos; release notes. Publishing stays a separate, explicit decision.

## Session 2026-10-16 (licence gates)

- Benchmark licence gate (`xferbench.data.classes.check_benchmark_licence`): `BENCHMARK.json` with
  `usage_tag: blocked`, or any dataset matching `BLOCKED_DATASETS` (currently `visuelle`, no data licence found),
  is refused as benchmark data with exit 2.
- Research-only methods (`RegistryEntry.research_only`): Moirai 2.0, TabPFN-TS, TimesFM 3 and the new planned
  `EXT.pop` adapter are excluded from every default profile; explicit use needs `--allow-research-only` (exit 2
  otherwise) and the run manifest records `usage_label: internal_research_only`. Registry 2026.10.16-b (30 entries).
- Tests: `tests/integration/test_licence_gates.py` (7 tests). Suite: 101 passed; ruff, format and mypy clean.

## Session 2026-10-16 (reviewer follow-ups)

- Ranking heading in report.html, summary.md and the CLI board now reads "Interface check: method ordering on this
  run (real benchmark rankings pending)" with a note that synthetic runs only test the interface
  (`tests/integration/test_ranking_heading.py`). Evaluator and harness validator unchanged (deferred to cycle 3).
- FM.tabpfn_ts now points at Prior-Labs/tabpfn_2_5 revision 6c45f3a6d0d07c6c5f62572e04a0c2929de91b8b (TABPFN-2.5
  License v1.1, sha256 ac1d2342..., non-commercial/non-production), research-only behind --allow-research-only.
  TabPFN 3.5 licence is unread: no 3.5 weights are pulled until a licence read is reviewed. Registry 2026.10.16-c.

## Session 2026-10-16 (adapters, B2/B3, TimeGPT, provenance)

- Licence-pinned donor-prior composites (`src/xferbench/methods/foundation.py`): FM.chronos2, FM.chronos_bolt
  (tiny/mini/small/base variants), FM.timesfm25, M6.deepar_count. experimental, donor_only composite: backend
  forecasts the item's origin-scoped donor rate per household, allocated by target households. Code pins from R3,
  HF weight revisions from pins.v2. Lazy imports; weights from local cache only unless
  XFERBENCH_ALLOW_WEIGHT_DOWNLOAD=1; tested with fake backends only. Not Reviewer-recommended for PAIR0.
  pytorch-forecasting / neuralforecast: no registry entry fits the C0 board (all warm_reference), so none added.
  M4.xgboost / M4.catboost: not covered by the R3 pins, left unimplemented.
- B2 = H_target x similar-FPG per-household rate (no shrinkage); B3 = B2 shrunk toward the national rate (old
  B2[k,kappa]), extra row with a B3 vs B2 shrinkage comparison. Old B2.raw_units retired (unregistered class only).
- SVC.timegpt removed (deferred by the user).
- run_manifest.json `software.git_commit` / `git_dirty`.
- Registry 2026.10.16-d. Suite: 128 passed; ruff, format, mypy clean.

## Session 2026-10-16 (shared hierarchy, readiness fixes)

- Shared retail hierarchy (`features/hierarchy.py`): rate item -> subcategory -> product_type, season category ->
  product_type, thresholds in the domain FeatureSpec; origin-only; levels recorded in forecasts and the manifest.
  Synthetic benchmarks bumped to 1.1.0 (subcategory column; 1.0.0 directories removed, hashes in manifests).
- `run --selection <dir|bad file>` now gives a clear error and exit 2 (tests in test_cli.py).
- evaluation/metrics.py: typing-only mypy fix (float cast), proven behaviour-neutral on synthetic-tiny 1.0.0
  (metrics, method order and forecasts identical before/after). Evaluator logic unchanged.
- Registry 2026.10.16-e.
