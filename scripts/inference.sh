#!/usr/bin/env bash
# Test-stage run with the frozen selection. Usage: scripts/inference.sh
set -euo pipefail
D=data/synthetic_data
xferbench run --metadata "$D/input/synthetic-tiny-42/metadata.json" --splits "$D/metadata/splits.json" --stage test \
  --selection "$D/metadata/selection.json" --out eval/test-run
