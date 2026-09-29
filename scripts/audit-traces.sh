#!/usr/bin/env bash
# Discipline audit for idev traces. Usage: audit-traces.sh [N] [--strict]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${IDEV_TRACE_DIR:-}" ]]; then
  DIR="$IDEV_TRACE_DIR"
else
  DIR="$(python3 "$ROOT/scripts/lib/product_sink.py" traces)"
fi
N=50
STRICT="${STRICT:-0}"
for arg in "$@"; do
  case "$arg" in
    --strict) STRICT=1 ;;
    --help|-h) echo "usage: $0 [N] [--strict]"; exit 0 ;;
    *)
      if [[ "$arg" =~ ^[0-9]+$ ]]; then N="$arg"
      else echo "unknown: $arg" >&2; exit 2
      fi
      ;;
  esac
done
[[ -d "$DIR" ]] || { echo "No traces dir: $DIR" >&2; exit 1; }

REPORT="$(python3 "$ROOT/scripts/audit_traces_lib.py" "$DIR" "$N")"
HARD="$(printf '%s\n' "$REPORT" | sed -n 's/^HARD_COUNT=//p' | tail -1)"
HARD="${HARD:-0}"
printf '%s\n' "$REPORT" | grep -v '^HARD_COUNT=' || true
echo "HARD_COUNT=${HARD}"

if [[ "$STRICT" == "1" && "$HARD" -gt 0 ]]; then
  echo "STRICT: $HARD hard alert(s)" >&2
  exit 1
fi
exit 0
