#!/usr/bin/env bash
# Soft-link ~/.agents and ~/.joycode idev dirs to the only true source:
# ~/.cursor/skills/idev (must be a real directory, not a symlink).
set -euo pipefail
TRUE="${HOME}/.cursor/skills/idev"

if [ ! -d "$TRUE" ]; then
  echo "FAIL true source missing: $TRUE" >&2
  exit 1
fi
if [ -L "$TRUE" ]; then
  echo "FAIL $TRUE is a symlink; true source must be a real directory" >&2
  echo "     points to: $(readlink "$TRUE")" >&2
  exit 1
fi

true_phys="$(cd "$TRUE" && pwd -P)"

link_alias() {
  local dest="$1"
  mkdir -p "$(dirname "$dest")"
  if [ -L "$dest" ]; then
    if [ -e "$dest" ] && [ "$(cd "$dest" && pwd -P)" = "$true_phys" ]; then
      echo "OK  $dest -> $TRUE"
      return 0
    fi
    echo "HEAL $dest (was $(readlink "$dest"))"
    rm -f "$dest"
  elif [ -e "$dest" ]; then
    echo "FAIL $dest exists and is not a symlink (would hide true source)" >&2
    return 1
  fi
  ln -sfn "$TRUE" "$dest"
  echo "OK  $dest -> $TRUE"
}

fail=0
link_alias "${HOME}/.agents/skills/idev" || fail=1
link_alias "${HOME}/.joycode/skills/idev" || fail=1
if [ "$fail" -ne 0 ]; then
  echo "link-idev-aliases FAIL"
  exit 1
fi
echo "link-idev-aliases PASS"
exit 0
