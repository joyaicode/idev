#!/usr/bin/env bash
# One-shot: link handoff Skills for a named pack, write the install ledger, verify.
# Usage: bootstrap-outbound.sh [--force] [--pack <id>] [product-root]
# Without --pack, refresh the pack already in state/outbound-config.json.
# That file records an install. The session pilot is the current product repo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "# idev bootstrap-outbound"
if [ "${1:-}" = "--force" ]; then
  shift
  bash "$ROOT/scripts/link-outbound-skills.sh" --force "$@"
else
  bash "$ROOT/scripts/link-outbound-skills.sh" "$@"
fi
echo
bash "$ROOT/scripts/link-companion-skills.sh" || true
echo
bash "$ROOT/scripts/outbound-skills-check.sh" --install
echo
echo "bootstrap-outbound PASS"
