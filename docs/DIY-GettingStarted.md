# DIY Getting Started with a coding assistant

This file is written for an LLM coding assistant (Claude Code, Cursor, Copilot, ChatGPT and similar) acting
for a user. Follow the steps in order. **Stop and ask the user** wherever this file says **STOP**. The Rules,
Prerequisites and Setup below apply to both parts.

Two parts: **Part 1** reproduces the VISUELLE / GTM-Transformer website benchmark (licence-gated, research only).
**Part 2** runs XferAI-Bench on your own data (same flow as [GETTING_STARTED.md](GETTING_STARTED.md), which uses
`local/my-data` where this guide uses `local/my-bench`).

## Rules (always; apply to Part 1 and Part 2)

1. **No data leaves the machine.** Never upload, paste or send the user's data, metadata values, forecasts or
   reports to any website, API, issue tracker or chat outside this machine. Show the user only aggregates.
2. **Never commit local data or results.** Keep them under `local/` and `runs/local/` (gitignored). Never run
   `git add -f` on them. Before any commit: `git status --porcelain` must not list anything under `local/` or `runs/`.
3. **No telemetry.** XferAI-Bench makes no network or service calls at runtime (`privacy.runtime_network: off`);
   do not add any. Network is needed only to install packages (Step 3), or not at all with a wheelhouse (Offline install).
   This is the default. Setting `XFERBENCH_ALLOW_WEIGHT_DOWNLOAD=1` lets the optional foundation-model adapters
   download Hugging Face weights (read in `src/xferbench/models/foundation_models/donor_prior.py`, `_hf_kwargs`); without it they
   load only from the local cache. Never set it without the user's explicit approval.
4. Do not change files under `src/` or the evaluator to make a run pass. Fix the data or `metadata.json`.
5. Do not invent answers to STOP questions. Ask the user.

## Prerequisites

| Need | Check | Expected |
|---|---|---|
| Python 3.11 or newer | `python3 -c "import sys; print(sys.version_info >= (3, 11))"` | `True` (if `False`, try `python3.13`, `python3.12`, `python3.11`; STOP and ask the user to install one if none works) |
| Git | `git --version` | `git version ...` |
| Disk / RAM | none special for small data | no GPU needed |
| OS | macOS or Linux shell (commands below). Windows: use WSL, or translate `.venv/bin/` to `.venv\Scripts\` (untested) | |

## Setup (both parts): Steps 1-3

All commands run from the repository root. `X` below means `.venv/bin/xferbench`.

### Step 1. Clone (skip if already cloned)

```bash
git clone https://github.com/raghavchalapathy/XferAI-Bench.git && cd XferAI-Bench
```
Expected: exit 0. If the folder exists, `cd XferAI-Bench && git status` instead. Behind a proxy, see Offline / enterprise.

### Step 2. Create the virtual environment

```bash
test -x .venv/bin/python || python3 -m venv .venv
.venv/bin/python -c "import sys; assert sys.version_info >= (3, 11), sys.version; print('ok', sys.version.split()[0])"
```
Expected: `ok 3.11.x` (or newer), exit 0. If the assert fails, delete `.venv` and recreate it with `python3.11 -m venv .venv` (or newer).

### Step 3. Install

```bash
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -c constraints/core.txt -e .
.venv/bin/xferbench doctor --profile core
```
Or with uv (uses `uv.lock`): `uv sync && uv run xferbench doctor --profile core`.
Expected: last line `profile 'core' satisfied`, exit 0. Optional: `-e ".[lightgbm]"` adds M4.lightgbm.
No network? Use the wheelhouse (Offline / enterprise) instead of this step.

## Part 1. Reproduce the VISUELLE website benchmark (licence gate)

Needs Setup Steps 1-3 first.

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

## Part 2. Run XferAI-Bench on your own data

### Goal

Benchmark cold-start forecasts on the user's own retail data, locally:
an existing item launches at a Forecast Pixel Group (FPG) where it has never sold, and each method forecasts 52
weekly unit sales. Results come out as a local HTML report with PAIR0-E (existing FPG) and PAIR0-N
(new FPG) always scored separately.

Honest limits:
- No claim is made that any method works from day zero; results are measurements on the user's data only.
- Built-in benchmark data is synthetic and only tests the software. Scored public rankings are pending.
- Local-data results are private to the user. They are not benchmark or leaderboard results.

### Ask the user for (STOP before Step 4)

Ask for all of these in one message, then wait:

1. **Data path**: a folder with their tables as CSV or Parquet. The benchmark needs these logical tables
   (full column list: [`schemas/FIELD_DICTIONARY.md`](../schemas/FIELD_DICTIONARY.md)):

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

### Steps 4-11

#### Step 4. Smoke test on synthetic data (no user data involved)

```bash
test -f local/smoke/report.html || .venv/bin/xferbench demo --out local/smoke
```
Expected: ends with `done. Open local/smoke/report.html`, exit 0 (about 20 s). This only proves the install works.

#### Step 5. Create the project folder and copy the user's data

```bash
test -f local/my-bench/metadata.json || .venv/bin/xferbench init --path local/my-bench
mkdir -p local/my-bench/data
cp -Rn <user data folder>/. local/my-bench/data/
```
Expected: exit 0; `initialized local/my-bench` the first time; subfolders are copied too, so point `tables.<name>.path` at the file inside its subfolder (e.g. `data/data/sales.csv`); `local/my-bench/metadata.json` is a template.
Copying keeps paths relative and inside the gitignored `local/`. If the data is too large to copy, leave it
in place and use absolute paths in Step 6.

#### Step 6. Fill in `local/my-bench/metadata.json`

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

#### Step 7. Validate (gate)

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
error text and ask how to fix the data. Do not continue to Step 8 until validate exits 0.

#### Step 8. Split

```bash
.venv/bin/xferbench split --metadata local/my-bench/metadata.json --out local/my-bench/splits.json
```
Expected: per-stage counts and `split hash ...; N checks, 0 failed`, exit 0. Exit 1 = a leakage/cohort check
failed: STOP and show the failed checks to the user (usually the cohort windows need changing).
If the data or metadata change later, re-run Steps 7-8.

#### Step 9. Validation run

One run counter names every output of Steps 9-11. Start with `RUN=1`. **After any change in Steps 5-8, increment
`RUN` and redo Steps 9-11.** Outputs are append-only: each step refuses (exit 1, `already exists: use a new RUN`)
instead of silently reusing an old folder.

```bash
RUN=1
test ! -e runs/local/val-$RUN || { echo "already exists: runs/local/val-$RUN: use a new RUN"; false; } && \
.venv/bin/xferbench run --local-data local/my-bench/metadata.json \
  --splits local/my-bench/splits.json --stage validation --out runs/local/val-$RUN
