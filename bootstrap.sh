#!/usr/bin/env bash
# Create or update a project-local environment, install xfer-bench into it and run `xferbench doctor`.
# Uses uv (https://docs.astral.sh/uv/) with the committed uv.lock when uv is on PATH; otherwise falls back to
# `python -m venv` + pip with constraints/core.txt (generated from uv.lock). Safe to re-run: an existing
# environment is updated in place, never deleted.
#
#   bash bootstrap.sh                       # this checkout (editable, with dev tools)
#   bash bootstrap.sh dist/xfer_bench-0.1.0-py3-none-any.whl   # a built wheel
#
# Environment:
#   PYTHON=python3.11     interpreter (pip path; with uv it is passed as --python)
#   VENV=.venv            environment folder
#   EXTRAS="dev lightgbm" extras for this checkout (default: dev; e.g. add lightgbm or distributed)
#   XFERBENCH_NO_UV=1     force the pip fallback even if uv is installed
# Exit codes: 0 ready, 1 no suitable Python, 2 bad usage (VENV exists but is not a virtual environment,
#             target missing), 3 install failed, 4 installed but `xferbench doctor` failed.
# Never uses sudo and never installs globally.
set -uo pipefail

PYTHON_SET="${PYTHON+x}"
PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv}"
EXTRAS="${EXTRAS:-dev}"
TARGET="${1:-}"

say() { echo "bootstrap: $*"; }
die() { echo "bootstrap: error: $2" >&2; exit "$1"; }

if [ -n "$TARGET" ] && [ ! -e "$TARGET" ]; then die 2 "'$TARGET' not found (pass a wheel/sdist path or nothing)."; fi
if [ -z "$TARGET" ] && [ ! -f pyproject.toml ]; then die 2 "run this from the repository root (pyproject.toml not found)."; fi
if [ -e "$VENV" ] && [ ! -f "$VENV/pyvenv.cfg" ]; then
  die 2 "'$VENV' exists but is not a virtual environment; refusing to touch it. Remove it or set VENV=<new folder>."
fi

USE_UV=0
if [ -z "${XFERBENCH_NO_UV:-}" ] && command -v uv >/dev/null 2>&1; then USE_UV=1; fi

if [ "$USE_UV" = 1 ]; then
  say "using $(uv --version) (uv.lock); set XFERBENCH_NO_UV=1 to use pip instead"
  export UV_PROJECT_ENVIRONMENT="$VENV"
  PYOPT=()
  if [ -n "$PYTHON_SET" ]; then PYOPT=(--python "$PYTHON"); fi
  if [ -z "$TARGET" ]; then
    EXOPT=()
    for e in $EXTRAS; do EXOPT+=(--extra "$e"); done
    uv sync --locked ${PYOPT[@]+"${PYOPT[@]}"} ${EXOPT[@]+"${EXOPT[@]}"} || die 3 "uv sync failed (if uv.lock is out of date: uv lock, then retry)."
  else
    if [ ! -e "$VENV" ]; then uv venv ${PYOPT[@]+"${PYOPT[@]}"} "$VENV" || die 3 "uv venv failed."; fi
    uv pip install --python "$VENV/bin/python" "$TARGET" || die 3 "uv pip install $TARGET failed."
  fi
else
  if [ -n "${XFERBENCH_NO_UV:-}" ]; then say "XFERBENCH_NO_UV set; using python -m venv + pip"
  else say "uv not found; using python -m venv + pip (install uv for the locked, faster path)"; fi
  if ! command -v "$PYTHON" >/dev/null 2>&1; then
    die 1 "'$PYTHON' not found. Install Python 3.11+ (https://www.python.org/downloads/) or set PYTHON=/path/to/python3.11."
  fi
  if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    die 1 "$("$PYTHON" --version 2>&1) is too old; xfer-bench needs Python 3.11 or newer."
  fi
  if [ -e "$VENV" ]; then say "updating existing $VENV"; else "$PYTHON" -m venv "$VENV" || die 3 "python -m venv failed."; fi
  "$VENV/bin/python" -m pip install -q --upgrade pip || die 3 "pip upgrade failed."
  if [ -z "$TARGET" ]; then
    SPEC=".[$(echo "$EXTRAS" | tr -s ' ' ',')]"
    "$VENV/bin/python" -m pip install -c constraints/core.txt -e "$SPEC" || die 3 "pip install -e '$SPEC' failed."
  else
    "$VENV/bin/python" -m pip install "$TARGET" || die 3 "pip install $TARGET failed."
  fi
fi

"$VENV/bin/xferbench" doctor --profile core || die 4 "installed, but 'xferbench doctor --profile core' reported a problem (see above)."
echo
if [ "$USE_UV" = 1 ] && [ -z "$TARGET" ] && [ "$VENV" = .venv ]; then say "ready. Try: uv run xferbench demo --preset tiny --out ./xb-demo"
else say "ready. Try: $VENV/bin/xferbench demo --preset tiny --out ./xb-demo"; fi
