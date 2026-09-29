# shellcheck shell=bash
# Sourced by outbound scripts. Sets nothing globally except via caller capture.
# Product-agnostic. Resolution order:
#   explicit arg → IDEV_PRODUCT_ROOT →
#   state/outbound-config.json (product_root).
# Disk presence of a registered product does not select a pack.

idev_script_root() {
  (cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
}

idev_outbound_config_path() {
  local root="${IDEV_ROOT:-}"
  if [ -z "$root" ]; then
    root="$(idev_script_root)"
  fi
  echo "${root}/state/outbound-config.json"
}

idev_read_product_root_from_config() {
  local cfg path
  cfg="$(idev_outbound_config_path)"
  [ -f "$cfg" ] || return 1
  path="$(python3 - "$cfg" <<'PY'
import json,sys
p=sys.argv[1]
try:
    d=json.load(open(p,encoding="utf-8"))
except Exception:
    raise SystemExit(1)
print(d.get("product_root") or "")
PY
)"
  [ -n "$path" ] && [ -d "${path}/.cursor/skills" ] || return 1
  printf '%s\n' "$path"
}

idev_discover_product_root() {
  # $1 = optional explicit path. IDEV_PRODUCT_ROOT is the env override.
  local c
  for c in \
    "${1:-}" \
    "${IDEV_PRODUCT_ROOT:-}" \
    "$(idev_read_product_root_from_config 2>/dev/null || true)"
  do
    if [ -n "$c" ] && [ -d "${c}/.cursor/skills" ]; then
      printf '%s\n' "$c"
      return 0
    fi
  done
  return 1
}

idev_write_outbound_config() {
  local jp="$1"
  local pack="${2:-}"
  if [ -z "$pack" ]; then
    echo "FAIL: pack id required" >&2
    return 2
  fi
  local script_root root
  script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  root="${IDEV_ROOT:-$script_root}"
  if [ "${IDEV_OUTBOUND_FORCE_PACK:-0}" = "1" ]; then
    python3 "${script_root}/scripts/lib/outbound_registry.py" write-config \
      --root "$script_root" \
      --cfg "${root}/state/outbound-config.json" \
      --product-root "$jp" \
      --pack "$pack" \
      --force-pack
  else
    python3 "${script_root}/scripts/lib/outbound_registry.py" write-config \
      --root "$script_root" \
      --cfg "${root}/state/outbound-config.json" \
      --product-root "$jp" \
      --pack "$pack"
  fi
}
