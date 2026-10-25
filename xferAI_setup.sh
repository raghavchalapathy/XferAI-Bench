#!/usr/bin/env bash
# xferAI_setup.sh - one-command setup for XferAI-Bench (Linux, macOS, Git Bash on Windows).
# Run from the repository root:   bash xferAI_setup.sh        (bash xferAI_setup.sh --help for options)
# It only touches ./.venv, ./.xferai-setup.log, ./xb-demo and (if it installs uv) uv's own user folder.
# It never uses sudo and never changes system files or your shell profile.
# Exit codes: 0 ready, 1 a step failed (see the hint and the log), 2 usage error (bad flag).
set -Eeuo pipefail

SETUP_VERSION="1.0.0"
UV_VERSION="0.13.5"
UV_INSTALLER_URL="https://astral.sh/uv/${UV_VERSION}/install.sh"
# astral publishes no checksum for its installer scripts; this is the sha256 we observed on 2026-10-24.
UV_INSTALLER_SHA256_OBSERVED="1c6e7f025499664633ac2dce43a210800510e9ef0625c52e034a8afdf8bf177a"
TOTAL=7
LOG=".xferai-setup.log"
VENV=".venv"

PYTHON_REQ=""; INSTALL_UV=1; WITH_LGBM=0; WITH_SPARK=0; DEMO=1; QUIET=0; VERBOSE=0
NONINTERACTIVE=0; DRY_RUN=0; YES_OWN=0; STEP=0; STEP_NAME="start"

usage() {
  cat <<'USAGE'
Usage: bash xferAI_setup.sh [options]

Sets up XferAI-Bench in ./.venv: checks git and Python, gets uv if needed, installs the
package from uv.lock (or with pip as a fallback), runs `xferbench doctor` and a tiny offline demo.
No flags are required. Safe to run again.

Options:
  --python VERSION|PATH  Python to use (3.11 or newer), e.g. 3.13 or /usr/bin/python3.11
  --no-install-uv        Do not install uv; use python -m venv + pip if uv is missing
  --with-lightgbm        Also install the lightgbm extra
  --with-spark           Also install the distributed (Spark) extra
  --no-demo              Skip the offline demo
  --yes-own-data         Print the "your own data" instructions without asking
  --non-interactive      Never ask questions (also automatic when CI is set or stdin is not a terminal)
  --dry-run              Show what would be done, change nothing
  --quiet                Only print failures and the final summary
  --verbose              Also show the output of every command (always written to .xferai-setup.log)
  --version              Print the setup script version
  -h, --help             Show this help

Exit codes: 0 ready, 1 a step failed, 2 usage error.
Respects NO_COLOR, UV_* variables, PIP_INDEX_URL and HTTP(S)_PROXY / NO_PROXY.
USAGE
}

usage_error() { echo "xferAI_setup: $1" >&2; echo "Run 'bash xferAI_setup.sh --help' for the options." >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --version) echo "xferAI_setup.sh $SETUP_VERSION (uv $UV_VERSION)"; exit 0 ;;
    --python) [ $# -ge 2 ] && [ -n "$2" ] || usage_error "--python needs a value, e.g. --python 3.13"; PYTHON_REQ="$2"; shift ;;
    --python=*) PYTHON_REQ="${1#--python=}"; [ -n "$PYTHON_REQ" ] || usage_error "--python needs a value" ;;
    --no-install-uv) INSTALL_UV=0 ;;
    --with-lightgbm) WITH_LGBM=1 ;;
    --with-spark) WITH_SPARK=1 ;;
    --no-demo) DEMO=0 ;;
    --yes-own-data) YES_OWN=1 ;;
    --non-interactive) NONINTERACTIVE=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --quiet) QUIET=1 ;;
    --verbose) VERBOSE=1 ;;
    *) usage_error "unknown option '$1'" ;;
  esac
  shift
done
[ "$QUIET" = 1 ] && [ "$VERBOSE" = 1 ] && usage_error "--quiet and --verbose cannot be combined"

