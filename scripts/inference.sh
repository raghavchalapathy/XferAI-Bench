#!/usr/bin/env bash
# Production-style inference: fit the frozen selected variant once, then forecast new launches.
# No actuals are read and the evaluator is never called. Usage: scripts/inference.sh [METHOD]
# Exit codes: 0 ok, 1 error, 2 usage, 5 artifact mismatch, 6 schema mismatch (see docs in README).
set -euo pipefail
D=data/synthetic_data
M="${1:-B3}"
MODEL=eval/models/$M
xferbench fit --metadata "$D/input/synthetic-tiny-42/metadata.json" --splits "$D/metadata/splits.json" \
  --method "$M" --selection "$D/metadata/selection.json" --stage test --out "$MODEL"
xferbench forecast --model "$MODEL" --metadata "$D/input/synthetic-tiny-42/metadata.json" \
  --splits "$D/metadata/splits.json" --stage test --out "eval/forecast-$M.parquet"
