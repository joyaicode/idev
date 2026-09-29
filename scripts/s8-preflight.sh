#!/usr/bin/env bash
# S8 preflight: fail fast when ticket/paths/patrol pack missing.
# Usage: s8-preflight.sh <feature> [workflow_id] [--product <name>]
# Exit: 0 OK, 1 usage/root fail, 2 BLOCKED missing inputs
# --product filters stage pages. Omit it to use the checkout marker id.
# IDEV_PRODUCT is the same switch.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FEATURE=""
WF=""
PRODUCT="${IDEV_PRODUCT:-}"
REPO="${IDEV_REPO:-${PWD:-.}}"
while [ $# -gt 0 ]; do
  case "$1" in
    --product)
      PRODUCT="${2:-}"
      shift 2
      ;;
    --product=*)
      PRODUCT="${1#--product=}"
      shift
      ;;
    *)
      if [ -z "$FEATURE" ]; then
        FEATURE="$1"
      elif [ -z "$WF" ]; then
        WF="$1"
      else
        echo "FAIL unexpected arg $1"
        exit 1
      fi
      shift
      ;;
  esac
done
WF="${WF:-lite-change}"

echo "# idev s8-preflight"
echo "feature=${FEATURE:-?} workflow=$WF product=${PRODUCT:-marker} repo=$REPO"

if [ ! -f "$ROOT/SKILL.md" ]; then
  echo "FAIL idev true source missing: $ROOT/SKILL.md"
  exit 1
fi
echo "OK  idev root $ROOT"

if [ -z "$FEATURE" ]; then
  echo "FAIL usage: s8-preflight.sh <feature> [workflow_id]"
  exit 1
fi

resolve_recipe() {
  local id="$1"
  local from="${2:-.}"
  local prod="" ext=""
  prod="$(cd "$from" && python3 "$ROOT/scripts/lib/product_sink.py" --print-repo || true)"
  if [ -n "$prod" ] && [ -n "$(python3 "$ROOT/scripts/lib/product_marker.py" --check "$prod")" ]; then
    if ! ext="$(python3 "$ROOT/scripts/lib/product_marker.py" --extension-repo "$prod")"; then
      echo "FAIL extension_root for $prod" >&2
      return 1
    fi
    if [ -n "$ext" ] && [ -f "$ext/.idev/workflows/${id}.yaml" ]; then
      printf '%s\n' "$ext/.idev/workflows/${id}.yaml"
      return 0
    fi
  fi
  if [ -f "$ROOT/workflows/${id}.yaml" ]; then
    printf '%s\n' "$ROOT/workflows/${id}.yaml"
    return 0
  fi
  return 1
}

recipe_skips_ticket() {
  python3 - "$1" <<'PY'
import sys
try:
    import yaml
except ImportError:
    sys.exit(1)
data = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
sys.exit(0 if isinstance(data, dict) and data.get("needs_ticket") is False else 1)
PY
}

blocked=0
block() { echo "BLOCKED $1"; blocked=1; }

DELIVER="$(python3 "$ROOT/scripts/lib/doc_home.py" --repo "$REPO" --feature "$FEATURE" --key deliver)"
PATROL="$(python3 "$ROOT/scripts/lib/doc_home.py" --repo "$REPO" --feature "$FEATURE" --key patrol)"
RECIPE=""
if RECIPE="$(resolve_recipe "$WF" "$REPO")"; then
  echo "OK  recipe $RECIPE"
else
  block "no recipe $WF under the marked product .idev/workflows or idev workflows"
fi

wants_ticket=1
if [ -n "$RECIPE" ] && recipe_skips_ticket "$RECIPE"; then
  wants_ticket=0
fi
if [ "$wants_ticket" = 1 ]; then
  if [ ! -f "$DELIVER" ]; then
    block "missing $DELIVER (set IDEV_REPO or cd to product repo)"
  else
    echo "OK  deliver.yaml $DELIVER"
  fi
