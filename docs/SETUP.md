# Setup, compatibility and troubleshooting

## Requirements

- Python **3.11 or newer** and Git. CPU only; no GPU, CUDA, service account or model download is needed.
- About 300 MB of RAM (measured process max RSS) and 10-30 seconds for the tiny demo.

If Python 3.11+ is missing: install it from <https://www.python.org/downloads/> (macOS/Windows installer), or
`brew install python@3.11` on macOS with Homebrew, or your Linux distribution's `python3.11` and
`python3.11-venv` packages. You never need `sudo pip` or a global install; everything goes into a
project-local `.venv`.

## Install options

| Goal | Command (macOS/Linux) |
|---|---|
| Develop from this checkout | `python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"` |
| Same, scripted | `bash bootstrap.sh` (refuses to touch an existing `.venv`) |
| Install a built wheel | `python3 -m venv /path/env && /path/env/bin/python -m pip install dist/xfer_bench-0.1.0-py3-none-any.whl` |
| Reproduce the tested pins | add `-c constraints/core.txt` to the pip command |

Windows uses `.venv\Scripts\python` and `bootstrap.ps1`. The package is not on PyPI.

## Optional extras

Declared in `pyproject.toml` for later milestones: `boosting`, `neural`, `foundation`, `intermittent`,
`services`, `distributed`. **None is tested or used by Milestone A**, and installing one does not make any
method run: the matching adapters are still unimplemented. `xferbench doctor --profile <extra>` reports
which modules are present without installing anything. Foundation-model weights are never downloaded
automatically; when those adapters land, weights must be prepared explicitly and their licences recorded.
Service adapters will be opt-in only (`privacy.service_calls`), never on by default.

## Tested compatibility matrix

| OS / arch | Python | Core dependency versions | What was run | Result |
|---|---|---|---|---|
| macOS 26.2, arm64 | 3.11.5 | `constraints/core.txt` (numpy 2.4.6, pandas 3.0.6, pyarrow 26.0.0) | lint, mypy, 75 tests, build, wheel install outside checkout, `--help`, `doctor`, `validate`, tiny demo | pass |
| macOS 26.2, arm64 | 3.13.0 | numpy 2.5.4, pandas 3.0.6, pyarrow 26.0.0 | wheel install outside checkout, tiny demo, 75 tests from the sdist against the installed wheel | pass |
| macOS 26.2, arm64 | 3.11.5 | `constraints/minimum.txt` (numpy 1.26.4, pandas 2.2.0, pyarrow 15.0.0, pydantic 2.6.4, typer 0.16.0) | 75 tests against the installed package | pass |
| Linux, Windows | 3.11, 3.13 | - | CI workflow prepared (`.github/workflows/ci.yml`), not yet run | untested |
| any | 3.12 | - | not installed on the build machine | untested |

Only the rows marked pass are supported claims.

## Constraints strategy

`pyproject.toml` declares compatible ranges (lower bounds tested in `constraints/minimum.txt`).
`constraints/core.txt` records the exact versions of the latest full verification. Use it for reproducible
benchmark runs: the run manifest records the actual package versions either way.

## Scale and resources

Presets, measured end-to-end with `xferbench demo` on the build machine (Apple silicon laptop): `tiny`
about 10 s and 0.3 GB max RSS; `small` about 58 s and 1.2 GB. `stress` is large, explicit only, and has
**not** been run yet (bounded stress testing is Milestone D). Runs accept
`--max-seconds`; when the budget is hit, unfinished requests are marked `skipped`, the run is `partial`
(exit code 4) and nothing is ranked. Each run records fit/predict seconds, the Python allocation peak per
variant (tracemalloc) and the process max RSS.

## Reproducibility

Synthetic data is deterministic per preset and seed (identical content hash on regeneration and between
CSV and Parquet). Runs record data, split, population, policy and software hashes and package versions.
Run directories are append-only.

## Privacy and security

- No network access, telemetry or model download on import or in the default demo (tests block sockets).
- Metadata is declarative; no code from metadata or plugins runs unless the plugin's entry-point name is in
  `XFERBENCH_TRUSTED_PLUGINS`.
- Reports escape all labels, embed everything inline (no CDN), set a restrictive Content-Security-Policy
  and show no raw data rows.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `requires a different Python: 3.10...` | create the venv with Python 3.11+ (`python3.11 -m venv .venv`) |
| `TypeError: Parameter.make_metavar() missing ... 'ctx'` | Typer older than 0.16 with Click 8.2+; `pip install "typer>=0.16"` |
| `output directory ... is not empty; runs are append-only` | choose a new `--out` |
| `dataset_hash_mismatch` | data changed after metadata was written; review, then update `dataset.expected_hash` |
| `splits.json was built for different data` | rerun `xferbench split` after changing data |
| `the test stage requires --selection` | run validation, then `xferbench select`, then the test stage |
| exit code 3 with `--methods M3` | M3 is `config_required`; supply its recipe (Milestone C) or drop it |
| `NOT SCOREABLE` from the wizard | the stage contains launches without 52 reported weeks; move its window earlier |
