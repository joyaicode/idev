#!/usr/bin/env bash
# Expose idev's five execution agents to Claude Code and Cursor.
#
#   link-agents.sh            agents/*.md -> ~/.claude/agents/ and ~/.cursor/agents/
#   link-agents.sh --unlink   remove them
#   link-agents.sh --check    report what is installed, change nothing
#
# Both locations get the same symlinks, on purpose. Cursor is documented to
# read ~/.claude/agents/ as a compatibility location, but that is a claim
# about someone else's software that this repo has never verified on a real
# Cursor install (references/agents-todo.md P0). Installing to its own
# ~/.cursor/agents/ as well costs one extra symlink per agent and removes
# the dependency on an unverified behaviour.
#
# A name clash resolves to ~/.cursor/agents/ in Cursor's own precedence
# order, and both paths point at the same file here, so the duplication
# cannot produce two different definitions.
#
# The /idev skill needs nothing from this script. idev is already a skill at
# ~/.cursor/skills/idev, and the agent layer now lives inside it — so there
# is no entry to replace and no kernel to keep reachable.
#
# Nothing is copied. A destination that exists and is not a symlink is
# refused, never overwritten.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
AGENT_SRC="${REPO}/agents"
# Claude Code first (its native location), then Cursor's own.
AGENT_DESTS=("${HOME}/.claude/agents" "${HOME}/.cursor/agents")

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

if [ "${1:-}" = "--check" ]; then
  miss=0
  for dest_dir in "${AGENT_DESTS[@]}"; do
    echo "## $dest_dir"
    for src in "${AGENT_SRC}"/*.md; do
      [ -e "$src" ] || continue
      dest="${dest_dir}/$(basename "$src")"
      if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$src" ]; then
        echo "  OK   $(basename "$src")"
      elif [ -L "$dest" ]; then
        echo "  DRIFT $(basename "$src") -> $(readlink "$dest")"
        miss=1
      elif [ -e "$dest" ]; then
        echo "  BLOCK $(basename "$src") exists and is not a symlink"
        miss=1
      else
        echo "  MISS $(basename "$src")"
        miss=1
      fi
    done
  done
  echo
  if [ "$miss" -ne 0 ]; then
    echo "link-agents CHECK: 有未安装或漂移项 —— 跑 bash scripts/link-agents.sh"
    exit 1
  fi
  echo "link-agents CHECK PASS (both locations)"
  exit 0
elif [ "${1:-}" = "--unlink" ]; then
  for dest_dir in "${AGENT_DESTS[@]}"; do
    for src in "${AGENT_SRC}"/*.md; do
      [ -e "$src" ] || continue
      dest="${dest_dir}/$(basename "$src")"
      if [ -L "$dest" ]; then
        rm -f "$dest"
        echo "GONE $dest"
      elif [ -e "$dest" ]; then
        echo "SKIP $dest is not a symlink; left alone" >&2
      fi
    done
  done
  echo "link-agents PASS (unlinked)"
  exit 0
elif [ $# -gt 0 ]; then
  echo "FAIL unknown flag: $1" >&2
  echo "     用法: link-agents.sh [--check|--unlink]" >&2
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
count=0
for dest_dir in "${AGENT_DESTS[@]}"; do
  for src in "${AGENT_SRC}"/*.md; do
    [ -e "$src" ] || continue
    link_one "$src" "${dest_dir}/$(basename "$src")" || fail=1
    count=$((count + 1))
  done
done

if [ "$fail" -ne 0 ]; then
  echo "link-agents FAIL"
  exit 1
fi
echo "link-agents PASS  ($count 个链接,两个位置)"
echo "HINT skill:   /idev          导体,随 idev 本身加载,本脚本不碰它"
echo "HINT Claude:  @agent-idev-coder   或让它按 DELEGATE 行自己派"
echo "HINT Cursor:  /idev-coder        五个执行者"
echo "HINT 核对:   bash scripts/link-agents.sh --check"
echo "HINT 撤销:   bash scripts/link-agents.sh --unlink"
exit 0
