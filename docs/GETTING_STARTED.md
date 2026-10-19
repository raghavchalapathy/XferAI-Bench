# Getting started with XferAI-Bench

XferAI-Bench is a local, offline benchmark for one forecasting problem. An existing retail item launches at a location group (FPG) where it has **never sold**, and you need 52 weekly unit forecasts. Two scenarios are always scored separately:

- **PAIR0-E**: the location group already sells other items.
- **PAIR0-N**: the location group is brand new.

> **Honest status.** Scored benchmark rankings are **pending**. The built-in benchmark data is **synthetic**, so it tests that the software works, not which method is better on real data. The package is not on PyPI; you install it from a clone.

## 1. Prerequisites

- **Python 3.11 or newer.** `pyproject.toml` sets `requires-python = ">=3.11"`. Tested on 3.11 and 3.13.
- **Git.**
- No GPU, no network, no paid services.
- macOS or Linux shell. The commands were tested end to end on Linux with Python 3.11 and 3.13; CI also runs Windows, but the Windows shell commands here are untested.

## 2. Clone

```bash
git clone https://github.com/raghavchalapathy/XferAI-Bench.git
cd XferAI-Bench
```

## 3. Create a virtual environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
```

If `python3` is older than 3.11, use a newer interpreter, for example `python3.11 -m venv .venv`.

## 4. Install

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/xferbench --help
.venv/bin/xferbench doctor --profile core
```

`doctor` should end with `profile 'core' satisfied`.

The commands below assume the venv is active (`source .venv/bin/activate`), so `xferbench` is on your PATH.

## 5. Check it works

```bash
xferbench demo --out xb-demo
```

This runs the whole pipeline on tiny synthetic data: generate → validate → split → validation run → select → test run → report. Open `xb-demo/report.html` in a browser. It takes about 15-20 seconds on a laptop.

## 6. Bring your own data

**Where to put it.** Keep your data and results **out of git**. `.gitignore` already ignores `local/`, `runs/`, `runs/local/` and `*.local.*`. We recommend:

- data in `local/my-data/` (or any folder outside the repo)
- results in `runs/local/<run-name>/`

`work/` and other folders are **not** ignored. Don't put real data there. Writing a local-data run's output to a non-ignored path inside the repo is refused (exit 2).

**Start from a template.** Generate the tiny synthetic dataset and copy its layout:

```bash
xferbench synth generate --preset tiny --out local/template
```

This writes `local/template/metadata.json`, a `data/` folder of Parquet tables, `FIELD_DICTIONARY.md` (every column) and `DATA_STORY.md`. Add `--format csv` or `--format both` if you prefer CSV.

Copy the template (`cp -r local/template local/my-data`), set `dataset.synthetic` to `false`, delete the synthetic-only `_synthetic_truth/` folder and `generation_report.json`, and replace the tables with your own, keeping the same table names:

| Table | Required? | One row per | Holds |
|---|---|---|---|
| `observations` | yes | item, FPG, week | weekly `units` plus `observation_state`: `observed`, `observed_censored` (stockout) or `missing` (units null) |
| `offers` | yes | item, FPG, week | whether and how many days the item was offered |
| `items` | yes | item, version | category, product type, optional subcategory, seasonality class |
| `locations` | yes | FPG, version | region, opening date, households, optional demographic shares |
| `launches` | yes | launch | the cold-pair launches to score: item, FPG, first offer week, scenario |
| `origin_features`, `donors`, `future_covariates` | optional | | e.g. the propensity `P` known at the origin |

**What each part of `metadata.json` means.** These are the sections in the generated file. Required by the schema: `dataset`, `tables`, `cohorts`, `rights`. Unknown keys are rejected, and nothing in the file is executed.

| Section | What to put there |
|---|---|
| `schema_version` | `"1.0"` |
| `dataset` | `id`, `version`, `description`, `synthetic` (set `false` for yours), optional `expected_hash` (loading fails if the data changes). The `generator` block only applies to synthetic data. |
| `domain_plugin` | `"retail"` |
| `task_profile` | `"retail_pair_zero_v1"` |
| `entity_roles` | which columns are the item (`item_id`) and the location (`fpg_id`) |
| `request_key` | `item_id, fpg_id, origin, horizon_week` |
| `layout` | `"multi_table"` |
| `time` | timezone, weekly frequency, `week_start` (Monday), `[start,end)` weeks, `reporting_delay_days`, `horizon_weeks` (52), `origin_rule` (`first_offer_week`) |
| `target` | the units column (`units`), gross weekly item units, nonnegative |
| `tables` | for each table: `path` (relative to `metadata.json`), `format` (`csv` or `parquet`), `columns` (map canonical name → your column name, only if renamed), `extra_columns` |
| `semantics` | how missing weeks, true zeros, never-offered weeks, stockouts and partial weeks are represented. Missing is never zero. |
| `features` | `households` definition; `propensity` (expected weekly units per household, season-neutral; set `null` if your P is a probability, which disables M1/M2); `seasonality` settings (mean one over 52 weeks); `hierarchy` (when an item has no history, rates fall back item → subcategory → product type and seasonal shapes category → product type; minimum support 3 location groups / 2 items; see `docs/METADATA.md`); `demographic_share_columns`; `item_rank_feature`; `item_affinity_prefix` |
| `donor_policy` | which other pairs may be learned from, plus the consistent-exposure window (52 weeks) and minimum measured fraction (0.9) |
| `cohorts` | origin date windows for `train`, `validation`, `test`; `selection_weights` (PAIR0-E 0.5, PAIR0-N 0.5); which launches are ranked; which stages may be used to fit for the test |
| `metrics` | WMAPE = sum\|F−A\|/sum A, Bias = sum F/sum A − 1, MAE; a zero denominator is reported as undefined, never patched |
| `resource_limits` | optional time budgets (`null` = none) |
| `rights` | `data_owner`, `permitted_use`, `input_license` for **your** data |
| `privacy` | network and service calls stay `off`; raw rows are not shown in reports |

