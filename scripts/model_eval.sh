#!/usr/bin/env bash
# Run one experiment end to end (synthetic) into experiments/<id>/runs/<timestamp>/.
# Usage: scripts/model_eval.sh exp01_synthetic_lightgbm_analogs   (or: scripts/model_eval.sh --all)
set -euo pipefail
E="${1:-exp01_synthetic_lightgbm_analogs}"
if [ "$E" = "--all" ]; then xferbench experiment run-all; else xferbench experiment run "$E"; fi
