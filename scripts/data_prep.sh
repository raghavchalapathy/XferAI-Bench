#!/usr/bin/env bash
# Generate synthetic data and validate it. Usage: scripts/data_prep.sh [preset] [seed]
set -euo pipefail
OUT=data/synthetic_data/input/synthetic-${1:-tiny}-${2:-42}
xferbench synth generate --preset "${1:-tiny}" --seed "${2:-42}" --out "$OUT"
xferbench validate --metadata "$OUT/metadata.json"
