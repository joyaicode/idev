#!/usr/bin/env bash
# Java convention scan used by coding-scan.sh.
# The only dependency is the plugin shipped next to this script.
# It does not install IntelliJ or a JDK, and it does not download.
#
#   bash scripts/problems-scan.sh <repo> [relative-dir]
#
# Exit 0: the plugin reported no findings (or there is no Java diff).
# Exit 1: the plugin reported a finding.
# Exit 2: the plugin is missing. That is UNPROVEN, not a clean scan.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="${ROOT}/plugin/java_inspect.py"

if [ ! -f "$PLUGIN" ]; then
  echo "problems: UNPROVEN"
  echo "plugin: missing ${PLUGIN}"
  exit 2
fi

exec python3 "$PLUGIN" "$@"
