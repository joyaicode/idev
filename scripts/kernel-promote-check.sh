#!/usr/bin/env bash
# Gate for lifting a product draft into the idev kernel.
# Does not copy. Exit 0 only when the file has no unlabelled product tokens.
# Usage: kernel-promote-check.sh <file>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
file="${1:?usage: kernel-promote-check.sh <file>}"
if [[ ! -f "$file" ]]; then
  echo "FAIL missing $file" >&2
  exit 1
fi
python3 - "$file" "$ROOT/scripts/lib" <<'PY'
import re, sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from product_marker import pilot_strip_tokens
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
tokens = pilot_strip_tokens(from_install=True)
if not tokens:
    print("OK  kernel-promote-check %s (no pilot strip tokens)" % path)
    raise SystemExit(0)
pattern = re.compile("|".join(re.escape(token) for token in tokens))
label = re.compile(r"试点例|试点：|试点:|例：|例:|e\.g\.|for example|EXAMPLE|example:")
bad = []
for i, line in enumerate(text.splitlines(), 1):
    if pattern.search(line) and not label.search(line):
        bad.append("%d:%s" % (i, line.strip()))
if bad:
    print("FAIL product tokens still in draft; strip before kernel promote", file=sys.stderr)
    for line in bad:
        print(line, file=sys.stderr)
    raise SystemExit(1)
print("OK  kernel-promote-check %s" % path)
PY
