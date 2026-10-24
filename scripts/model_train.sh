#!/usr/bin/env bash
# Validation-stage run (fit and forecast) then frozen selection. Usage: scripts/model_train.sh [methods]
set -euo pipefail
D=data/synthetic_data/input/synthetic-tiny-42
xferbench split --metadata "$D/metadata.json" --out data/synthetic_data/metadata/splits.json
xferbench run --metadata "$D/metadata.json" --splits data/synthetic_data/metadata/splits.json \
  --stage validation --out eval/validation-run ${1:+--methods "$1"}
xferbench select --validation-run eval/validation-run --out data/synthetic_data/metadata/selection.json