fi

DELIVER_STAGE=""
if [ -f "${DELIVER:-}" ]; then
  DELIVER_STAGE="$(grep -E '^stage:' "$DELIVER" | head -1 | sed -E 's/^stage:[[:space:]]*//;s/[[:space:]]*$//;s/["'\'']//g' || true)"
fi
if [ "$wants_ticket" = 1 ] && [ -f "${DELIVER:-}" ] && [ "$WF" = "test-pack" ]; then
  if [ -n "$DELIVER_STAGE" ] && [ "$DELIVER_STAGE" != "test" ]; then
    block "test-pack expects stage=test, got stage=$DELIVER_STAGE"
  else
    echo "OK  stage=${DELIVER_STAGE:-unknown}"
  fi
fi

if [ "$WF" = "patrol-replay" ]; then
  if [ ! -f "$PATROL" ]; then
    block "missing patrol pack $PATROL"
  else
    echo "OK  patrol pack $PATROL"
  fi
fi

# Optional compile probe (opt-in): catches API/classpath drift before selftest.
# Usage: IDEV_PREFLIGHT_COMPILE=1 s8-preflight.sh <feature> <workflow>
# Optional module list: IDEV_PREFLIGHT_COMPILE_MODULES="<module>"
if [ "${IDEV_PREFLIGHT_COMPILE:-0}" = "1" ]; then
  if [ ! -f "$REPO/pom.xml" ]; then
    echo "WARN compile probe skipped (no pom.xml at repo root)"
  elif ! command -v mvn >/dev/null 2>&1; then
    echo "WARN compile probe skipped (mvn not on PATH)"
  else
    modules="${IDEV_PREFLIGHT_COMPILE_MODULES:-}"
    if [ -n "$modules" ]; then
      echo "RUN  mvn -pl $modules -am -DskipTests compile"
      if ! (cd "$REPO" && mvn -pl "$modules" -am -DskipTests compile -q); then
        block "mvn compile failed (modules=$modules); fix drift before selftest"
      else
        echo "OK  mvn compile ($modules)"
      fi
    else
      echo "RUN  mvn -DskipTests compile"
      if ! (cd "$REPO" && mvn -DskipTests compile -q); then
        block "mvn compile failed; fix drift before selftest"
      else
        echo "OK  mvn compile"
      fi
    fi
  fi
fi

PROD="$(cd "$REPO" && python3 "$ROOT/scripts/lib/product_sink.py" --print-repo || true)"
if [ -n "$RECIPE" ] && [ -n "$PROD" ]; then
  set +e
  def_out="$(python3 "$ROOT/scripts/lib/workflow_defaults.py" --repo "$PROD" --recipe "$RECIPE" 2>&1)"
  def_rc=$?
  set -e
  if [ -n "$def_out" ]; then
    printf '%s\n' "$def_out"
  fi
  if [ "$def_rc" -ne 0 ]; then
    blocked=1
  fi
fi
if [ -n "$PROD" ]; then
  ctx=(python3 "$ROOT/scripts/session-context.py" --repo "$PROD" --scenario S8 --feature "$FEATURE" --workflow "$WF")
  if [ -n "$PRODUCT" ]; then
    ctx+=(--product "$PRODUCT")
  fi
  if [ -n "$DELIVER_STAGE" ]; then
    ctx+=(--stage "$DELIVER_STAGE")
  fi
  set +e
  ext_out="$("${ctx[@]}" 2>&1)"
  ext_rc=$?
  set -e
  printf '%s\n' "$ext_out"
  if [ "$ext_rc" -ne 0 ]; then
    block "session-context failed"
  fi
fi

if [ "$blocked" -ne 0 ]; then
  echo "RESULT BLOCKED — list missing inputs above; do not invent seal/coverage"
  exit 2
fi
echo "RESULT OK"
exit 0
