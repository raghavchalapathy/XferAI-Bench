#!/usr/bin/env bash
# Regenerate constraints/core.txt and constraints/extras.txt (pip fallback pins) from uv.lock so pip and uv install
# the same versions. extras.txt holds only the extra packages of the lightgbm and distributed extras (not in core.txt).
# Run after `uv lock`; tests/unit/test_constraints_lock.py fails if the two drift.
# constraints/minimum.txt is NOT generated: it pins the declared lower bounds from pyproject.toml (CI lower-bound check),
# which by design differ from the lock.
set -euo pipefail
cd "$(dirname "$0")/.."
uv lock --check
{
  echo "# GENERATED from uv.lock by scripts/export_constraints.sh -- do not edit by hand. Core dependencies only"
  echo "# (no extras, no dev tools). Use with: pip install -c constraints/core.txt -e \".[dev]\""
  uv export --frozen --no-hashes --no-emit-project --no-dev --no-header --no-annotate --format requirements-txt
} > constraints/core.txt
echo "wrote constraints/core.txt ($(grep -vc '^#' constraints/core.txt) pins)"
{
  echo "# GENERATED from uv.lock by scripts/export_constraints.sh -- do not edit by hand. Packages added by the"
  echo "# lightgbm and distributed extras, beyond constraints/core.txt. Use with:"
  echo "#   pip install -c constraints/core.txt -c constraints/extras.txt -e \".[dev,lightgbm]\""
  uv export --frozen --no-hashes --no-emit-project --no-dev --no-header --no-annotate --format requirements-txt \
    --extra lightgbm --extra distributed | grep -vxF -f <(grep -v '^#' constraints/core.txt)
} > constraints/extras.txt
echo "wrote constraints/extras.txt ($(grep -vc '^#' constraints/extras.txt) pins)"
