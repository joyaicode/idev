#!/usr/bin/env bash
# Capability recipes live in idev/workflows. A marked product's recipes live in
# .idev/workflows of its extension root (the checkout itself when marker.yaml has
# no extension_root), the same place workflow.py and s8-preflight read them.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
IDEV="${HOME}/.cursor/skills/idev"
RECIPES="${IDEV}/workflows"
EXTRA=()
PROD="$(python3 "${IDEV}/scripts/lib/product_sink.py" --print-repo || true)"
if [ -n "${PROD}" ] && [ -n "$(python3 "${IDEV}/scripts/lib/product_marker.py" --check "${PROD}")" ]; then
  if ! EXT="$(python3 "${IDEV}/scripts/lib/product_marker.py" --extension-repo "${PROD}")"; then
    echo "FAIL: extension_root of ${PROD} is invalid" >&2
    exit 1
  fi
  if [ -n "${EXT}" ] && [ -d "${EXT}/.idev/workflows" ]; then
    EXTRA=(--product-recipes "${EXT}/.idev/workflows")
  fi
fi
if [ "${#EXTRA[@]}" -eq 0 ]; then
  exec python3 "${ROOT}/workflow-check.py" --recipes-dir "${RECIPES}" "$@"
fi
exec python3 "${ROOT}/workflow-check.py" --recipes-dir "${RECIPES}" "${EXTRA[@]}" "$@"
