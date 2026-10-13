#!/usr/bin/env bash
# Parse every script without running it.
#
#   bash scripts/syntax-check.sh
#
# This runs BEFORE smoke.sh, because smoke cannot catch a syntax error in
# smoke: a script that will not parse never executes a single assertion,
# and `bash` says nothing until you try to run it.
#
# That is not hypothetical. smoke.sh carried an unparseable heredoc for
# several rounds of "smoke covers this" — a fixture containing a literal
# "BLOCKED(" inside a $(...)-wrapped heredoc made bash count that paren,
# and the reported error landed 300 lines away at EOF. See
# references/failure-modes.md.
#
# Both checks are pure parsing with no side effects: `bash -n` never runs
# a command, and ast.parse never imports anything.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$REPO"
fail=0

echo "== bash"
for f in scripts/*.sh; do
  [ -e "$f" ] || continue
  out="$(bash -n "$f" 2>&1)"
  if [ -n "$out" ]; then
    printf '  FAIL %s\n' "$f"
    printf '%s\n' "$out" | sed 's/^/       /'
    fail=$((fail + 1))
  else
    printf '  ok   %s\n' "$f"
  fi
done

echo "== python"
if ! python3 - <<'PY'; then
import ast
import pathlib
import sys

bad = 0
for path in sorted(pathlib.Path("scripts").rglob("*.py")):
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        print(f"  FAIL {path}:{exc.lineno} {exc.msg}")
        bad += 1
    except OSError as exc:
        print(f"  FAIL {path}: {exc.strerror}")
        bad += 1
    else:
        print(f"  ok   {path}")
sys.exit(1 if bad else 0)
PY
  fail=$((fail + 1))
fi

echo
if [ "$fail" -ne 0 ]; then
  echo "syntax-check FAIL"
  exit 1
fi
echo "syntax-check PASS"
exit 0
