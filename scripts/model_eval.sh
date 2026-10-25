#!/usr/bin/env bash
# Run one experiment end to end (synthetic) into eval/<id>__<tier>/ (tier from the config, default synthetic).
# Extra args are passed through, e.g. --tier sample.
# Usage: scripts/model_eval.sh exp01_synthetic_lightgbm_analogs   (or: scripts/model_eval.sh --all)
set -euo pipefail
E="${1:-exp01_synthetic_lightgbm_analogs}"
if [ "$E" = "--all" ]; then xferbench experiment run-all; else shift || true; xferbench experiment run "$E" "$@"; fi
