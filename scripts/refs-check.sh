#!/usr/bin/env bash
# Fail if SKILL / cheatsheet / invoke reference a missing scripts/*.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
fail=0
echo "# idev refs-check"

docs="$ROOT/SKILL.md $ROOT/references/operator-cheatsheet.md $ROOT/references/invoke.md $ROOT/references/deep-read.md $ROOT/references/lite-change-pitfalls.md"
# shellcheck disable=SC2086
refs=$(rg -oN 'scripts/[a-z0-9_-]+\.sh' $docs 2>/dev/null | sed 's/.*://' | sort -u || true)
if [ -z "$refs" ]; then
  echo "WARN no scripts/*.sh mentions found in docs"
fi
while IFS= read -r rel; do
  [ -z "$rel" ] && continue
  if [ ! -f "$ROOT/$rel" ]; then
    echo "MISS $rel (mentioned in docs)"
    fail=1
  else
    echo "OK  $rel"
  fi
done <<EOFREFS
$refs
EOFREFS

for rel in \
  verify/scripts/promote.sh \
  workflows/lite-change.yaml \
  scripts/healthcheck.sh \
  scripts/selfcheck.sh \
  scripts/link-outbound-skills.sh \
  scripts/link-idev-aliases.sh \
  scripts/link-companion-skills.sh \
  scripts/core-strip-check.sh \
  scripts/lite-change-smoke.sh \
  scripts/late-lifecycle-smoke.sh \
  scripts/second-product-smoke.sh \
  scripts/s8-preflight.sh \
  references/s1-vs-s8-playbook.md \
  scripts/ticket_yaml.py \
  scripts/lib/outbound_registry.py \
  scripts/lib/outbound-root.sh \
  handoffs/registry.yaml \
  references/deep-read.md \
  references/lite-change-pitfalls.md
do
  if [ ! -e "$ROOT/$rel" ]; then
    echo "MISS critical $rel"
    fail=1
  else
    echo "OK  critical:$rel"
  fi
done

names="$(python3 "$ROOT/scripts/lib/outbound_registry.py" names --root "$ROOT" 2>/dev/null || true)"
names="${names}"$'\n'"grilling"
while IFS= read -r name; do
  [ -z "$name" ] && continue
  p="${HOME}/.cursor/skills/${name}"
  if [ -L "$p" ]; then
    if [ ! -e "$p" ]; then
      echo "WARN broken symlink $p"
    else
      echo "OK  link $name"
    fi
  fi
done <<<"$names"

if ! python3 "$ROOT/scripts/config-doc-check.py"; then
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "refs-check FAIL"
  exit 1
fi
echo "refs-check PASS"
exit 0
