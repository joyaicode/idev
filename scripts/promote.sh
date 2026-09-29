#!/usr/bin/env bash
# Thin wrapper → verify/scripts/promote.sh (docs may say scripts/promote.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "$ROOT/verify/scripts/promote.sh" "$@"
