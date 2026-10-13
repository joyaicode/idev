#!/usr/bin/env bash
# Expose idev's five execution agents to Claude Code and Cursor.
#
#   link-agents.sh            agents/*.md -> ~/.claude/agents/
#   link-agents.sh --unlink   remove them
#
# One target serves both tools: Cursor reads ~/.claude/agents/ as a
# compatibility location (its own ~/.cursor/agents/ wins on a name clash,
# and we put nothing there).
#
# The /idev skill needs nothing from this script. idev is already a skill at
# ~/.cursor/skills/idev, and the agent layer now lives inside it — so there
# is no entry to replace and no kernel to keep reachable. The whole
# swap-and-verify dance this script used to do existed only because the
# layer sat in a separate repo and wanted the idev name for itself.
#
# Nothing is copied. A destination that exists and is not a symlink is
# refused, never overwritten.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
AGENT_SRC="${REPO}/agents"
AGENT_DEST="${HOME}/.claude/agents"

link_one() {
  local src="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [ -L "$dest" ]; then
    if [ "$(readlink "$dest")" = "$src" ]; then
      echo "OK   $dest"
      return 0
    fi
    echo "HEAL $dest (was $(readlink "$dest"))"
    rm -f "$dest"
  elif [ -e "$dest" ]; then
    echo "FAIL $dest exists and is not a symlink (would hide it)" >&2
    return 1
  fi
  ln -sfn "$src" "$dest"
  echo "OK   $dest -> $src"
}

if [ "${1:-}" = "--unlink" ]; then
  for src in "${AGENT_SRC}"/*.md; do
    [ -e "$src" ] || continue
    dest="${AGENT_DEST}/$(basename "$src")"
    if [ -L "$dest" ]; then
      rm -f "$dest"
      echo "GONE $dest"
    elif [ -e "$dest" ]; then
      echo "SKIP $dest is not a symlink; left alone" >&2
    fi
  done
  echo "link-agents PASS (unlinked)"
  exit 0
elif [ $# -gt 0 ]; then
  echo "FAIL unknown flag: $1" >&2
  exit 1
fi

# Never publish a definition set that does not pass its own check: a file
# without name or description is skipped silently by Claude Code, which is
# the worst failure mode to debug.
if ! python3 "${REPO}/scripts/agents-check.py"; then
  echo "link-agents FAIL: fix agents-check first" >&2
  exit 1
fi

fail=0
for src in "${AGENT_SRC}"/*.md; do
  [ -e "$src" ] || continue
  link_one "$src" "${AGENT_DEST}/$(basename "$src")" || fail=1
done

if [ "$fail" -ne 0 ]; then
  echo "link-agents FAIL"
  exit 1
fi
echo "link-agents PASS"
echo "HINT skill:  /idev          导体,随 idev 本身加载,本脚本不碰它"
echo "HINT agent:  @agent-idev-coder / /idev-coder   五个执行者"
echo "HINT 撤销:  bash scripts/link-agents.sh --unlink"
exit 0
