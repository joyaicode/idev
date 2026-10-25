#!/usr/bin/env bash
# Python, Go, Shell, and JS/Vue convention scan used by coding-scan.sh.
# The only dependency is the plugin shipped next to this script.
# It does not install ruff, golangci-lint, shellcheck, eslint, Node, or Go,
# and it does not download.
#
#   bash scripts/lang-scan.sh <repo>
#
# Exit 0: every language plugin that had a diff reported no findings,
#         or there is no diff in these languages.
# Exit 1: a plugin reported a finding.
# Exit 2: a plugin file is missing. That is UNPROVEN, not a clean scan.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="${1:-}"
if [ -z "$REPO" ] || [ ! -d "$REPO" ]; then
  echo "usage: lang-scan.sh <repo>" >&2
  exit 2
fi
REPO="$(cd "$REPO" && pwd)"
PLUGIN_DIR="${LANG_PLUGIN_DIR:-$ROOT/plugin}"

langs="$(python3 - "$ROOT" "$REPO" << 'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "lib"))
import source_diff
repo = Path(sys.argv[2])
specs = (
    ("python", (".py",), "python"),
    ("go", (".go",), "go"),
    ("shell", (".sh", ".bash"), "shell"),
    ("js", (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue"), "js"),
)
for name, suffixes, label in specs:
    rels, _scope = source_diff.changed(repo, suffixes, label)
    if rels:
        print(name)
PY
)"

if [ -z "$langs" ]; then
  echo "lang: no diff"
  exit 0
fi

worst=0
while IFS= read -r lang; do
  [ -n "$lang" ] || continue
  plugin="$PLUGIN_DIR/${lang}_inspect.py"
  if [ ! -f "$plugin" ]; then
    echo "lang: UNPROVEN"
    echo "plugin: missing ${plugin}"
    if [ "$worst" -ne 1 ]; then
      worst=2
    fi
    continue
  fi
  set +e
  python3 "$plugin" "$REPO"
  rc=$?
  set -e
  if [ "$rc" -eq 1 ]; then
    worst=1
  elif [ "$rc" -ne 0 ] && [ "$worst" -ne 1 ]; then
    worst=2
  fi
done <<< "$langs"

if [ "$worst" -eq 1 ]; then
  echo "lang: findings"
  exit 1
fi
if [ "$worst" -eq 2 ]; then
  echo "lang: UNPROVEN"
  exit 2
fi
echo "lang: clean"
exit 0
