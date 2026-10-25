#!/usr/bin/env bash
# Deprecated entry point kept for old instructions: a thin wrapper around xferAI_setup.sh (same flags, same
# exit codes: 0 ready, 1 a step failed, 2 usage error). Use `bash xferAI_setup.sh` directly.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"
exec bash "$here/xferAI_setup.sh" "$@"
