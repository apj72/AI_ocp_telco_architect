#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT=$(pwd)

DB="$ROOT/data/partners.db"
WORKSPACE="${TPS_WORKSPACE:-$HOME/tps-workspace}"
DEST="${1:-$ROOT/data/backups}"
mkdir -p "$DEST"

if [[ ! -f "$DB" ]]; then
  echo "No database at $DB"
  exit 1
fi

STAMP=$(date +%Y%m%d_%H%M%S)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Safe online backup via SQLite .backup command
sqlite3 "$DB" ".backup $TMP/partners.db"

# Validate
INTEGRITY=$(sqlite3 "$TMP/partners.db" "PRAGMA integrity_check;" 2>&1)
if [[ "$INTEGRITY" != "ok" ]]; then
  echo "Backup validation FAILED: $INTEGRITY"
  exit 1
fi

# Bundle DB + workspace into zip
OUT="$DEST/manual_${STAMP}.zip"
(cd "$TMP" && zip -q -r "$OUT" partners.db)
if [[ -d "$WORKSPACE" ]]; then
  (cd "$(dirname "$WORKSPACE")" && zip -q -r "$OUT" "$(basename "$WORKSPACE")")
fi

echo "Backed up to $OUT ($(du -h "$OUT" | cut -f1))"
echo "Integrity: $INTEGRITY"
