#!/usr/bin/env bash
# Companion skills idev opens during delivery.
# grilling true source: ~/.cursor/skills/grilling (real directory).
# setup-agents-docs: ~/.cursor/skills/setup-agents-docs must resolve to SKILL.md
# (a symlink to that skill's own tree is accepted).
# Soft-link ~/.agents and ~/.joycode at the same names.
# Usage: link-companion-skills.sh [grilling|setup-agents-docs ...]
# No args links both.
set -euo pipefail

link_alias() {
  local true_src="$1"
  local dest="$2"
  local true_phys
  true_phys="$(cd "$true_src" && pwd -P)"
  mkdir -p "$(dirname "$dest")"
  if [ -L "$dest" ]; then
    if [ -e "$dest" ] && [ "$(cd "$dest" && pwd -P)" = "$true_phys" ]; then
      echo "OK  $dest -> $true_src"
      return 0
    fi
    echo "HEAL $dest (was $(readlink "$dest"))"
    rm -f "$dest"
  elif [ -e "$dest" ]; then
    echo "FAIL $dest exists and is not a symlink (would hide true source)" >&2
    return 1
  fi
  ln -sfn "$true_src" "$dest"
  echo "OK  $dest -> $true_src"
}

link_named() {
  local name="$1"
  local require_real="$2"
  local src="${HOME}/.cursor/skills/${name}"
  if [ ! -e "$src" ]; then
    echo "FAIL true source missing: $src" >&2
    echo "HINT: ${name} must live at ~/.cursor/skills/${name}" >&2
    return 1
  fi
  if [ "$require_real" = "real" ] && [ -L "$src" ]; then
    echo "FAIL $src is a symlink; true source must be a real directory" >&2
    echo "     points to: $(readlink "$src")" >&2
    return 1
  fi
  if [ ! -f "$src/SKILL.md" ]; then
    echo "FAIL $src has no SKILL.md" >&2
    return 1
  fi
  local fail=0
  link_alias "$src" "${HOME}/.agents/skills/${name}" || fail=1
  link_alias "$src" "${HOME}/.joycode/skills/${name}" || fail=1
  return "$fail"
}

targets=("$@")
if [ "${#targets[@]}" -eq 0 ]; then
  targets=(grilling setup-agents-docs)
fi

fail=0
for name in "${targets[@]}"; do
  case "$name" in
    grilling) link_named grilling real || fail=1 ;;
    setup-agents-docs) link_named setup-agents-docs any || fail=1 ;;
    *)
      echo "FAIL unknown companion: $name" >&2
      fail=1
      ;;
  esac
done
if [ "$fail" -ne 0 ]; then
  echo "link-companion-skills FAIL"
  exit 1
fi
echo "link-companion-skills PASS"
exit 0
