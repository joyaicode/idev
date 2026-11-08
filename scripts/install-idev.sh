#!/usr/bin/env bash
# idev one-shot install: skills, agents, hooks, companion skills, codegraph
# hooks, knowledge index — every existing installer in order, then the
# healthcheck verdict.
#
#   bash scripts/install-idev.sh             # install + verify
#   bash scripts/install-idev.sh --verify     # verify only, change nothing
#   bash scripts/install-idev.sh --unlink     # run every installer's --unlink
#
# Design: this script ONLY orchestrates. Each step is an existing installer
# that owns its own idempotence and its own --check/--unlink semantics; the
# one-shot adds no second copy of any install logic (one number, one owner).
# Failure stops the run — a half install is reported as a half install, and
# re-running is safe because every step is idempotent.
#
# Knowledge assets ship with the git checkout (canon / coding-tables /
# 精读缺口 are repo content — clone gets them); the FTS5 index is built at
# install time because a distributed index cannot be hash-verified against
# a moving source (过期即失效 is the design). External dependencies are
# DETECTED and REPORTED, never auto-installed: installing software on
# someone's machine is not this script's authority.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
MODE=install

while [ $# -gt 0 ]; do
  case "$1" in
    --verify) MODE=verify; shift ;;
    --unlink) MODE=unlink; shift ;;
    -h|--help)
      sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

echo "# idev install-idev (mode: ${MODE})"

step() {
  echo
  echo "## $1"
  shift
  "$@"
}

if [ "${MODE}" = "unlink" ]; then
  step "client hooks" bash "${ROOT}/scripts/install-idev-hooks.sh" --uninstall
  step "agents" bash "${ROOT}/scripts/link-agents.sh" --unlink
  # codegraph git hooks own no --uninstall: the marker block
  # (# >>> idev codegraph sync >>>) can be stripped by hand if needed.
  echo "# codegraph git hooks: keep (strip the 'idev codegraph sync' block by hand)"
  echo
  echo "install-idev UNLINK done"
  exit 0
fi

if [ "${MODE}" = "verify" ]; then
  step "agents" bash "${ROOT}/scripts/link-agents.sh" --check
  step "companion skills" bash "${ROOT}/scripts/link-companion-skills.sh" grilling setup-agents-docs
  # 仓外真源技能：缺失只报告不算失败（understand-anything / super-linter
  # 是可选路径；grilling 缺失由上面 link-companion-skills 报 FAIL）。
  for opt_skill in understand-anything super-linter; do
    if [ -e "${HOME}/.cursor/skills/${opt_skill}/SKILL.md" ]; then
      echo "OK   optional skill ${opt_skill}"
    else
      echo "WARN optional skill ${opt_skill} missing (optional; idev runs without it)"
    fi
  done
  step "client hooks" python3 - <<'PY'
import json, os, re, sys
from pathlib import Path
ours = re.compile(r"idev/hooks/|/hooks/(prompt_log|pre_tool|subagent_stop|stop_trace)\.py --client ")
missing = []
for client in ("cursor", "claude"):
    f = Path.home() / f".{client}" / "hooks.json"
    if not f.is_file():
        continue
    hooks = (json.loads(f.read_text(encoding="utf-8")) or {}).get("hooks", {})
    found = [e.get("command", "") for ev in hooks.values() if isinstance(ev, list) for e in ev if ours.search(str(e.get("command", "")))]
    print(f"{client}: {len(found)} idev hook entries")
    if not found:
        missing.append(client)
if missing:
    print("hooks: MISSING for " + ", ".join(missing))
    sys.exit(1)
print("hooks: OK")
PY
  # 外部依赖：检测并报告，不自动安装（装软件不是本脚本的权限）。
  # 缺任何一项都会让某些能力降级，但 install 仍 PASS——降级路径各能力
  # 自带（codegraph 没图不建、python lane 无二进制跑、FTS5 由 stdlib 提供）。
  echo
  echo "## external dependencies (detect + report, never auto-install)"
  dep_missing=0
  check_dep() {
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then
      echo "OK   ${label}"
    else
      echo "MISS ${label} — $2"
      dep_missing=1
    fi
  }
  check_dep "python3"        command -v python3            "scripts need python3 (>=3.9)"
  check_dep "PyYAML"         python3 -c "import yaml"      "pip install --user pyyaml (or -r requirements.txt)"
  check_dep "go toolchain"   sh -c 'command -v go'         "only needed to rebuild bin/idev; python lane runs without"
  check_dep "sqlite3 FTS5"   python3 -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute(\"CREATE VIRTUAL TABLE t USING fts5(x)\")"  "knowledge search needs stdlib sqlite3 with FTS5"
  check_dep "codegraph CLI"  command -v codegraph          "optional; idev skips graph features when absent"
  if [ "${dep_missing}" -ne 0 ]; then
    echo "(missing deps degrade features; install them yourself, then re-run)"
  fi
  echo
  bash "${ROOT}/scripts/healthcheck.sh" >/dev/null && echo "healthcheck PASS" || {
    echo "healthcheck FAIL (run bash scripts/healthcheck.sh for detail)" >&2
    exit 1
  }
  echo
  echo "install-idev VERIFY PASS"
  exit 0
fi

# install mode ---------------------------------------------------------------

step "idev skill aliases (~/.claude, ~/.agents, ~/.joycode)" \
  bash "${ROOT}/scripts/link-idev-aliases.sh"

step "agents -> ~/.claude/agents + ~/.cursor/agents" \
  bash "${ROOT}/scripts/link-agents.sh"

step "companion skills (grilling, setup-agents-docs)" \
  bash "${ROOT}/scripts/link-companion-skills.sh"

step "client hooks (~/.cursor + ~/.claude)" \
  bash "${ROOT}/scripts/install-idev-hooks.sh"

step "codegraph git hooks (this checkout)" \
  bash "${ROOT}/scripts/install-codegraph-hooks.sh"

# 知识资产随 clone 已在仓内；这里只重建本机 FTS5 索引（过期即失效的
# 设计：索引不可分发，只能对着当前真源重建）。idev 自身入库；产品仓
# （joypaas 等）的索引在各仓内首次 search 时自动增量同步，不在此列。
step "knowledge index (idev repo, FTS5 rebuild)" \
  python3 "${ROOT}/scripts/knowledge.py" sync --repo "${ROOT}"

echo
echo "## verify"
bash "$0" --verify
echo
echo "install-idev PASS"
