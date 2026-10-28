#!/usr/bin/env bash
# Install pre-commit and pre-push hooks that refresh CodeGraph first.
# Writes .git/hooks only. Does not change git config.
#
#   bash scripts/install-codegraph-hooks.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
HOOKS="$(git -C "${ROOT}" rev-parse --git-path hooks)"
case "${HOOKS}" in
  /*) ;;
  *) HOOKS="${ROOT}/${HOOKS}" ;;
esac
mkdir -p "${HOOKS}"

MARKER_BEGIN="# >>> idev codegraph sync >>>"
MARKER_END="# <<< idev codegraph sync <<<"

block() {
  cat <<EOF
${MARKER_BEGIN}
# Refresh the local CodeGraph index before this git operation.
root=\$(git rev-parse --show-toplevel) || exit 1
/bin/bash "\$root/scripts/codegraph-sync.sh" --repo "\$root" commit || exit \$?
${MARKER_END}
EOF
}

strip_block() {
  awk -v begin="${MARKER_BEGIN}" -v end="${MARKER_END}" '
    $0 == begin { skip = 1; next }
    $0 == end { skip = 0; next }
    !skip { print }
  '
}

install_one() {
  local name="$1"
  local dest="${HOOKS}/${name}"
  local existing=""
  if [ -f "${dest}" ]; then
    existing="$(strip_block < "${dest}")"
  fi
  local tmp
  tmp="$(mktemp)"
  if [ -z "${existing}" ]; then
    {
      echo "#!/bin/sh"
      block
    } > "${tmp}"
  else
    {
      echo "#!/bin/sh"
      block
      printf '%s\n' "${existing}" | awk 'NR==1 && /^#!/ { next } { print }'
    } > "${tmp}"
  fi
  mv "${tmp}" "${dest}"
  chmod 755 "${dest}"
  echo "installed ${dest}"
}

install_one pre-commit
install_one pre-push