```
Expected: a leaderboard, then `run validation-... status complete; data class local; tier complete; outputs in runs/local/val-1` (add `--tier sample` to `run` if your data is only a sample), exit 0.

#### Step 10. Select on validation, then score the frozen choice on test

```bash
test ! -e runs/local/selection-$RUN.json || { echo "already exists: runs/local/selection-$RUN.json: use a new RUN"; false; } && \
.venv/bin/xferbench select --validation-run runs/local/val-$RUN --out runs/local/selection-$RUN.json && \
{ test ! -e runs/local/test-$RUN || { echo "already exists: runs/local/test-$RUN: use a new RUN"; false; }; } && \
.venv/bin/xferbench run --local-data local/my-bench/metadata.json --splits local/my-bench/splits.json \
  --stage test --selection runs/local/selection-$RUN.json --out runs/local/test-$RUN
```
Expected: `selected on validation: ... wrote runs/local/selection-1.json`, then `run test-... status complete; data class local`, exit 0.
If it prints `already exists`, STOP: never reuse an older test run; increment `RUN` and redo Steps 9-11.

#### Step 11. Report

```bash
.venv/bin/xferbench report --run runs/local/test-$RUN --out runs/local/test-$RUN-report.html
git status --porcelain
```
Expected: `wrote runs/local/test-1-report.html`, exit 0; `git status --porcelain` prints nothing.
Tell the user to open `runs/local/test-$RUN-report.html` locally. It carries a LOCAL DATA banner and hashes item/FPG IDs.

#### Reading results (tell the user)

- PAIR0-E and PAIR0-N are scored separately; the overall order uses 0.5 x WMAPE(E) + 0.5 x WMAPE(N).
- WMAPE: lower is better. Bias: above 0 over-forecasts. Zero actuals show `N/A`, never a made-up number.
- Methods that need a missing extra, a recipe (M3) or that failed are listed with the reason.
- Exit codes: `0` ok, `1` data/split/config error, `2` bad usage, `3` requested method rejected, `4` partial run (time budget), `130` cancelled.

### Offline / enterprise

**Proxy and internal mirror** (Step 3 with network through a proxy):

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
/tmp/wh-venv/bin/python -m pip wheel -c constraints/core.txt -w local/wheelhouse .
```
Expected: exit 0; `local/wheelhouse/` (gitignored) holds `xfer_bench-<version>-py3-none-any.whl` plus every dependency
wheel. Copy the repo folder including `local/wheelhouse/` to the target, then on the target instead of Step 3:

```bash
.venv/bin/python -m pip install --no-index --find-links local/wheelhouse xfer-bench
.venv/bin/xferbench doctor --profile core
```
Expected: `profile 'core' satisfied`. This is a normal (non-editable) install; all later steps are the same.
No package index, network or telemetry is used after this.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `requires a different Python` / assert in Step 2 | Recreate `.venv` with Python 3.11+ |
| pip `ProxyError`, `SSLError`, timeouts | Set the proxy / mirror / `PIP_CERT` (Offline / enterprise), or use the wheelhouse |
| `No matching distribution` with `--no-index` | The package name is `xfer-bench` (the command is `xferbench`); otherwise the wheelhouse was built for another OS/arch/Python: rebuild it on a matching machine |
| `metadata invalid ... Extra inputs are not permitted` | Typo or unsupported key in `metadata.json` (the error names it, e.g. `time.frequncy`); compare with the `init` template |
| `[error] missing_column <table>.<col>` (lists the available columns) | Fix `tables.<table>.columns.<col>`, or STOP if the column does not exist in the data |
| `[error] file_not_found` | Fix `tables.<name>.path` (relative paths resolve from `metadata.json`) |
| `dataset_hash_mismatch` | Data changed; set `dataset.expected_hash` to `null` or to the new hash after the user confirms |
| `split` exits 1 | Cohort windows overlap, are empty, or lack 52 weeks of labels; STOP and agree new windows |
| "splits.json was built for different data" | Re-run Step 8 |
| "is not empty; choose a new --out" | Run folders are append-only; use a new `--out` |
| Exit 2 writing results | `--out` is inside the repo but not gitignored; use `runs/local/...` |
| "the test stage requires --selection" | Do Step 9 and the `select` part of Step 10 first |
| Exit 3 with `--methods M3` | M3 needs a recipe nobody has supplied; drop it |
| A method shows "missing extra" | Optional; e.g. `pip install -e ".[lightgbm]"` |

More detail: [`GETTING_STARTED.md`](GETTING_STARTED.md), [`METADATA.md`](METADATA.md), [`DATA_CLASSES.md`](DATA_CLASSES.md).
