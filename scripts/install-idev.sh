#!/usr/bin/env bash
# idev one-shot install: skills, agents, hooks, companion skills, codegraph
# hooks — every existing installer in order, then the healthcheck verdict.
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

echo
echo "## verify"
bash "$0" --verify
echo
echo "install-idev PASS"
