#!/usr/bin/env bash
# Show actual idev runtime paths from traces. Usage:
#   path-view.sh              # last trace path
#   path-view.sh paths [N]    # table
#   path-view.sh stats [N]    # frequency
#   path-view.sh <file.yaml>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TRACE="$ROOT/scripts/trace.sh"
case "${1:-}" in
  "" ) exec bash "$TRACE" path ;;
  paths )
    n="${2:-20}"
    exec bash "$TRACE" paths -n "$n"
    ;;
  stats|path-stats )
    n="${2:-50}"
    exec bash "$TRACE" path-stats -n "$n"
    ;;
  * )
    exec bash "$TRACE" path "$1"
    ;;
esac
