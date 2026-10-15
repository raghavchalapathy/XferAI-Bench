# Xfer Benchmark (`xfer-bench`)

Xfer Benchmark is a local, CPU-first Python package for testing forecasting methods on **cold item-location
pairs**. It answers one question fairly: for an existing retail item launching at a fulfilment point group (FPG)
where that pair has **zero own-pair sales history**, which methods give the best 52-week weekly unit forecasts
on your own completed historical launches?

Two scenarios are always scored and shown separately, with equal 0.5/0.5 selection weight:

- **PAIR0-E**: existing item at an *established* FPG (other items already sell there).
- **PAIR0-N**: existing item at an *entirely new* FPG (no transactions there before the origin).

The package ships deterministic synthetic retail data so the whole pipeline runs offline. **Synthetic results
demonstrate software behaviour only; they say nothing about real-world model superiority.**

> Status: **Milestone A** (vertical slice). Core baselines B0, B1, B2 (+ raw-unit ablation), business rules
> M1 and M2, the evaluator, frozen validation selection and the HTML report are implemented and tested.
> Boosting, neural, foundation and service adapters are registered with explicit reasons but **not implemented
> yet**; they never receive scores. See [METHOD_SUPPORT.md](METHOD_SUPPORT.md) and [PROGRESS.md](PROGRESS.md).
> The package is not published on PyPI; install it from this checkout or a locally built wheel.

## Quickstart (macOS / Linux)

Needs Python 3.11 or newer (tested on 3.11 and 3.13) and Git. From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/xferbench doctor --profile core
.venv/bin/xferbench demo --preset tiny --out ./xb-demo
open ./xb-demo/report.html        # Linux: xdg-open ./xb-demo/report.html
```

Windows (PowerShell; these commands are prepared for CI but have **not yet been run on Windows**):

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\xferbench demo --preset tiny --out .\xb-demo
start .\xb-demo\report.html
```

The tiny demo takes about 10 seconds on a laptop CPU and makes no network calls. It writes:

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

## Installing from a built wheel

```bash
.venv/bin/python -m build                      # writes dist/xfer_bench-0.1.0-py3-none-any.whl and .tar.gz
python3 -m venv /tmp/xb-env
/tmp/xb-env/bin/python -m pip install dist/xfer_bench-0.1.0-py3-none-any.whl
/tmp/xb-env/bin/xferbench demo --out /tmp/xb-wheel-demo
```

`bootstrap.sh` / `bootstrap.ps1` do the same into a new local `.venv` (they refuse to overwrite an existing one).

## Documentation

| Topic | File |
|---|---|
| Beginner quickstart and expected outputs | [docs/QUICKSTART.md](docs/QUICKSTART.md) |
| Metadata and column mapping | [docs/METADATA.md](docs/METADATA.md) |
| Replacing synthetic data with your own | [docs/REAL_DATA.md](docs/REAL_DATA.md) |
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

## License

Apache-2.0 for the code in this repository ([LICENSE](LICENSE)). Third-party code, model weights, datasets and
services have their own terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[METHOD_SUPPORT.md](METHOD_SUPPORT.md).
