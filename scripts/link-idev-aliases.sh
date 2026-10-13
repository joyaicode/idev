#!/usr/bin/env bash
# Soft-link ~/.agents and ~/.joycode idev dirs to the only true source:
# ~/.cursor/skills/idev.
#
# That path may itself be a symlink into a git checkout. "True source" means
# there is exactly ONE copy of the content, not that this path is a real
# directory — and a versioned checkout is the better shape. Aliases are
# verified by physical path below, which handles either.
set -euo pipefail
TRUE="${HOME}/.cursor/skills/idev"

if [ ! -e "$TRUE" ]; then
  echo "FAIL true source missing: $TRUE" >&2
  exit 1
fi
if [ ! -f "$TRUE/SKILL.md" ]; then
  echo "FAIL $TRUE does not look like an idev root (no SKILL.md)" >&2
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