# ---- output helpers -------------------------------------------------------------------------------------------
UTF8=0
case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in *UTF-8*|*utf8*|*UTF8*|*utf-8*) UTF8=1 ;; esac
if [ "$UTF8" = 1 ]; then OK="✓"; BAD="✗"; else OK="[ok]"; BAD="[x]"; fi
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-}" != dumb ]; then
  G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[1m'; N=$'\033[0m'
else G=""; R=""; Y=""; B=""; N=""; fi

say() { [ "$QUIET" = 1 ] || printf '%s\n' "$*"; }
log() { printf '%s\n' "$*" >> "$LOG"; }
begin() { STEP=$((STEP + 1)); STEP_NAME="$1"; log "== [$STEP/$TOTAL] $1"; }
ok() { say "${G}[$STEP/$TOTAL] $OK${N} $STEP_NAME${1:+ - $1}"; log "ok: $STEP_NAME ${1:-}"; }
fail() {  # fail "what went wrong" "one-line fix"
  printf '%s\n' "${R}[$STEP/$TOTAL] $BAD $STEP_NAME: $1${N}" >&2
  printf '%s\n' "  Fix: $2" >&2
  printf '%s\n' "  Full log: $PWD/$LOG" >&2
  log "FAILED: $STEP_NAME: $1 | fix: $2"
  trap - ERR
  exit 1
}
# shellcheck disable=SC2329  # called by the ERR trap
on_err() {
  local rc=$? line=$1
  printf '%s\n' "${R}[$STEP/$TOTAL] $BAD $STEP_NAME: unexpected error (exit $rc, line $line)${N}" >&2
  printf '%s\n' "  Fix: read the log, fix the cause, then run 'bash xferAI_setup.sh' again (it is safe to re-run)." >&2
  printf '%s\n' "  Full log: $PWD/$LOG" >&2
  exit 1
}
trap 'on_err $LINENO' ERR
run() {  # run a command, output to the log (and screen with --verbose); returns its exit code
  log "\$ $*"
  if [ "$VERBOSE" = 1 ]; then "$@" 2>&1 | tee -a "$LOG"; return "${PIPESTATUS[0]}"
  else "$@" >> "$LOG" 2>&1; fi
}
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
  else return 1; fi
}

[ -f pyproject.toml ] && [ -f uv.lock ] || usage_error "run this from the XferAI-Bench folder (pyproject.toml and uv.lock not found here)"
: > "$LOG"
log "xferAI_setup.sh $SETUP_VERSION started $(date '+%Y-%m-%d %H:%M:%S %z')"

# ---- detect (no changes) --------------------------------------------------------------------------------------
OS="$(uname -s 2>/dev/null || echo unknown)"; ARCH="$(uname -m 2>/dev/null || echo unknown)"
case "$OS" in MINGW*|MSYS*|CYGWIN*) BIN="$VENV/Scripts" ;; *) BIN="$VENV/bin" ;; esac

