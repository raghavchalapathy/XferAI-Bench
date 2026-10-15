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
| Versioned registry of 29 entries (6 implemented, 1 config_required, 22 unimplemented) with separate implementation/execution/eligibility states | `src/xferbench/methods/registry.py`, `METHOD_SUPPORT.md` |
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

## Remaining work

### Milestone B: boosting, hurdle, neural and feature/graph adapters
- `M4.lightgbm`, `M4.xgboost`, `M4.catboost` (count objectives) and `M5.hurdle` on origin-built pair features,
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