Prefer a guided start? `xferbench init --path local/my-bench` creates templates, and `xferbench metadata wizard --data <folder> --out <metadata.json>` maps your columns interactively. See `docs/METADATA.md`.

## 7. Validate

```bash
xferbench validate --metadata local/my-data/metadata.json --out local/my-data/data_quality.json
```

A nonzero exit means errors. Fix them before going on.

## 8. Split

```bash
xferbench split --metadata local/my-data/metadata.json --out local/my-data/splits.json
```

This builds frozen chronological cohorts and runs leakage checks. It prints PAIR0-E / PAIR0-N counts and exits 1 if a check fails. `--out` is a **file**.

## 9. Run on your data

```bash
xferbench run --local-data local/my-data/metadata.json --splits local/my-data/splits.json \
              --stage validation --out runs/local/val-1
```

Optional: `--methods B0,B1,B2,M1,M2` (explicit list, nothing substituted) or `--profile core|all`. Use `xferbench list-methods` to see what's implemented.

## 10. Select (on validation only)

```bash
xferbench select --validation-run runs/local/val-1 --out runs/local/selection.json
```

`--out` is a **file**. Then score only the frozen choice on test:

```bash
xferbench run --local-data local/my-data/metadata.json --splits local/my-data/splits.json \
              --stage test --selection runs/local/selection.json --out runs/local/test-1
```

## 11. Report

```bash
xferbench report --run runs/local/test-1 --out runs/local/test-1-report.html
```

`--out` is the HTML file. A `summary.md` is also written into the run folder.

## 12. Reading the results

- **PAIR0-E and PAIR0-N are always shown separately.** The overall order uses 0.5 × WMAPE(E) + 0.5 × WMAPE(N).
- **WMAPE**: lower is better. **Bias**: above 0 means over-forecasting, below 0 means under-forecasting. If actual sales total zero, both are shown as `N/A`, not a made-up number.
- Methods that failed, need a missing extra or need a recipe (M3) are listed with the reason, never silently dropped.
- Local-data reports carry a **"LOCAL DATA"** banner, and item/FPG IDs are replaced by salted hashes. These results are for you. They are not a benchmark or leaderboard result.
- On synthetic data, a ranking only shows that the pipeline works. It is not evidence about real-world accuracy.
- Each run folder holds `run_manifest.json`, `forecasts.parquet`, `metrics.json`, `leaderboard.csv`, `slices.csv`, `failures.csv` and more (see `docs/QUICKSTART.md`).

## FAQ and troubleshooting

| Problem | What to do |
|---|---|
| `requires a different Python` | Recreate the venv with Python 3.11+ |
| `TypeError: Parameter.make_metavar() ... 'ctx'` | `pip install "typer>=0.16"` |
| "is not empty; choose a new --out" | Runs are append-only; pick a new `--out` |
| `dataset_hash_mismatch` | Your data changed; review it, then update `dataset.expected_hash` |
| "splits.json was built for different data" | Rerun `xferbench split` |
| "the test stage requires --selection" | Run validation, then `select`, then test |
| Exit 2 when writing local results | Your `--out` is inside the repo but not gitignored; use `runs/local/...` or a folder outside the repo |
| Exit 3 with `--methods M3` | M3 needs a recipe nobody has supplied yet; drop it |
| A method shows "missing extra" | Optional; e.g. `pip install -e ".[lightgbm]"` for M4.lightgbm |
| Can I publish my numbers? | Nothing is published automatically. Local-data results are never leaderboard results. |

Exit codes: `0` ok, `1` data/split/config error, `2` bad usage, `3` requested method rejected, `4` partial run (time budget), `130` cancelled.

## Like it?

If XferAI-Bench is useful to you, please ⭐ star the repo on GitHub. It helps others find it. Bug reports and onboarding problems are welcome as GitHub issues; see `CONTRIBUTING.md`.
