#!/usr/bin/env bash
# Link outbound skills for a named pack.
# --pack <id> selects the registry pack to link. Omitted: refresh the pack
# already recorded in the install ledger (state/outbound-config.json).
# That ledger is not the session's current product.
# --heal refreshes a recorded pack and exits 0 when none is recorded.
# --force overwrites a different recorded pack. Still requires --pack or a recorded id.
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IDEV_ROOT="${IDEV_ROOT:-$SCRIPT_ROOT}"
# shellcheck source=lib/outbound-root.sh
source "${SCRIPT_ROOT}/scripts/lib/outbound-root.sh"

MODE=opt-in
PACK_ARG=""
POSITIONAL=()
while [ $# -gt 0 ]; do
  case "$1" in
    --heal)
      MODE=heal
      shift
      ;;
    --force)
      MODE=force
      IDEV_OUTBOUND_FORCE_PACK=1
      export IDEV_OUTBOUND_FORCE_PACK
      shift
      ;;
    --pack)
      PACK_ARG="${2:-}"
      if [ -z "$PACK_ARG" ]; then
        echo "FAIL: --pack needs a pack id" >&2
        exit 2
      fi
      shift 2
      ;;
    --)
      shift
      POSITIONAL+=("$@")
      break
      ;;
    -*)
      echo "FAIL: unknown flag $1" >&2
      exit 2
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done
PRODUCT_PATH="${POSITIONAL[0]:-}"

REGPY="${SCRIPT_ROOT}/scripts/lib/outbound_registry.py"
existing="$(python3 "$REGPY" read-pilot --cfg "$(idev_outbound_config_path)")"

pack_known() {
  python3 - "$SCRIPT_ROOT" "$1" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "scripts" / "lib"))
from outbound_registry import load_registry
pid = sys.argv[2]
reg = load_registry(Path(sys.argv[1]))
raise SystemExit(0 if pid in (reg.get("packs") or {}) else 1)
PY
}

PACK="$PACK_ARG"
if [ "$MODE" != "force" ] && [ -n "$existing" ] && [ -n "$PACK_ARG" ] && [ "$existing" != "$PACK_ARG" ]; then
  echo "KEEP existing pilot ${existing} — skip link"
  exit 0
fi
if [ -z "$PACK" ] && [ -n "$existing" ]; then
  if pack_known "$existing"; then
    PACK="$existing"
  elif [ "$MODE" != "force" ]; then
    echo "KEEP existing pilot ${existing} — skip link"
    exit 0
  fi
fi
if [ -z "$PACK" ]; then
  if [ "$MODE" = "heal" ]; then
    echo "SKIP heal (no pack selected; name --pack to opt in)"
    exit 0
  fi
  echo "FAIL: name --pack <id>. No pilot is selected." >&2
  exit 2
fi

DEST_CURSOR="${HOME}/.cursor/skills"
DEST_AGENTS="${HOME}/.agents/skills"
mkdir -p "$DEST_CURSOR" "$DEST_AGENTS"

JP="$(idev_discover_product_root "$PRODUCT_PATH")" || {
  if [ "$MODE" = "heal" ]; then
    echo "SKIP product heal (repo not found)"
    exit 0
  fi
  echo "FAIL: product repo not found. Pass path or set IDEV_PRODUCT_ROOT." >&2
  exit 1
}
SRC="${JP}/.cursor/skills"
echo "product root: $JP"
echo "pack: $PACK"

link_one() {
  local name="$1" required="${2:-0}"
  local src="${SRC}/${name}"
  if [ ! -e "$src" ]; then
    if [ "$required" = "1" ]; then
      echo "FAIL missing source: $src" >&2
      return 1
    fi
    echo "SKIP optional missing source: $name"
    return 0
  fi
  local dest_root dest
  for dest_root in "$DEST_CURSOR" "$DEST_AGENTS"; do
    dest="${dest_root}/${name}"
    if [ -L "$dest" ] && [ ! -e "$dest" ]; then
      echo "HEAL broken symlink: $dest"
      rm -f "$dest"
    fi
    if [ -e "$dest" ] && [ ! -L "$dest" ]; then
      echo "KEEP existing (not symlink): $dest"
      continue
    fi
    ln -sfn "$src" "$dest"
    echo "OK  $dest -> $src"
  done
}

link_json="$(python3 "$REGPY" pack-link --root "$SCRIPT_ROOT" --repo "$JP" --pack "$PACK")"
fail=0
while IFS=$'\t' read -r req name; do
  [ -z "${name:-}" ] && continue
  link_one "$name" "$req" || fail=1
done < <(python3 - "$link_json" <<'PY'
import json,sys
d=json.loads(sys.argv[1])
for n in d.get("required") or []:
    print("1\t%s" % n)
for n in d.get("optional") or []:
    print("0\t%s" % n)
PY
)

cfg="$(idev_write_outbound_config "$JP" "$PACK")"
echo "OK  wrote $cfg"

if [ "$fail" -ne 0 ]; then
  echo "link-outbound-skills FAIL"
  exit 1
fi
echo "link-outbound-skills PASS"
exit 0
