#!/usr/bin/env bash
# Ingest VISUELLE from the OFFICIAL source only, after explicit interactive licence acceptance.
# The official source is a request form (linked from https://github.com/HumaticsLAB/GTM-Transformer README):
#   https://forms.gle/cVGQAmxhHf7eRJ937
# There is no direct download URL, so you download the archive yourself through that form and pass it with
# --archive. This script never fetches anything from elsewhere and only writes into a git-ignored data/ folder.
# Exit codes: 0 ok, 2 usage, 3 licence not accepted, 4 unsafe destination (tracked / not git-ignored).
set -euo pipefail
OFFICIAL_SOURCE="https://forms.gle/cVGQAmxhHf7eRJ937"
PHRASE="I ACCEPT THE VISUELLE TERMS"
ARCHIVE=""; DEST="data/visuelle/input/raw"
while [ $# -gt 0 ]; do
  case "$1" in
    --archive) ARCHIVE="${2:-}"; shift 2 ;;
    --dest) DEST="${2:-}"; shift 2 ;;
    -h|--help) sed -n 2,8p "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
case "$DEST" in
  data/*/input/*|data/*/input) ;;
  *) echo "refusing: --dest must be under data/<flavour>/input/ (got $DEST)" >&2; exit 4 ;;
esac
case "$DEST" in *..*) echo "refusing: '..' in --dest" >&2; exit 4 ;; esac
if ! git check-ignore -q "$DEST/probe.csv" 2>/dev/null; then
  echo "refusing: $DEST is not git-ignored; data must never be committed" >&2; exit 4
fi
if [ -n "$(git ls-files -- "$DEST" 2>/dev/null)" ]; then
  echo "refusing: $DEST contains tracked files" >&2; exit 4
fi
echo "VISUELLE official source: $OFFICIAL_SOURCE"
echo "Licence status recorded by XferAI-Bench (2026-10-24): NO LICENCE TEXT FOUND. Read the terms given by the"
echo "official source yourself. Research use only. Type exactly: $PHRASE"
if [ ! -t 0 ]; then
  echo "refusing: licence acceptance must be interactive (stdin is not a terminal)" >&2; exit 3
fi
read -r ANSWER
if [ "$ANSWER" != "$PHRASE" ]; then echo "licence not accepted; nothing written" >&2; exit 3; fi
if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
  echo "pass --archive PATH to the archive you downloaded via $OFFICIAL_SOURCE" >&2; exit 2
fi
mkdir -p "$DEST"
case "$ARCHIVE" in
  *.zip) unzip -q -o "$ARCHIVE" -d "$DEST" ;;
  *.tar.gz|*.tgz) tar -xzf "$ARCHIVE" -C "$DEST" ;;
  *) echo "unsupported archive type: $ARCHIVE" >&2; exit 2 ;;
esac
META="$(dirname "$(dirname "$DEST")")/metadata"; mkdir -p "$META"
printf '{"accepted_phrase": "%s", "accepted_at_utc": "%s", "official_source": "%s", "archive_sha256": "%s"}\n' \
  "$PHRASE" "$(date -u +%FT%TZ)" "$OFFICIAL_SOURCE" "$(sha256sum "$ARCHIVE" | cut -d' ' -f1)" > "$META/licence_acceptance.json"
echo "extracted into $DEST (git-ignored); acceptance recorded in $META/licence_acceptance.json"
