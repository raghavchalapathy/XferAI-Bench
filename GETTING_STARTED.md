# Getting started with XferAI-Bench

XferAI-Bench is a local, offline benchmark for one forecasting problem. An existing retail item launches at a Forecast Pixel Group (FPG) where it has **never sold**, and you need 52 weekly unit forecasts. Two scenarios are always scored separately:

- **PAIR0-E**: the FPG already sells other items.
- **PAIR0-N**: the FPG is brand new.

> **Honest status.** Scored benchmark rankings are **pending**. The built-in benchmark data is **synthetic**, so it tests that the software works, not which method is better on real data. The package is not on PyPI; you install it from a clone. No claim is made that any method works from day zero; results on your data are measurements on your data only.

This is the single guide, for people at a terminal and for coding assistants (Claude Code, Cursor, Copilot, ChatGPT and similar) acting for a user. Three steps: **Step 0** installs, **Step 1** runs a demo experiment, **Step 2** runs it on your own data. Coding assistants: follow the Rules below, and **stop and ask the user** wherever this guide says **STOP**.

## Rules for coding assistants (always)

1. **No data leaves the machine.** Never upload, paste or send the user's data, metadata values, forecasts or
   reports to any website, API, issue tracker or chat outside this machine. Show the user only aggregates.
2. **Never commit local data or results.** Keep them under `local/` and `runs/local/` (gitignored). Never run
   `git add -f` on them. Before any commit: `git status --porcelain` must not list anything under `local/` or `runs/`.
3. **No telemetry.** XferAI-Bench makes no network or service calls at runtime (`privacy.runtime_network: off`);
   do not add any. Network is needed only to install packages (Step 0), or not at all with a wheelhouse (see Offline / enterprise in Step 0).
   This is the default. Setting `XFERBENCH_ALLOW_WEIGHT_DOWNLOAD=1` lets the optional foundation-model adapters
   download Hugging Face weights (read in `src/xferbench/models/foundation_models/donor_prior.py`, `_hf_kwargs`); without it they
   load only from the local cache. Never set it without the user's explicit approval.
4. Do not change files under `src/` or the evaluator to make a run pass. Fix the data or `metadata.json`.
5. Do not invent answers to STOP questions. Ask the user.

## Step 0. Install

You need **Git** and **Python 3.11 or newer** (tested on 3.11 and 3.13). No GPU, no paid services; after install everything runs offline.

