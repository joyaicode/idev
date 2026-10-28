#!/usr/bin/env bash
# Weekly outcome pack: metrics + curator dry-run + deletion budget (phase 2).
# Counts only; never a gate. Write under IDEV_DATA or --out.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${1:-$(pwd)}"
OUT="${IDEV_WEEKLY_OUT:-${IDEV_DATA:-$HOME/.idev}/weekly}"
mkdir -p "$OUT"
STAMP="$(date -u +%Y%m%d)"
DEST="$OUT/$STAMP"
mkdir -p "$DEST"

python3 "$ROOT/scripts/outcome-metrics.py" --repo "$REPO" --json >"$DEST/outcome.json"
python3 "$ROOT/scripts/outcome-metrics.py" --repo "$REPO" >"$DEST/outcome.txt"
bash "$ROOT/scripts/evolve-curator.sh" --days 30 >"$DEST/curator.txt" 2>&1 || true
python3 "$ROOT/scripts/deletion-budget.py" --json >"$DEST/deletion-budget.json"
python3 "$ROOT/scripts/usage-scan.py" --repo "$REPO" --days 60 >"$DEST/usage-scan.txt" || true

echo "weekly-outcome wrote $DEST"
ls -la "$DEST"
