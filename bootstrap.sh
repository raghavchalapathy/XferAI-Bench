#!/usr/bin/env bash
# Create a project-local virtual environment, install xfer-bench into it and run `xferbench doctor`.
#
#   bash bootstrap.sh                       # install this checkout (editable, with dev tools)
#   bash bootstrap.sh dist/xfer_bench-0.1.0-py3-none-any.whl   # install a built wheel
#
# Environment: PYTHON=python3.11 to choose the interpreter, VENV=.venv to choose the folder.
# Never uses sudo, never installs globally, never overwrites an existing environment.
set -euo pipefail

PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv}"
TARGET="${1:-}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: '$PYTHON' not found. Install Python 3.11+ (https://www.python.org/downloads/) and retry," >&2
  echo "       or set PYTHON=/path/to/python3.11" >&2
  exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "error: $("$PYTHON" --version 2>&1) is too old; xfer-bench needs Python 3.11 or newer." >&2
  exit 1
fi
if [ -e "$VENV" ]; then
  echo "error: '$VENV' already exists; refusing to modify it. Remove it yourself or set VENV=<new folder>." >&2
  exit 1
fi

"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
if [ -z "$TARGET" ]; then
  "$VENV/bin/python" -m pip install -e ".[dev]"
else
  "$VENV/bin/python" -m pip install "$TARGET"
fi
"$VENV/bin/xferbench" doctor --profile core
echo
echo "ready. Try: $VENV/bin/xferbench demo --preset tiny --out ./xb-demo"