| Need | Check | Expected |
|---|---|---|
| Python 3.11 or newer | `python3 -c "import sys; print(sys.version_info >= (3, 11))"` | `True` (if `False`, try `python3.13`, `python3.12`, `python3.11`; or let the setup script's uv provide one. Assistants: STOP and ask the user to install one if none works) |
| Git | `git --version` | `git version ...` |
| OS | Linux, macOS, Windows (PowerShell script); Windows and macOS are checked in CI only | |

```bash
git clone https://github.com/raghavchalapathy/XferAI-Bench.git
cd XferAI-Bench
bash xferAI_setup.sh
```

On Windows PowerShell: `powershell -ExecutionPolicy Bypass -File .\xferAI_setup.ps1` (the same flags in PowerShell style: `-DryRun`, `-Minimal`, `-WithLightgbm`, ...).

The script prints its plan, then seven numbered steps (`[1/7] ✓ Check git (0.0 s)` ... `[7/7] ✓ Offline demo`), each with its time and a one-line fix if it fails, and a timestamped log in `.xferai-setup.log`. It uses [uv](https://docs.astral.sh/uv/) and the committed `uv.lock`; if uv is missing it installs a pinned uv for your user only (no sudo, your shell profile is not changed) and shows the installer URL, version and sha256 first. It installs the `lightgbm` extra by default so the demo experiment also runs M4.lightgbm; if lightgbm cannot be installed on your platform it warns, continues without it, and says that M4.lightgbm will be skipped. It is safe to re-run.

Coding assistants: run `bash xferAI_setup.sh --dry-run --non-interactive` first (expected: a `Plan:` list and `Dry run: nothing was changed.`, exit 0) and show the plan to the user, then `bash xferAI_setup.sh --non-interactive` (expected: `[1/7]` ... `[7/7]` all ok, exit 0; `.venv/bin/xferbench` exists afterwards). On failure read the `Fix:` line and `.xferai-setup.log`.

Flags (`bash xferAI_setup.sh --help` lists all):

- `--dry-run`: show the plan, change nothing
- `--minimal` (alias `--no-lightgbm`): skip the lightgbm extra; `--with-lightgbm` is the default and puts it back
- `--with-spark`: also install the distributed (Spark) extra
- `--no-install-uv`: use `python -m venv` + pip instead of installing uv
- `--python <version or path>`: the Python to use (3.11+)
- `--no-demo`: skip the tiny offline demo
- `--yes-own-data`: print the "your own data" instructions (Step 2) without asking
- `--non-interactive`: never ask (automatic when `CI` is set or input is not a terminal)
- `--quiet`, `--verbose`, `--version`, `--help`

Exit codes: `0` ok, `1` a step failed, `2` bad usage.

**Without the script, with uv:** `uv sync --locked --extra dev --extra lightgbm` (drop `--extra lightgbm` for a minimal install; add `--extra distributed` for Spark), then `uv run xferbench doctor --profile core`.

**Pip fallback (no uv):**

```bash
python3 -m venv .venv                       # Python 3.11+; e.g. python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -c constraints/core.txt -c constraints/extras.txt -e ".[dev,lightgbm]"
.venv/bin/xferbench doctor --profile core   # should end with: profile 'core' satisfied
```

On Windows use `.venv\Scripts\python` and `.venv\Scripts\xferbench`. The constraints files are generated from `uv.lock` (`constraints/core.txt` for the core, `constraints/extras.txt` for the lightgbm and distributed extras), so pip gets the same versions.

### Offline / enterprise

**Proxy and internal mirror** (Step 0 with network through a proxy):

```bash
export HTTPS_PROXY=http://proxy.example.com:8080 HTTP_PROXY=http://proxy.example.com:8080
export PIP_INDEX_URL=https://mirror.example.com/pypi/simple   # internal mirror, if any
export PIP_CERT=/path/to/corporate-ca.pem                      # if TLS is intercepted
git config --global http.proxy "$HTTPS_PROXY"                  # only if git clone needs the proxy
```
Ask the user for the real proxy, mirror and CA values (STOP); never guess them.

**No-network install (wheelhouse).** On a machine with network, same OS, CPU architecture and Python minor version as the target:

```bash
python3 -m venv /tmp/wh-venv && /tmp/wh-venv/bin/python -m pip install --upgrade pip
/tmp/wh-venv/bin/python -m pip wheel -c constraints/core.txt -c constraints/extras.txt -w local/wheelhouse .
```
Expected: exit 0; `local/wheelhouse/` (gitignored) holds `xfer_bench-<version>-py3-none-any.whl` plus every dependency
wheel. Copy the repo folder including `local/wheelhouse/` to the target, then on the target instead of the setup script:

```bash
.venv/bin/python -m pip install --no-index --find-links local/wheelhouse xfer-bench
.venv/bin/xferbench doctor --profile core
```
Expected: `profile 'core' satisfied`. This is a normal (non-editable) install; all later steps are the same.
No package index, network or telemetry is used after this.

Install problems (proxies, offline installs, Python versions): see also [SETUP.md](docs/SETUP.md#troubleshooting).

## Step 1. Run the demo experiment

The setup script ends by printing this block (it is kept in `setup/next_demo.txt` and tested to match; after a pip install the script prints the `.venv` command first):

<!-- BEGIN setup/next_demo.txt -->
```text
Next: run a demo experiment (offline, synthetic data)
  Why a second demo: xb-demo above was the setup health check; exp01 is a full experiment folder you copy for your own data.
  uv run xferbench experiment run exp01_synthetic_lightgbm_analogs
  same without uv: .venv/bin/xferbench experiment run exp01_synthetic_lightgbm_analogs
                   (Windows: .venv\Scripts\xferbench experiment run exp01_synthetic_lightgbm_analogs)
  Tier: synthetic (generated data: an interface test, not a result or a ranking)
  Output: eval/exp01_synthetic_lightgbm_analogs__synthetic/ (eval/<id>__<tier>; -2, -3, ... if it already exists)
  Data: the built-in tiny synthetic retail preset, seed 42. Models: baselines B0, B1, B2, B3 and methods M1, M2,
        plus M4.lightgbm (installed by default; skipped, with the reason and fix, if setup could not install lightgbm
        or you used --minimal; re-run with --with-lightgbm to enable it).
  Runtime: measured on the maintainer's Linux box on 2026-10-24: 16 s (core install), 32 s (with lightgbm).
  Open: SUMMARY.md, leaderboard.html and report.html in that output folder (the run prints their paths).
  More: GETTING_STARTED.md Step 1 (this demo), Step 2 (your own data), experiments/README.md
  All experiments: uv run xferbench experiment list
```
<!-- END setup/next_demo.txt -->

Two demos, two jobs: `xferbench demo --out xb-demo` (run by setup) is a health check of the whole pipeline (generate → validate → split → validation run → select → test run → report) on tiny synthetic data; open `xb-demo/report.html`. `exp01` is an experiment folder with configs per data tier, which you copy in Step 2.

## Step 2. Run on your own data

The setup script asks `Do you want to run on your own data? [y/N]` and, if you answer yes (or pass `--yes-own-data`), prints this block (kept in `setup/own_data.txt`):

<!-- BEGIN setup/own_data.txt -->
```text
Your own data (GETTING_STARTED.md Step 2; format: docs/REAL_DATA.md and schemas/FIELD_DICTIONARY.md)
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

That is the short path: one experiment command does validate, split, validation run, selection, test run and report. The step-by-step path below (Steps 2.1-2.8) runs each stage by hand with explicit checks; coding assistants should use it, because it has the STOP points.

### Your tables and `metadata.json`

`data/sample_data/input/`, `data/complete_data/input/`, `local/`, `runs/` and `eval/` are git-ignored. Other folders in the repo are **not**; don't put real data there. Writing a local-data run's output to a non-ignored path inside the repo is refused (exit 2). Column-by-column format: [REAL_DATA.md](docs/REAL_DATA.md) and [FIELD_DICTIONARY.md](schemas/FIELD_DICTIONARY.md). Tables:

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

Prefer a guided start? `xferbench init --path local/my-bench` creates templates, and `xferbench metadata wizard --data <folder> --out <metadata.json>` maps your columns interactively. See [METADATA.md](docs/METADATA.md) and [DATA_CLASSES.md](docs/DATA_CLASSES.md).

### Ask the user for (assistants: STOP before Step 2.1)

Ask for all of these in one message, then wait:

1. **Data path**: a folder with their tables as CSV or Parquet. The benchmark needs these logical tables
   (full column list: [`schemas/FIELD_DICTIONARY.md`](schemas/FIELD_DICTIONARY.md)):

   | Table | Required | One row per | Key columns |
   |---|---|---|---|
   | `observations` | yes | item, FPG, week | `item_id, fpg_id, week_start, week_end, units, observation_state, known_at` |
   | `offers` | yes | item, FPG, week | `item_id, fpg_id, week_start, week_end, offer_state, offered_days, available_days, exposure_fraction, stockout_state, known_at` |
   | `items` | yes | item version | `item_id, category, product_type, effective_from, known_at` (+ optional `subcategory`, `seasonality_class`) |
   | `locations` | yes | FPG version | `fpg_id, region, fpg_open_at, households, effective_from, known_at` |
   | `launches` | yes | launch | `launch_id, pair_id, item_id, fpg_id, first_offer_at, first_offer_week, fpg_open_at, origin, scenario, qualification, launch_type, cohort_id` |
   | `origin_features`, `donors`, `future_covariates` | optional | | see FIELD_DICTIONARY |

   Their column names may differ; you will map them in `metadata.json`. If a required table or column does not
   exist in their data, STOP and tell the user which one; do not fabricate it.
2. **A metadata description** (plain text is fine). Ask for each item in the template below:

```text
Data folder:            <path>                       # e.g. /data/retail_export
File per table:         observations=<file>, offers=<file>, items=<file>, locations=<file>, launches=<file>
                        (optional) origin_features=<file>, donors=<file>, future_covariates=<file>
Column renames:         <canonical> = <their column>, per table   # e.g. items: item_id=sku, category=dept
IDs:                    item id column, Forecast Pixel Group (FPG) id column
Time column / frequency: weekly; week_start column; week starts on <Monday|...>; timezone <IANA name>
Reporting delay:        days from week end until the data is available (default 7)
Target:                 the weekly units column; gross units, nonnegative
Missing vs zero:        how a missing week is marked (must be observation_state=missing with null units, never 0)
Hierarchy:              item -> subcategory -> product_type (rates); category -> product_type (seasonality);
                        does `items` have a subcategory column? (optional)
Static features:        households column in locations; demographic share columns (must sum to 1) or none
Propensity P:           is there a season-neutral "expected weekly units per household" feature? name? else none
Cohort windows:         first and last launch origin date for train, validation and test (chronological)
Dataset id / version:   e.g. acme_retail / v1
Rights:                 data owner; permitted use (e.g. "internal benchmarking only")
```

If the user does not know the cohort windows, propose ones from the `launches.origin` date range (oldest third
train, middle validation, newest test) and STOP for confirmation.

### Step by step (Steps 2.1-2.8)

All commands run from the repository root (commands use `.venv/bin/xferbench`; `uv run xferbench` works the same).

#### Step 2.1. Smoke test on synthetic data (no user data involved)

```bash
test -f local/smoke/report.html || .venv/bin/xferbench demo --out local/smoke
```
Expected: ends with `done. Open local/smoke/report.html` (the setup script already ran this as `xb-demo`; skip it if that passed), exit 0 (about 20 s). This only proves the install works.

#### Step 2.2. Create the project folder and copy the user's data

```bash
test -f local/my-bench/metadata.json || .venv/bin/xferbench init --path local/my-bench
mkdir -p local/my-bench/data
cp -Rn <user data folder>/. local/my-bench/data/
```
Expected: exit 0; `initialized local/my-bench` the first time; subfolders are copied too, so point `tables.<name>.path` at the file inside its subfolder (e.g. `data/data/sales.csv`); `local/my-bench/metadata.json` is a template.
Copying keeps paths relative and inside the gitignored `local/`. If the data is too large to copy, leave it
in place and use absolute paths in Step 2.3.

#### Step 2.3. Fill in `local/my-bench/metadata.json`

Edit the JSON (unknown keys are rejected; nothing in it is executed). Change only these parts, from the user's answers:

| Key | Set to |
|---|---|
| `dataset.id`, `dataset.version`, `dataset.description` | user's values; keep `synthetic: false`, `expected_hash: null` |
| `time.timezone`, `time.week_start`, `time.reporting_delay_days` | user's values; keep `frequency: weekly`, `horizon_weeks: 52` |
| `tables.<name>.path` | file path relative to `metadata.json` (e.g. `data/sales.csv`) or absolute |
| `tables.<name>.format` | `csv` or `parquet` |
| `tables.<name>.columns` | `{"<canonical name>": "<their column>"}` only for renamed columns; `{}` if names already match |
| optional tables | delete the `tables.origin_features` / `donors` / `future_covariates` entry if the user has none |
| `features.households.column` | canonical `households` (rename via `tables.locations.columns`) |
| `features.propensity` | the `init` template default is **not** null (`feature_name: "propensity_rate"`): set it to `null` unless the user confirmed a season-neutral units-per-household P; then set `feature_name` |
| `features.hierarchy` | keep the default (`rate_levels` item, subcategory, product_type; `season_levels` category, product_type; `min_rate_support_fpgs` 3; `min_season_support_items` 2). Without a `subcategory` column the rate falls back from item to product type |
| `features.demographic_share_columns` | list of share columns, or `[]` |
| `cohorts.stages.{train,validation,test}` | `origin_start` / `origin_end` (YYYY-MM-DD) confirmed by the user |
| `rights.data_owner`, `rights.permitted_use` | user's values (replace the `REPLACE:` text) |

Example for a user whose items file is `items.csv` with columns `sku, dept, ...`:

```json
"items": {"path": "data/items.csv", "format": "csv", "columns": {"item_id": "sku", "category": "dept"}, "extra_columns": []}
```

Alternative for a person at a terminal (interactive, not for agents): `xferbench metadata wizard --data local/my-bench/data --out local/my-bench/metadata.json`.

#### Step 2.4. Validate (gate)

```bash
grep -c "REPLACE" local/my-bench/metadata.json
.venv/bin/xferbench validate --metadata local/my-bench/metadata.json --out local/my-bench/data_quality.json
```
Expected: `grep` prints `0` (it exits 1 when there is no match, which is fine). Any other number means template
placeholders such as `REPLACE: data owner` remain; validate does not catch them, so STOP and ask the user for the
rights values. Then validate prints `dataset <id> <version> hash <hash>: 0 errors, 0 warnings`, exit 0.
Warnings: show them to the user. `propensity_absent` means set `features.propensity` to `null` unless the user
confirms a P column (M1/M2 are then skipped). Nonzero exit: read the printed errors (also in `data_quality.json`). Fix `metadata.json` mapping mistakes yourself
and re-run. If an error is about the data itself (missing column, wrong values, gaps), **STOP**: show the user the
error text and ask how to fix the data. Do not continue to Step 2.5 until validate exits 0.

#### Step 2.5. Split

```bash
.venv/bin/xferbench split --metadata local/my-bench/metadata.json --out local/my-bench/splits.json
```
Expected: per-stage counts and `split hash ...; N checks, 0 failed`, exit 0. Exit 1 = a leakage/cohort check
failed: STOP and show the failed checks to the user (usually the cohort windows need changing).
If the data or metadata change later, re-run Steps 2.4-2.5.

#### Step 2.6. Validation run

One run counter names every output of Steps 2.6-2.8. Start with `RUN=1`. **After any change in Steps 2.2-2.5, increment
`RUN` and redo Steps 2.6-2.8.** Outputs are append-only: each step refuses (exit 1, `already exists: use a new RUN`)
instead of silently reusing an old folder.

```bash
RUN=1
test ! -e runs/local/val-$RUN || { echo "already exists: runs/local/val-$RUN: use a new RUN"; false; } && \
.venv/bin/xferbench run --local-data local/my-bench/metadata.json \
  --splits local/my-bench/splits.json --stage validation --out runs/local/val-$RUN
```
Expected: a leaderboard, then `run validation-... status complete; data class local; tier complete; outputs in runs/local/val-1` (add `--tier sample` to `run` if your data is only a sample), exit 0.

#### Step 2.7. Select on validation, then score the frozen choice on test

```bash
test ! -e runs/local/selection-$RUN.json || { echo "already exists: runs/local/selection-$RUN.json: use a new RUN"; false; } && \
.venv/bin/xferbench select --validation-run runs/local/val-$RUN --out runs/local/selection-$RUN.json && \
{ test ! -e runs/local/test-$RUN || { echo "already exists: runs/local/test-$RUN: use a new RUN"; false; }; } && \
.venv/bin/xferbench run --local-data local/my-bench/metadata.json --splits local/my-bench/splits.json \
  --stage test --selection runs/local/selection-$RUN.json --out runs/local/test-$RUN
```
Expected: `selected on validation: ... wrote runs/local/selection-1.json`, then `run test-... status complete; data class local`, exit 0.
If it prints `already exists`, STOP: never reuse an older test run; increment `RUN` and redo Steps 2.6-2.8.

#### Step 2.8. Report

```bash
.venv/bin/xferbench report --run runs/local/test-$RUN --out runs/local/test-$RUN-report.html
git status --porcelain
```
Expected: `wrote runs/local/test-1-report.html`, exit 0; `git status --porcelain` prints nothing.
Tell the user to open `runs/local/test-$RUN-report.html` locally. It carries a LOCAL DATA banner and hashes item/FPG IDs.

#### Reading results (tell the user)

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
| Can I publish my numbers? | Nothing is published automatically. Local-data results are never leaderboard results. |
| pip `ProxyError`, `SSLError`, timeouts | Set the proxy / mirror / `PIP_CERT` (Offline / enterprise), or use the wheelhouse |
| `No matching distribution` with `--no-index` | The package name is `xfer-bench` (the command is `xferbench`); otherwise the wheelhouse was built for another OS/arch/Python: rebuild it on a matching machine |
| `metadata invalid ... Extra inputs are not permitted` | Typo or unsupported key in `metadata.json` (the error names it, e.g. `time.frequncy`); compare with the `init` template |
| `[error] missing_column <table>.<col>` (lists the available columns) | Fix `tables.<table>.columns.<col>`, or STOP if the column does not exist in the data |
| `[error] file_not_found` | Fix `tables.<name>.path` (relative paths resolve from `metadata.json`) |
| `split` exits 1 | Cohort windows overlap, are empty, or lack 52 weeks of labels; STOP and agree new windows |
| A method shows "not run" with a missing extra (e.g. M4.lightgbm) | Re-run `bash xferAI_setup.sh --with-lightgbm` (Windows: `.\xferAI_setup.ps1 -WithLightgbm`) or `uv sync --locked --extra dev --extra lightgbm`. If setup warned that lightgbm cannot be installed on your platform, M4.lightgbm stays skipped there |

Exit codes: `0` ok, `1` data/split/config error, `2` bad usage, `3` requested method rejected, `4` partial run (time budget), `130` cancelled.

## Reproduce the VISUELLE website benchmark (licence gate, research only)

Needs Step 0 first.

Status: **results pending**. The VISUELLE licence terms were not found, so no data is shipped or downloaded, and
GTM-Transformer has not been run by us. The paper-reported WAPE 55.2 ([Skenderi et al. 2021, arXiv:2109.09824 v6](https://arxiv.org/abs/2109.09824),
Table 1, GTM-Transformer [T+I+G], 6 weeks, 52-week Google Trends, WAPE column) is shown only as "Paper-reported",
never as ours. Its Scout/Scientist/Reviewer record is **pending Reviewer check**; no record exists yet.

1. **STOP**: ask the user to obtain VISUELLE themselves from the official form linked by the GTM README and to read
   its terms. Never download it for them.
2. Ingest the user's own archive (needs a terminal and typing `I ACCEPT THE VISUELLE TERMS`):
   `experiments/exp03_visuelle_gtm/scripts/download_visuelle.sh --archive <path>` (data stays in git-ignored `data/visuelle/input`).
3. **STOP**: GTM-Transformer (MIT, HumaticsLAB) is not vendored. The user installs and reviews it themselves, then
   sets `gtm.install_path`, `gtm.python` and `gtm.ckpt_path` in `experiments/exp03_visuelle_gtm/config.yaml`.
4. Run: `xferbench experiment run exp03_visuelle_gtm --allow-research-only`. If anything is missing it exits 3 and
   `report.md` lists what is blocked.

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


See [experiments/README.md](experiments/README.md). These are interface tests, not rankings.
