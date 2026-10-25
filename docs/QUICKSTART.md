# Quickstart

This walks through the complete offline demo, then each step separately so you can see what every file is.

## 1. Install (once)

Follow [GETTING_STARTED.md Step 0](GETTING_STARTED.md#step-0-install) (`bash xferAI_setup.sh`, or the pip fallback).
The commands below use `.venv/bin/xferbench`, which both routes create (Windows: `.venv\Scripts\xferbench`; with uv
you can also write `uv run xferbench`).

Expected `doctor` ending: `profile 'core' satisfied`.

## 2. Run the whole demo

```bash
.venv/bin/xferbench demo --preset tiny --out ./xb-demo
```

You will see seven numbered steps: generate, validate, split, validation run, freeze selection, test run,
report. The leaderboards printed for validation and test list WMAPE and Bias for each scenario and the
equal-scenario objective. Open `./xb-demo/report.html` in a browser.

## 3. What the report tells you

- **Dataset and scenario summary**: launches and eligible (measured) target weeks per scenario, hashes.
- **Frozen validation selection**: which variants were frozen before the first test origin and which was
  recommended. The test report never re-selects.
- **Top eligible methods**: ranked by `0.5 x WMAPE(PAIR0-E) + 0.5 x WMAPE(PAIR0-N)`, both scenarios shown.
- **Accuracy and Bias**, **Horizon slices** (weeks 1-4, 5-13, 14-26, 27-52) and category / region /
  intermittency / availability slices with sample counts.
- **Error versus resource use** (fit/predict seconds, Python peak memory).
- **Excluded, blocked and failed methods**: every registry entry with its implementation, execution and
  eligibility state and the exact reason and remedy.
- **Edge fixtures**: deliberately awkward launches (partial launch week, heavy stockouts, missing weeks,
  missing propensity, unseen category, unknown location attributes) kept off the ranked board.

## 4. The same pipeline, step by step

```bash
X=.venv/bin/xferbench
$X synth generate --preset tiny --format both --out ./work/data
$X validate --metadata ./work/data/metadata.json            # exit 1 on any error
$X validate --metadata ./work/data/metadata.csv.json        # same data, CSV files, same hash
$X split --metadata ./work/data/metadata.json --out ./work/splits.json
$X run --metadata ./work/data/metadata.json --splits ./work/splits.json --stage validation --out ./work/val
$X select --validation-run ./work/val --out ./work/selection.json
$X run --metadata ./work/data/metadata.json --splits ./work/splits.json --stage test \
       --selection ./work/selection.json --out ./work/test
$X report --run ./work/test --out ./work/report.html
$X compare --runs ./work/val --runs ./work/val-rerun --out ./work/compare.html   # refuses mismatched runs
```

Each run directory contains:

| File | Content |
|---|---|
| `run_manifest.json` | software, data, split, population and policy hashes; origins; variants; resources |
| `forecasts.parquet` | 52 rows per request per variant: `point_units`, `status`, `reason` |
| `metrics.json`, `leaderboard.csv`, `slices.csv` | per-scenario metrics, ranks, slices |
| `failures.csv` | failed and fallback rows grouped by reason |
| `method_support.json` | every registry entry and why it did or did not run |
| `resources.json`, `data_quality.json` | timings/memory; validation issues and zero-fraction profile |
| `report.html`, `summary.md` | self-contained report and a short Markdown summary |

Run directories are append-only: re-using a non-empty `--out` is refused.

## Exit codes

`0` complete, `1` error (data, split or configuration), `2` bad command-line usage, `3` an explicitly
requested method was rejected or unknown (nothing is substituted), `4` partial run (budget stop), `130` cancelled.
