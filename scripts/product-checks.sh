#!/usr/bin/env bash
# Run the current product's own checks in the extension root's .idev/checks/*.sh.
# No marker, or no checks directory: nothing to run.
# A script may declare `# idev-stages: arch code`. With --stage, it runs only
# for those stages. Without --stage, every script runs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
REPO=""
STAGE=""

usage() {
  echo "usage: product-checks.sh [--stage <stage>] [--repo <git-root> | <git-root>]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stage)
      STAGE="${2:-}"
      shift 2
      ;;
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "$REPO" ]]; then
        REPO="$1"
        shift
      else
        usage
        exit 2
      fi
      ;;
  esac
done

echo "# idev product-checks"

if [[ -z "$REPO" ]]; then
  REPO="$(python3 "$ROOT/scripts/lib/product_sink.py" --print-repo || true)"
fi
if [[ -z "$REPO" ]]; then
  echo "OK  no current product"
  echo "product-checks PASS"
  exit 0
fi

ERR="$(mktemp "${TMPDIR:-/tmp}/idev-ext-repo.XXXXXX")"
trap 'rm -f "$ERR"' EXIT
set +e
EXT="$(python3 "$ROOT/scripts/lib/product_marker.py" --extension-repo "$REPO" 2>"$ERR")"
erc=$?
set -e
if [[ "$erc" -ne 0 ]]; then
  cat "$ERR" >&2 || true
  echo "product-checks FAIL"
  exit 1
fi
if [[ -z "$EXT" ]]; then
  echo "OK  current product has no idev marker"
  echo "product-checks PASS"
  exit 0
fi

applies() {
  local script="$1" line stages token
  [[ -z "$STAGE" ]] && return 0
  line="$(grep -m1 -E '^# idev-stages:' "$script" || true)"
  [[ -z "$line" ]] && return 0
  stages="${line#\# idev-stages:}"
  for token in $stages; do
    if [[ "$token" == "$STAGE" ]]; then
      return 0
    fi
  done
  return 1
}

dir="$EXT/.idev/checks"
if [[ ! -d "$dir" ]]; then
  echo "OK  no .idev/checks"
  echo "product-checks PASS"
  exit 0
fi

shopt -s nullglob
scripts=("$dir"/*.sh)
shopt -u nullglob
if [[ ${#scripts[@]} -eq 0 ]]; then
  echo "OK  .idev/checks has no scripts"
  echo "product-checks PASS"
  exit 0
fi

fail=0
ran=0
for script in "${scripts[@]}"; do
  if ! applies "$script"; then
    echo "OK  $(basename "$script") skipped for $STAGE"
    continue
  fi
  ran=1
  if bash "$script" "$EXT"; then
    echo "OK  $(basename "$script")"
  else
    echo "FAIL $(basename "$script")"
    fail=1
  fi
done
if [[ "$fail" -ne 0 ]]; then
  echo "product-checks FAIL"
  exit 1
fi
if [[ "$ran" -eq 0 ]]; then
  echo "OK  no checks for ${STAGE:-all}"
fi
echo "product-checks PASS"
exit 0
