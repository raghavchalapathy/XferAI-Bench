# Xfer Benchmark (`xfer-bench`)

[![ci](https://github.com/raghavchalapathy/XferAI-Bench/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/raghavchalapathy/XferAI-Bench/actions/workflows/ci.yml)
![Python 3.11 | 3.13](https://img.shields.io/badge/python-3.11%20%7C%203.13-blue)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

Xfer Benchmark is a local, CPU-first Python package for testing forecasting methods on **cold item-location
pairs**: an existing retail item launches at a Forecast Pixel Group (FPG) where that pair has **zero own-pair
sales history**, and each method produces 52 weekly unit forecasts, evaluated on your own completed historical
launches.

Two scenarios are always scored and shown separately, with equal 0.5/0.5 selection weight:

- **PAIR0-E**: existing item at an *established* FPG (other items already sell there).
- **PAIR0-N**: existing item at an *entirely new* FPG (no transactions there before the origin).

> **Status.** No rights-cleared real benchmark has been run, so **benchmark rankings are pending**. The bundled
> data is synthetic: it tests that the software works, not which method is better. Nothing here claims that any
> method forecasts well from day zero. The package is not on PyPI; install it from a clone or a locally built wheel.

**Website:** [xferai.app](https://xferai.app): [Benchmark](https://xferai.app/benchmark/) ·
[News & Research](https://xferai.app/news/) · [Getting started](https://xferai.app/getting-started/) ·
[Offers | Services](https://xferai.app/services/).

**Run on your own data, locally:** [docs/DIY-GettingStarted.md](docs/DIY-GettingStarted.md).

**Scope.** Cold-start time-series forecasting (zero or near-zero own history). Foundation-model and zero-shot
approaches (e.g. TimesFM, Chronos, Moirai) are tracked; see the method table below for what actually runs.
Licence: Apache-2.0 ([LICENSE](LICENSE)). Contributor and site rules: [docs/SITE_AND_HARNESS.md](docs/SITE_AND_HARNESS.md).

## Quickstart (macOS / Linux)

- New here? Follow **[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)**: install, demo, then your own data.
- Using a coding assistant (Claude Code, Cursor, Copilot, ChatGPT)? Point it at
  **[docs/DIY-GettingStarted.md](docs/DIY-GettingStarted.md)** (also [AGENTS.md](AGENTS.md), [llms.txt](llms.txt)).
  It covers offline/enterprise installs and keeps your data on your machine.

Needs Python 3.11 or newer and Git:

```bash
git clone https://github.com/raghavchalapathy/XferAI-Bench.git && cd XferAI-Bench
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/xferbench doctor --profile core   # -> profile 'core' satisfied
.venv/bin/xferbench demo --out ./xb-demo     # about 20 s, no network
open ./xb-demo/report.html                  # Linux: xdg-open ./xb-demo/report.html
```

Windows (PowerShell). CI runs the test suite and the wheel demo on `windows-latest`; these interactive commands
themselves are untested:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\xferbench demo --preset tiny --out .\xb-demo
start .\xb-demo\report.html
```

The demo writes:

```text
xb-demo/
  data/                    synthetic tables (Parquet + CSV), metadata.json, metadata.csv.json,
                           DATA_STORY.md, FIELD_DICTIONARY.md, generation_report.json
  data/_synthetic_truth/   hidden generator truth (never read by any method)
  splits.json              frozen chronological cohorts + leakage checks + hash
  selection-policy.json    preregistered selection rule
  validation-run/          validation forecasts, metrics, leaderboard, report
  selection.json           selection frozen from validation only
  test-run/                test forecasts/metrics for the frozen variants only
  report.html              self-contained report for the test run
```

## Methods

From the method registry (`xferbench list-methods --all`; full table with reasons in
[METHOD_SUPPORT.md](METHOD_SUPPORT.md)). There are no rankings here: scores exist only for runs on your data.

| Method | What it is | State | Dependency licence | Weights | Status |
|---|---|---|---|---|---|
| `B0` | National flat rate x households | implemented | Apache-2.0 | none | core baseline |
| `B1` | B0 x seasonal profile | implemented | Apache-2.0 | none | core baseline |
| `B2` | Target households x similar-FPG per-household rate (no shrinkage) | implemented | Apache-2.0 | none | core baseline |
| `B3` | B2 shrunk toward the national rate (extra row) | implemented | Apache-2.0 | none | core baseline |
| `M1` | Business rule H x P | implemented | Apache-2.0 | none | core (needs a propensity feature) |
| `M2` | Business rule H x P x S | implemented | Apache-2.0 | none | core (needs a propensity feature) |
| `M3` | Your ramp/blend/calibration rule | config_required | Apache-2.0 | none | needs a recipe; never substituted |
| `M4.lightgbm` | Global LightGBM (Poisson) | implemented | MIT | none | optional extra `lightgbm` |
| `FM.chronos2` | Chronos-2 donor prior x households | experimental | Apache-2.0 | Apache-2.0 | licence-pinned; not Reviewer-recommended for PAIR0; extra `foundation` |
| `FM.chronos_bolt` | Chronos-Bolt donor prior x households | experimental | Apache-2.0 | Apache-2.0 | same as above |
| `FM.timesfm25` | TimesFM 2.5 donor prior x households | experimental | Apache-2.0 | Apache-2.0 | same as above; extra `timesfm` |
| `M6.deepar_count` | GluonTS DeepAR (negative binomial) donor prior | experimental | Apache-2.0 | none | same as above; extra `neural` |
| `FM.moirai2`, `FM.tabpfn_ts`, `FM.timesfm3` | foundation adapters | unimplemented | Apache-2.0 | non-commercial | research-only, opt-in (`--allow-research-only`); never in default profiles |
| `EXT.pop` | POP external adapter | unimplemented | CC-BY-NC-SA-4.0 | none | rejected by the Reviewer (leakage); not admitted |
| others (`M4.xgboost`, `M4.catboost`, `M5`-`M9`, `E1`, `REF.*`) | planned | unimplemented | various | none | registered with reasons; never scored |

"Experimental" adapters are tested only with fake backends here; their real backends need optional extras.

## Step-by-step commands

```bash
xferbench synth generate --preset tiny --format both --out ./work/data
xferbench validate --metadata ./work/data/metadata.json
xferbench split    --metadata ./work/data/metadata.json --out ./work/splits.json
xferbench run      --metadata ./work/data/metadata.json --splits ./work/splits.json \
                   --stage validation --out ./work/validation-run
xferbench select   --validation-run ./work/validation-run --out ./work/selection.json
xferbench run      --metadata ./work/data/metadata.json --splits ./work/splits.json \
                   --stage test --selection ./work/selection.json --out ./work/test-run
xferbench report   --run ./work/test-run --out ./work/report.html
xferbench list-methods --all
```

### Methods in order, and your own data

```bash
xferbench steps --benchmark synthetic-tiny@1.1.0 --out ./xb-steps          # shared benchmark data (hashed)
xferbench steps --local-data /path/to/my/metadata.json --out ~/xb-local-1  # your own data, labeled local
```

`steps` runs B0, B1, B2, B3 (extra row), M1, M2, M3 (listed as needing a recipe) and M4.lightgbm (if the `boosting`
extra is installed), each adding one idea, and reports WMAPE and Bias for PAIR0-E and PAIR0-N separately.
Benchmark data and local data are kept apart; see [docs/DATA_CLASSES.md](docs/DATA_CLASSES.md).

## Installing from a built wheel

```bash
.venv/bin/python -m build                      # writes dist/xfer_bench-0.1.0-py3-none-any.whl and .tar.gz
python3 -m venv /tmp/xb-env
/tmp/xb-env/bin/python -m pip install dist/xfer_bench-0.1.0-py3-none-any.whl
/tmp/xb-env/bin/xferbench demo --out /tmp/xb-wheel-demo
```

`bootstrap.sh` / `bootstrap.ps1` do the same into a new local `.venv` (they refuse to overwrite an existing one).

## Repository layout and experiments

`configs/` (YAML per data flavour), `data/` (contents gitignored), [data_preparation/](data_preparation/README.md), [models/](models/README.md), [harness/](harness/README.md), `scripts/` (runbooks: data_prep, data_cleaning, model_train, model_eval, inference), [experiments/](experiments/README.md), `eval/`, `results/`. The code lives in `src/xferbench`.

```bash
xferbench experiment --config experiments/exp01_m5_lightgbm_analogs/config.yaml --out eval/exp01
```

Experiments use synthetic data only. **Synthetic interface test, not rankings.**

## Documentation

| Topic | File |
|---|---|
| Getting started, end to end with your own data | [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) |
| Beginner quickstart and expected outputs | [docs/QUICKSTART.md](docs/QUICKSTART.md) |
| Metadata and column mapping | [docs/METADATA.md](docs/METADATA.md) |
| Replacing synthetic data with your own | [docs/REAL_DATA.md](docs/REAL_DATA.md) |
| Benchmark data vs local data | [docs/DATA_CLASSES.md](docs/DATA_CLASSES.md) |
| Methods, compatibility and licensing | [docs/METHODS.md](docs/METHODS.md), [METHOD_SUPPORT.md](METHOD_SUPPORT.md) |
| Metrics, splits, leakage rules, selection | [docs/EVALUATION.md](docs/EVALUATION.md) |
| Adding a model or an industry plugin | [docs/EXTENDING.md](docs/EXTENDING.md) |
| Installation, extras, OS matrix, troubleshooting, privacy | [docs/SETUP.md](docs/SETUP.md) |
| Synthetic data story | [examples/retail_synthetic/DATA_STORY.md](examples/retail_synthetic/DATA_STORY.md) |
| Contributing and releases | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Guarantees

- Methods only see an origin-scoped context: rows whose week ended and whose `known_at` is on or before the
  origin, attribute versions effective and known by then, and never any row of a held-out pair or a held-out
  new FPG of the evaluated stage.
- Every request gets exactly 52 forecast rows. Failures are null with a reason; they are never dropped and
  never zero-filled. A method with less than 100% coverage is unrankable.
- WMAPE and Bias are undefined (JSON `null` plus reason, `N/A` in reports) when the actual total is zero.
- The test stage scores only variants frozen from validation; split, data and policy hashes are checked.
- No network, telemetry or model download on import or in the default demo. Metadata is declarative; no code
  or expressions from metadata are executed.

## Contributing

Bug reports, onboarding problems and method proposals are welcome as GitHub issues. Before a pull request:

```bash
.venv/bin/python -m pip install -c constraints/core.txt -e ".[dev]"
.venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests
.venv/bin/python -m mypy && .venv/bin/python -m pytest
```

Ground rules (no fake scores, no leakage, no silent substitution, no network, declarative metadata) and how to
add a method are in [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/EXTENDING.md](docs/EXTENDING.md). New methods
need honest licence metadata and leakage tests, and go through review before they are listed as implemented.

## License

Apache-2.0 for the code in this repository ([LICENSE](LICENSE)). Third-party code, model weights, datasets and
services have their own terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[METHOD_SUPPORT.md](METHOD_SUPPORT.md).
