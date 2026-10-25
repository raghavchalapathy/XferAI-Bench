# Getting started with XferAI-Bench

XferAI-Bench is a local, offline benchmark for one forecasting problem. An existing retail item launches at a Forecast Pixel Group (FPG) where it has **never sold**, and you need 52 weekly unit forecasts. Two scenarios are always scored separately:

- **PAIR0-E**: the FPG already sells other items.
- **PAIR0-N**: the FPG is brand new.

> **Honest status.** Scored benchmark rankings are **pending**. The built-in benchmark data is **synthetic**, so it tests that the software works, not which method is better on real data. The package is not on PyPI; you install it from a clone.

Three steps: **Step 0** installs, **Step 1** runs a demo experiment, **Step 2** runs it on your own data.

## Step 0. Install

You need **Git** and **Python 3.11 or newer** (tested on 3.11 and 3.13). No GPU, no paid services; after install everything runs offline.

```bash
git clone https://github.com/raghavchalapathy/XferAI-Bench.git
cd XferAI-Bench
bash xferAI_setup.sh
```

On Windows PowerShell: `powershell -ExecutionPolicy Bypass -File .\xferAI_setup.ps1`.

The script prints its plan, then seven numbered steps (`[1/7] ✓ Check git` ... `[7/7] ✓ Offline demo`), each with a one-line fix if it fails, and a log in `.xferai-setup.log`. It uses [uv](https://docs.astral.sh/uv/) and the committed `uv.lock`; if uv is missing it installs a pinned uv for your user only (no sudo, your shell profile is not changed) and shows the installer URL, version and sha256 first. It is safe to re-run. Measured on a Linux box with a fast connection: about 20 s with uv, 30 s with pip, 13 s when re-run.

Useful flags (`bash xferAI_setup.sh --help` lists all): `--dry-run` (show the plan, change nothing), `--with-lightgbm`, `--with-spark`, `--no-install-uv` (use pip instead of installing uv), `--python <path>`, `--no-demo`, `--non-interactive`, `--quiet`, `--verbose`. Exit codes: `0` ok, `1` a step failed, `2` bad usage.

**Without the script, with uv:** `uv sync --locked --extra dev` (add `--extra lightgbm` or `--extra distributed` as needed), then `uv run xferbench doctor --profile core`.

**Pip fallback (no uv):**

```bash
python3 -m venv .venv                       # Python 3.11+; e.g. python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -c constraints/core.txt -e ".[dev]"
.venv/bin/xferbench doctor --profile core   # should end with: profile 'core' satisfied
```

On Windows use `.venv\Scripts\python` and `.venv\Scripts\xferbench`. The constraints files are generated from `uv.lock`, so pip gets the same versions.

## Step 1. Run the demo experiment

The setup script ends by printing this block (it is kept in `setup/next_demo.txt` and tested to match):

<!-- BEGIN setup/next_demo.txt -->
```text
Next: run a demo experiment (offline, synthetic data)
  uv run xferbench experiment run exp01_synthetic_lightgbm_analogs
  same without uv: .venv/bin/xferbench experiment run exp01_synthetic_lightgbm_analogs
                   (Windows: .venv\Scripts\xferbench experiment run exp01_synthetic_lightgbm_analogs)
  Tier: synthetic (generated data: an interface test, not a result or a ranking)
  Output: eval/exp01_synthetic_lightgbm_analogs__synthetic/ (eval/<id>__<tier>; -2, -3, ... if it already exists)
  Data: the built-in tiny synthetic retail preset, seed 42. Models: baselines B0, B1, B2, B3 and methods M1, M2,
        plus M4.lightgbm if you installed with --with-lightgbm.
  Runtime: measured on the maintainer's Linux box on 2026-10-24: 16 s (core install), 32 s (with lightgbm).
  Open: SUMMARY.md, leaderboard.html and report.html in that output folder.
  More: docs/GETTING_STARTED.md Step 1 (this demo), Step 2 (your own data), experiments/README.md
  All experiments: uv run xferbench experiment list
```
<!-- END setup/next_demo.txt -->

`uv run xferbench demo --out xb-demo` runs the whole pipeline (generate → validate → split → validation run → select → test run → report) on tiny synthetic data; open `xb-demo/report.html`.

## Step 2. Run on your own data

The setup script asks `Do you want to run on your own data? [y/N]` and, if you answer yes, prints this block (kept in `setup/own_data.txt`):

<!-- BEGIN setup/own_data.txt -->
```text
Your own data (docs/GETTING_STARTED.md Step 2; format: docs/REAL_DATA.md and schemas/FIELD_DICTIONARY.md)
  1. Put your CSV or Parquet files in data/sample_data/input/
     (a sample of your data; use data/complete_data/input/ for the complete dataset). These folders are git-ignored.
  2. Describe the files (interactive; it asks, never guesses):
       uv run xferbench metadata wizard --data data/sample_data/input --out data/sample_data/metadata/metadata.json
  3. Validate them:
       uv run xferbench validate --metadata data/sample_data/metadata/metadata.json
  4. Copy the demo experiment:
       uv run xferbench experiment new exp04_mydata_lightgbm --from exp01_synthetic_lightgbm_analogs
  5. Edit experiments/exp04_mydata_lightgbm/configs/sample.yaml so it reads:
       data:
         metadata: data/sample_data/metadata/metadata.json
  6. Run it on the sample tier:
       uv run xferbench experiment run exp04_mydata_lightgbm --tier sample
  Results: eval/exp04_mydata_lightgbm__sample/ (labelled LOCAL DATA; never commit them).
  Without uv, use .venv/bin/xferbench (Windows: .venv\Scripts\xferbench) instead of "uv run xferbench".
```
<!-- END setup/own_data.txt -->

`data/sample_data/input/`, `data/complete_data/input/`, `local/`, `runs/` and `eval/` are git-ignored. Other folders in the repo are **not**; don't put real data there. Writing a local-data run's output to a non-ignored path inside the repo is refused (exit 2). Column-by-column format: [REAL_DATA.md](REAL_DATA.md) and [FIELD_DICTIONARY.md](../schemas/FIELD_DICTIONARY.md). Tables:

| Table | Required? | One row per | Holds |
|---|---|---|---|
| `observations` | yes | item, FPG, week | weekly `units` plus `observation_state`: `observed`, `observed_censored` (stockout) or `missing` (units null) |
| `offers` | yes | item, FPG, week | whether and how many days the item was offered |
| `items` | yes | item, version | category, product type, optional subcategory, seasonality class |
| `locations` | yes | FPG, version | region, opening date, households, optional demographic shares |
| `launches` | yes | launch | the cold-pair launches to score: item, FPG, first offer week, scenario |
| `origin_features`, `donors`, `future_covariates` | optional | | e.g. the propensity `P` known at the origin |

To start from a template instead of the wizard: `uv run xferbench synth generate --preset tiny --out local/template`, copy it, set `dataset.synthetic` to `false`, delete `_synthetic_truth/` and `generation_report.json`, and replace the tables with yours, keeping the table names.

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
| `features` | `households` definition; `propensity` (expected weekly units per household, season-neutral; set `null` if your P is a probability, which disables M1/M2); `seasonality` settings (mean one over 52 weeks); `hierarchy` (when an item has no history, rates fall back item → subcategory → product type and seasonal shapes category → product type; minimum support 3 FPGs / 2 items; see `docs/METADATA.md`); `demographic_share_columns`; `item_rank_feature`; `item_affinity_prefix` |
| `donor_policy` | which other pairs may be learned from, plus the consistent-exposure window (52 weeks) and minimum measured fraction (0.9) |
| `cohorts` | origin date windows for `train`, `validation`, `test`; `selection_weights` (PAIR0-E 0.5, PAIR0-N 0.5); which launches are ranked; which stages may be used to fit for the test |
| `metrics` | WMAPE = sum\|F−A\|/sum A, Bias = sum F/sum A − 1, MAE; a zero denominator is reported as undefined, never patched |
| `resource_limits` | optional time budgets (`null` = none) |
| `rights` | `data_owner`, `permitted_use`, `input_license` for **your** data |
| `privacy` | network and service calls stay `off`; raw rows are not shown in reports |

Prefer a guided start? `xferbench init --path local/my-bench` creates templates, and `xferbench metadata wizard --data <folder> --out <metadata.json>` maps your columns interactively. See `docs/METADATA.md`.

## Step 2 by hand: the pipeline step by step

`experiment run` does the following for you. To run each stage yourself (commands assume an activated venv, or prefix them with `uv run`):

### Validate

```bash
xferbench validate --metadata local/my-data/metadata.json --out local/my-data/data_quality.json
```

A nonzero exit means errors. Fix them before going on.

### Split

```bash
xferbench split --metadata local/my-data/metadata.json --out local/my-data/splits.json
```

This builds frozen chronological cohorts and runs leakage checks. It prints PAIR0-E / PAIR0-N counts and exits 1 if a check fails. `--out` is a **file**.

### Run on your data

```bash
xferbench run --local-data local/my-data/metadata.json --splits local/my-data/splits.json \
              --stage validation --out runs/local/val-1
```

Optional: `--methods B0,B1,B2,M1,M2` (explicit list, nothing substituted) or `--profile core|all`. Use `xferbench list-methods` to see what's implemented.

### Select (on validation only)

```bash
xferbench select --validation-run runs/local/val-1 --out runs/local/selection.json
```

`--out` is a **file**. Then score only the frozen choice on test:

```bash
xferbench run --local-data local/my-data/metadata.json --splits local/my-data/splits.json \
              --stage test --selection runs/local/selection.json --out runs/local/test-1
```

### Report

```bash
xferbench report --run runs/local/test-1 --out runs/local/test-1-report.html
```

`--out` is the HTML file. A `summary.md` is also written into the run folder.

## Reading the results

- **PAIR0-E and PAIR0-N are always shown separately.** The overall order uses 0.5 × WMAPE(E) + 0.5 × WMAPE(N).
- **WMAPE**: lower is better. **Bias**: above 0 means over-forecasting, below 0 means under-forecasting. If actual sales total zero, both are shown as `N/A`, not a made-up number.
- Methods that failed, need a missing extra or need a recipe (M3) are listed with the reason, never silently dropped.
- Local-data reports carry a **"LOCAL DATA"** banner, and item/FPG IDs are replaced by salted hashes. These results are for you. They are not a benchmark or leaderboard result.
- On synthetic data, a ranking only shows that the pipeline works. It is not evidence about real-world accuracy.
- Each run folder holds `run_manifest.json`, `forecasts.parquet`, `metrics.json`, `leaderboard.csv`, `slices.csv`, `failures.csv` and more (see `docs/QUICKSTART.md`).

## FAQ and troubleshooting

Install problems (proxies, offline installs, Python versions): see [SETUP.md](SETUP.md#troubleshooting).


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
| A method shows "missing extra" | Optional; rerun `bash xferAI_setup.sh --with-lightgbm` (or `uv sync --extra dev --extra lightgbm`) for M4.lightgbm |
| Can I publish my numbers? | Nothing is published automatically. Local-data results are never leaderboard results. |

Exit codes: `0` ok, `1` data/split/config error, `2` bad usage, `3` requested method rejected, `4` partial run (time budget), `130` cancelled.

## Like it?

If XferAI-Bench is useful to you, please ⭐ star the repo on GitHub. It helps others find it. Bug reports and onboarding problems are welcome as GitHub issues; see `CONTRIBUTING.md`.

## Experiments (synthetic interface tests)

```bash
xferbench experiment run exp01_synthetic_lightgbm_analogs     # -> eval/exp01_synthetic_lightgbm_analogs__synthetic/
```

Experiment folders are named `exp<NN>_<dataset>_<method>` (for example `exp04_synthetic_b3`); `xferbench experiment
new` refuses other names.

## Data tiers (synthetic, sample, complete)

Every run states which data it used, and the tier is written to `run_manifest.json`, `metrics.json`,
`leaderboard.csv` (a `tier` column on every row), `report.html`, `summary.md` and, for experiments, `results.json`
(every row), `leaderboard.html` and `SUMMARY.md`:

| tier | meaning |
|---|---|
| `synthetic` | generated data; an interface test only, never a result |
| `sample` | a sample of your own data, not the complete dataset |
| `complete` | your complete dataset |

Switching tier changes only config, not code or the experiment: `xferbench experiment run <id> --tier sample` reads
`experiments/<id>/configs/sample.yaml` (deep-merged over `config.yaml`; set `data.metadata` there to your own
`local/.../metadata.json`), or set `tier:` in `config.yaml`. Outputs go to `eval/<id>__<tier>/` (git-ignored; `-2`,
`-3`, ... if already used). Sample and complete runs are labelled local and keep the LOCAL DATA banner. For
`xferbench run`, `--tier` defaults to `synthetic` for generated data and `complete` otherwise; pass `--tier sample`
when you run on a subset. `xferbench compare` and `xferbench experiment run-all` refuse to mix tiers (exit 2, also
with `--allow-incompatible`).


See [experiments/README.md](../experiments/README.md). These are interface tests, not rankings.
