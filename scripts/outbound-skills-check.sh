#!/usr/bin/env bash
# Check handoff Skills for the current product, or for the install ledger.
# Session (default): the current product repo is the pilot. Required skills
# come from that repo's .idev/handoff.yaml. The kernel registry does not
# name products.
# --install: verify skills recorded in state/outbound-config.json, using
# that ledger's product_root handoff. That file is not the session's current product.
# Optional miss -> WARN, still exit 0 if required OK.
# Broken symlinks count as missing.
set -euo pipefail
IDEV_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/outbound-root.sh
source "${IDEV_ROOT}/scripts/lib/outbound-root.sh"

REPO=""
INSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --install) INSTALL=1; shift ;;
    -h|--help) echo "usage: outbound-skills-check.sh [--repo <git-root> | --install]"; exit 0 ;;
    *) echo "usage: outbound-skills-check.sh [--repo <git-root> | --install]" >&2; exit 2 ;;
  esac
done

roots=()
resolve_args=(resolve --root "$IDEV_ROOT")
if [ "$INSTALL" = "1" ]; then
  resolve_args+=(--install)
  if jp="$(idev_read_product_root_from_config 2>/dev/null)"; then
    roots+=("${jp}/.cursor/skills" "${jp}/.agents/skills")
    resolve_args+=(--repo "$jp")
    echo "note: install ledger product root ${jp}"
  fi
else
  if [ -z "$REPO" ]; then
    REPO="$(python3 "${IDEV_ROOT}/scripts/lib/product_sink.py" --print-repo)"
  fi
  if [ -n "$REPO" ]; then
    roots+=("${REPO}/.cursor/skills" "${REPO}/.agents/skills")
    resolve_args+=(--repo "$REPO")
    echo "note: current product ${REPO}"
  fi
fi
if [ -n "${IDEV_SKILL_ROOTS:-}" ]; then
  IFS=':' read -r -a extra <<< "${IDEV_SKILL_ROOTS}"
  if [ "${#extra[@]}" -gt 0 ]; then
    roots+=("${extra[@]}")
  fi
fi
if [ "${IDEV_OUTBOUND_NO_HOME:-0}" = "1" ]; then
  echo "note: IDEV_OUTBOUND_NO_HOME=1 — skipping \$HOME skill roots"
else
  roots+=("${HOME}/.cursor/skills" "${HOME}/.agents/skills")
fi

meta="$(python3 "${IDEV_ROOT}/scripts/lib/outbound_registry.py" "${resolve_args[@]}")"

have() {
  local n="$1" r p
  for r in "${roots[@]}"; do
    p="${r}/${n}"
    if [ -L "$p" ] && [ ! -e "$p" ]; then
      continue  # broken link ≠ present
    fi
    if [ -d "$p" ] || [ -f "${p}/SKILL.md" ]; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

fail=0
warn=0

all_names="$(python3 -c "import json,sys; print('\n'.join(json.load(sys.stdin)['all_names']))" <<<"$meta")"
if [ "${IDEV_OUTBOUND_NO_HOME:-0}" != "1" ]; then
  while IFS= read -r n; do
    [ -z "$n" ] && continue
    for base in "${HOME}/.cursor/skills" "${HOME}/.agents/skills"; do
      bp="${base}/${n}"
      if [ -L "$bp" ] && [ ! -e "$bp" ]; then
        echo "WARN broken home symlink: $bp"
        warn=1
      fi
    done
  done <<<"$all_names"
fi

echo "=== idev outbound skills ==="
pack="$(python3 -c "import json,sys; print(json.load(sys.stdin).get('pack') or '')" <<<"$meta")"
note="$(python3 -c "import json,sys; print(json.load(sys.stdin).get('note') or '')" <<<"$meta")"
if [ -n "$pack" ]; then
  echo "note: pack ${pack} required (${note})"
else
  echo "note: ${note:-没有当前产品}"
fi

resolve() {
  local label="$1" required="$2"
  shift 2
  local n path
  for n in "$@"; do
    if path="$(have "$n")"; then
      echo "OK  $label -> $n ($path)"
      return 0
    fi
  done
  if [ "$required" = "1" ]; then
    echo "MISS REQUIRED $label (tried: $*)"
    fail=1
  else
    echo "WARN optional missing: $label (tried: $*)"
    warn=1
  fi
  return 1
}

while IFS=$'\t' read -r req label names; do
  [ -z "${label:-}" ] && continue
  # shellcheck disable=SC2086
  resolve "$label" "$req" $names || true
done < <(python3 - "$meta" <<'PY'
import json,sys
meta=json.loads(sys.argv[1])
for slot in meta.get("slots") or []:
    print("%s\t%s\t%s" % (1 if slot.get("required") else 0, slot.get("label") or "", " ".join(slot.get("names") or [])))
PY
)

if [ "$fail" -ne 0 ]; then
  echo "HINT: the missing Skill is named in this product's .idev/handoff.yaml"
  echo "      put it in ~/.cursor/skills/<name> (or the product repo .cursor/skills)"
  echo "FAIL: required handoff Skill(s) missing. Stop at handoff; do not invent parallel runbooks."
  exit 1
fi
if [ "$warn" -ne 0 ]; then
  echo "=== required OK; optional gaps noted ==="
else
  echo "=== all outbound skills present ==="
fi
exit 0