find_python() {
  local c
  if [ -n "$PYTHON_REQ" ]; then
    case "$PYTHON_REQ" in */*|*\\*) c="$PYTHON_REQ" ;; [0-9]*) c="python$PYTHON_REQ" ;; *) c="$PYTHON_REQ" ;; esac
    command -v "$c" >/dev/null 2>&1 && { echo "$c"; return 0; }
    return 1
  fi
  for c in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      echo "$c"; return 0
    fi
  done
  return 1
}
PY="$(find_python || true)"
PYVER=""
if [ -n "$PY" ]; then PYVER="$("$PY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || true)"; fi
HAVE_UV=0; command -v uv >/dev/null 2>&1 && HAVE_UV=1
if [ "$HAVE_UV" = 1 ]; then MODE=uv; elif [ "$INSTALL_UV" = 1 ]; then MODE=uv-install; else MODE=pip; fi
EXTRAS="dev"; [ "$WITH_LGBM" = 1 ] && EXTRAS="$EXTRAS lightgbm"; [ "$WITH_SPARK" = 1 ] && EXTRAS="$EXTRAS distributed"
INTERACTIVE=1
if [ "$NONINTERACTIVE" = 1 ] || [ -n "${CI:-}" ] || [ ! -t 0 ]; then INTERACTIVE=0; fi
log "detected: os=$OS arch=$ARCH python=${PY:-none} ${PYVER} uv=$HAVE_UV mode=$MODE extras=$EXTRAS interactive=$INTERACTIVE"

say "${B}XferAI-Bench setup${N}: checks git and Python, gets uv if needed, installs into ./.venv, runs a health check and a tiny offline demo."
say "Measured on a Linux box with a fast connection: about 20 s with uv, 30 s with pip, 13 s when re-run (slower networks take longer)."
say "Detected: $OS $ARCH, Python ${PYVER:-not found}${PY:+ ($PY)}, uv $([ "$HAVE_UV" = 1 ] && uv --version 2>/dev/null | cut -d' ' -f2 || echo 'not found')"
say "Plan:"
case "$MODE" in
  uv) say "  - use uv: uv sync --locked$(for e in $EXTRAS; do printf ' --extra %s' "$e"; done)${PYTHON_REQ:+ --python $PYTHON_REQ} into $VENV" ;;
  uv-install) say "  - install uv $UV_VERSION for your user only (from $UV_INSTALLER_URL), then uv sync --locked$(for e in $EXTRAS; do printf ' --extra %s' "$e"; done)" ;;
  pip) say "  - no uv: python -m venv $VENV, then pip install -c constraints/core.txt -e .[$(echo "$EXTRAS" | tr -s ' ' ',')]" ;;
esac
say "  - run: xferbench doctor --profile core"
[ "$DEMO" = 1 ] && say "  - run: xferbench demo --preset tiny --out xb-demo (offline, synthetic)"
if [ "$DRY_RUN" = 1 ]; then say "Dry run: nothing was changed."; trap - ERR; exit 0; fi
say ""

# ---- 1. git ---------------------------------------------------------------------------------------------------
begin "Check git"
command -v git >/dev/null 2>&1 || fail "git was not found" "install git (https://git-scm.com/downloads), then run this again"
ok "$(git --version 2>/dev/null | cut -d' ' -f3)"

# ---- 2. Python ------------------------------------------------------------------------------------------------
begin "Check Python 3.11+"
if [ -n "$PY" ] && [ -n "$PYVER" ]; then
  "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
    || fail "$PY is $PYVER, but 3.11 or newer is needed" "install Python 3.11+ or pass --python /path/to/python3.11"
  ok "$PYVER ($PY)"
elif [ "$MODE" != pip ]; then
  ok "none found; uv will download a Python 3.11+ into its own folder"
else
  fail "no Python 3.11 or newer found${PYTHON_REQ:+ for --python $PYTHON_REQ}" "install Python 3.11+ (https://www.python.org/downloads/) or drop --no-install-uv so uv can provide one"
fi

# ---- 3. uv ----------------------------------------------------------------------------------------------------
begin "Get uv"
if [ "$MODE" = uv ]; then
  ok "already installed: $(uv --version)"
elif [ "$MODE" = pip ]; then
  ok "skipped (--no-install-uv); using pip instead"
else
  command -v curl >/dev/null 2>&1 || fail "curl is needed to download uv" "install curl, or run with --no-install-uv to use pip"
  TMP="$(mktemp "${TMPDIR:-/tmp}/uv-installer.XXXXXX")"
  say "  downloading the uv $UV_VERSION installer: $UV_INSTALLER_URL"
  run curl --proto '=https' --tlsv1.2 -fsSL "$UV_INSTALLER_URL" -o "$TMP" \
    || { rm -f "$TMP"; fail "could not download $UV_INSTALLER_URL" "check your connection or proxy (HTTPS_PROXY), or run with --no-install-uv"; }
  GOT="$(sha256_of "$TMP" || echo unknown)"
  WANT="${XFERAI_UV_INSTALLER_SHA256:-$UV_INSTALLER_SHA256_OBSERVED}"
  say "  installer sha256: $GOT"
  say "  expected:         $WANT (observed 2026-10-24; astral publishes no installer checksum)"
  [ -n "${XFERAI_UV_INSTALLER_SHA256:-}" ] && say "  ${Y}note: expected checksum overridden by XFERAI_UV_INSTALLER_SHA256${N}"
  if [ "$GOT" != "$WANT" ]; then
    rm -f "$TMP"
    fail "the downloaded installer does not match the expected sha256" "do not run it; install uv yourself (https://docs.astral.sh/uv/getting-started/installation/) or use --no-install-uv"
  fi
  UV_NO_MODIFY_PATH=1 run sh "$TMP" || { rm -f "$TMP"; fail "the uv installer failed" "see the log, or run with --no-install-uv to use pip"; }
  rm -f "$TMP"
  for d in "${UV_INSTALL_DIR:-}" "${XDG_BIN_HOME:-}" "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -n "$d" ] && [ -x "$d/uv" ]; then PATH="$d:$PATH"; export PATH; break; fi
  done
  command -v uv >/dev/null 2>&1 || fail "uv was installed but is not on PATH" "add ~/.local/bin to PATH, then run this again"
  ok "installed $(uv --version) (your shell profile was not changed; add ~/.local/bin to PATH to use uv later)"
  MODE=uv
fi

# ---- 4. venv --------------------------------------------------------------------------------------------------
begin "Create $VENV"
if [ -e "$VENV" ] && [ ! -f "$VENV/pyvenv.cfg" ]; then
  fail "$VENV exists but is not a virtual environment" "move or delete $VENV, then run this again"
fi
if [ -f "$VENV/pyvenv.cfg" ]; then
  ok "reusing the existing $VENV"
elif [ "$MODE" = uv ]; then
  run uv venv ${PYTHON_REQ:+--python "$PYTHON_REQ"} "$VENV" || fail "uv venv failed" "pass --python 3.11 (or newer), or see the log"
  ok "created with uv"
else
  run "$PY" -m venv "$VENV" || fail "python -m venv failed" "on Debian/Ubuntu install the python3-venv package, then run this again"
  ok "created with $PY"
fi

# ---- 5. install -----------------------------------------------------------------------------------------------
begin "Install XferAI-Bench (extras: $EXTRAS)"
if [ "$MODE" = uv ]; then
  EXOPT=(); for e in $EXTRAS; do EXOPT+=(--extra "$e"); done
  UV_PROJECT_ENVIRONMENT="$VENV" run uv sync --locked ${PYTHON_REQ:+--python "$PYTHON_REQ"} "${EXOPT[@]}" \
    || fail "uv sync --locked failed" "if uv.lock is out of date run 'uv lock', or see the log"
  ok "from uv.lock"
else
  SPEC=".[$(echo "$EXTRAS" | tr -s ' ' ',')]"
  run "$BIN/python" -m pip install -q --upgrade pip || fail "pip could not be upgraded" "check your connection or PIP_INDEX_URL, then run this again"
  run "$BIN/python" -m pip install -c constraints/core.txt -e "$SPEC" \
    || fail "pip install failed" "check your connection or PIP_INDEX_URL, or see the log"
  ok "with pip and constraints/core.txt"
fi

# ---- 6. doctor ------------------------------------------------------------------------------------------------
begin "Health check (xferbench doctor --profile core)"
run "$BIN/xferbench" doctor --profile core || fail "doctor reported a problem" "read the doctor output in the log; re-run this script to repair the install"
ok "profile core satisfied"

# ---- 7. demo --------------------------------------------------------------------------------------------------
begin "Offline demo (tiny synthetic data)"
if [ "$DEMO" = 1 ]; then
  rm -rf xb-demo  # our own output folder (git-ignored); recreated on every run so re-runs stay identical
  run "$BIN/xferbench" demo --preset tiny --out xb-demo || fail "the demo failed" "see the log; run 'bash xferAI_setup.sh --no-demo' to skip it"
  ok "open xb-demo/report.html"
else
  ok "skipped (--no-demo)"
fi

# ---- summary --------------------------------------------------------------------------------------------------
trap - ERR
if [ "$QUIET" = 1 ]; then echo "XferAI-Bench is ready in $VENV ($MODE, extras: $EXTRAS)."; exit 0; fi
say ""
say "${G}${B}Done.${N} Installed XferAI-Bench into $VENV with $MODE (extras: $EXTRAS); doctor passed."
[ "$DEMO" = 1 ] && say "The tiny demo report is at xb-demo/report.html. Setup log: $LOG"
say ""
cat setup/next_demo.txt
say ""
show_own() { echo; cat setup/own_data.txt; }
if [ "$YES_OWN" = 1 ]; then
  show_own
elif [ "$INTERACTIVE" = 1 ]; then
  printf 'Do you want to run on your own data? [y/N] '
  ANSWER=""; read -r ANSWER || ANSWER=""
  case "$ANSWER" in
    y|Y|yes|YES|Yes) show_own ;;
    *) echo "OK. Start with the demo above: docs/GETTING_STARTED.md Step 1, and experiments/README.md." ;;
  esac
else
  echo "(Not asking about your own data: non-interactive. Run with --yes-own-data, or see docs/GETTING_STARTED.md Step 2.)"
fi
exit 0
