#!/usr/bin/env bash
# Run an experiment end to end (synthetic). Usage: scripts/model_eval.sh exp01_m5_lightgbm_analogs
set -euo pipefail
E="${1:-exp01_m5_lightgbm_analogs}"
xferbench experiment --config "experiments/$E/config.yaml" --out "eval/$E"
