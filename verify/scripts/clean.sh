#!/usr/bin/env bash
# Remove generatedverify trees. Does not touch docs/task/.../verify/.
set -euo pipefail

root="${1:-.}"
found=0
while IFS= read -r -d '' dir; do
  rm -rf "$dir"
  echo "clean: removed $dir"
  found=1
done < <(find "$root" -type d -name generatedverify -path '*/src/test/java/*' -print0 2>/dev/null)

if [[ "$found" -eq 0 ]]; then
  echo "clean: no generatedverify directories"
fi
