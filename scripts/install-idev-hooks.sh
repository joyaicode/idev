#!/usr/bin/env bash
# Install or remove idev client hooks for Cursor and Claude Code.
# Idempotent: re-running refreshes the idev block; --uninstall strips it.
#
#   bash scripts/install-idev-hooks.sh              # user: ~/.cursor + ~/.claude
#   bash scripts/install-idev-hooks.sh --repo PATH  # project: PATH/.cursor + PATH/.claude
#   bash scripts/install-idev-hooks.sh --uninstall
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
MODE=install
TARGET=user
REPO=""

while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) MODE=uninstall; shift ;;
    --repo) TARGET=repo; REPO="$(cd "$2" && pwd -P)"; shift 2 ;;
    --user) TARGET=user; shift ;;
    -h|--help)
      sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

PY="$(command -v python3)"
PROMPT_LOG="${PY} ${ROOT}/hooks/prompt_log.py"
PRE_TOOL="${PY} ${ROOT}/hooks/pre_tool.py"
SUB_STOP="${PY} ${ROOT}/hooks/subagent_stop.py"
STOP_TRACE="${PY} ${ROOT}/hooks/stop_trace.py"
# An idev entry is known by its hook script, not by the checkout's directory
# name: a kernel cloned as anything but idev/ must still replace its own block.
export IDEV_HOOK_RE='idev/hooks/|/hooks/(prompt_log|pre_tool|subagent_stop|stop_trace)\.py --client '
# subagentStop asks a subagent with no summary to continue; only idev's own
# agents owe a delegation return, so other subagents never see that nudge.
AGENTS_RE="^($("${PY}" -c "import sys; sys.path.insert(0, sys.argv[1]); import kind_agents; print('|'.join(kind_agents.AGENTS))" "${ROOT}/scripts/lib"))\$"

if [ "${TARGET}" = "repo" ]; then
  CURSOR_DIR="${REPO}/.cursor"
  CLAUDE_DIR="${REPO}/.claude"
else
  CURSOR_DIR="${HOME}/.cursor"
  CLAUDE_DIR="${HOME}/.claude"
fi
mkdir -p "${CURSOR_DIR}" "${CLAUDE_DIR}"

MARKER_BEGIN="# >>> idev hooks >>>"
MARKER_END="# <<< idev hooks <<<"

write_cursor() {
  local dest="${CURSOR_DIR}/hooks.json"
  local tmp
  tmp="$(mktemp)"
  if [ "${MODE}" = "uninstall" ]; then
    "${PY}" - "${dest}" "${tmp}" <<'PY'
import json, os, re, sys
from pathlib import Path
ours = re.compile(os.environ["IDEV_HOOK_RE"]).search
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
data = {"version": 1, "hooks": {}}
if src.is_file():
    data = json.loads(src.read_text(encoding="utf-8") or "{}")
hooks = data.setdefault("hooks", {})
for event, entries in list(hooks.items()):
    if not isinstance(entries, list):
        continue
    hooks[event] = [e for e in entries if not ours(str(e.get("command", "")))]
    if not hooks[event]:
        del hooks[event]
dst.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
    mv "${tmp}" "${dest}"
    echo "cursor hooks: stripped idev entries -> ${dest}"
    return
  fi
  "${PY}" - "${dest}" "${tmp}" \
    --prompt-log "${PROMPT_LOG} --client cursor" \
    --pre-tool "${PRE_TOOL} --client cursor" \
    --sub-stop "${SUB_STOP} --client cursor" \
    --sub-stop-matcher "${AGENTS_RE}" \
    --stop-trace "${STOP_TRACE} --client cursor" <<'PY'
import json, os, re, sys
from pathlib import Path
ours = re.compile(os.environ["IDEV_HOOK_RE"]).search
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
# argv after -- : pairs are unused; we read from env-like flags via remaining
args = sys.argv[3:]
cmds = {}
i = 0
while i < len(args):
    if args[i].startswith("--") and i + 1 < len(args):
        cmds[args[i][2:].replace("-", "_")] = args[i + 1]
        i += 2
    else:
        i += 1
data = {"version": 1, "hooks": {}}
if src.is_file():
    try:
        data = json.loads(src.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        data = {"version": 1, "hooks": {}}
if not isinstance(data.get("hooks"), dict):
    data["hooks"] = {}
hooks = data["hooks"]

def drop_idev(entries):
    return [e for e in entries if not ours(str(e.get("command", "")))]

idev = {
    "beforeSubmitPrompt": [{"command": cmds["prompt_log"], "failClosed": False}],
    "preToolUse": [
        {"command": cmds["pre_tool"], "matcher": "Write|Edit|Shell", "failClosed": False},
    ],
    "beforeShellExecution": [
        {"command": cmds["pre_tool"], "failClosed": False},
    ],
    "subagentStop": [{"command": cmds["sub_stop"], "matcher": cmds["sub_stop_matcher"], "failClosed": False}],
    "stop": [{"command": cmds["stop_trace"], "failClosed": False}],
}
for event, entries in idev.items():
    existing = drop_idev(list(hooks.get(event) or []))
    hooks[event] = existing + entries
data["version"] = 1
dst.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  mv "${tmp}" "${dest}"
  echo "cursor hooks: wrote idev block -> ${dest}"
}

write_claude() {
  local dest="${CLAUDE_DIR}/settings.json"
  local tmp
  tmp="$(mktemp)"
  if [ "${MODE}" = "uninstall" ]; then
    "${PY}" - "${dest}" "${tmp}" <<'PY'
import json, os, re, sys
from pathlib import Path
ours = re.compile(os.environ["IDEV_HOOK_RE"]).search
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
data = {}
if src.is_file():
    data = json.loads(src.read_text(encoding="utf-8") or "{}")
hooks = data.get("hooks")
if isinstance(hooks, dict):
    for event, entries in list(hooks.items()):
        if not isinstance(entries, list):
            continue
        cleaned = []
        for block in entries:
            if not isinstance(block, dict):
                continue
            inner = block.get("hooks")
            if isinstance(inner, list):
                block = dict(block)
                block["hooks"] = [
                    h for h in inner
                    if not ours(str((h or {}).get("command", "")))
                ]
                if block["hooks"]:
                    cleaned.append(block)
            elif not ours(str(block.get("command", ""))):
                cleaned.append(block)
        if cleaned:
            hooks[event] = cleaned
        else:
            del hooks[event]
    if not hooks:
        data.pop("hooks", None)
dst.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
    mv "${tmp}" "${dest}"
    echo "claude settings: stripped idev hooks -> ${dest}"
    return
  fi
  "${PY}" - "${dest}" "${tmp}" \
    --prompt-log "${PROMPT_LOG} --client claude" \
    --pre-tool "${PRE_TOOL} --client claude" \
    --sub-stop "${SUB_STOP} --client claude" \
    --stop-trace "${STOP_TRACE} --client claude" <<'PY'
import json, os, re, sys
from pathlib import Path
ours = re.compile(os.environ["IDEV_HOOK_RE"]).search
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
args = sys.argv[3:]
cmds = {}
i = 0
while i < len(args):
    if args[i].startswith("--") and i + 1 < len(args):
        cmds[args[i][2:].replace("-", "_")] = args[i + 1]
        i += 2
    else:
        i += 1
data = {}
if src.is_file():
    try:
        data = json.loads(src.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        data = {}
hooks = data.setdefault("hooks", {})
if not isinstance(hooks, dict):
    hooks = {}
    data["hooks"] = hooks

def drop_idev_blocks(entries):
    out = []
    for block in entries or []:
        if not isinstance(block, dict):
            continue
        inner = block.get("hooks")
        if isinstance(inner, list):
            kept = [h for h in inner if not ours(str((h or {}).get("command", "")))]
            if kept:
                b = dict(block)
                b["hooks"] = kept
                out.append(b)
        elif not ours(str(block.get("command", ""))):
            out.append(block)
    return out

def cmd_hook(command):
    return {"type": "command", "command": command}

idev = {
    "UserPromptSubmit": [{"hooks": [cmd_hook(cmds["prompt_log"])]}],
    "PreToolUse": [
        {"matcher": "Edit|Write|Bash", "hooks": [cmd_hook(cmds["pre_tool"])]},
    ],
    "SubagentStop": [{"hooks": [cmd_hook(cmds["sub_stop"])]}],
    "Stop": [{"hooks": [cmd_hook(cmds["stop_trace"])]}],
}
for event, entries in idev.items():
    hooks[event] = drop_idev_blocks(hooks.get(event)) + entries
dst.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  mv "${tmp}" "${dest}"
  echo "claude settings: wrote idev hooks -> ${dest}"
}

chmod +x "${ROOT}/hooks/"*.py
write_cursor
write_claude
echo "idev hooks ${MODE} done (target=${TARGET})"
if [ "${MODE}" = "install" ]; then
  echo "next: export IDEV_PROMPT_LOG_CHECK=1   # so record --quote must match prompts.log"
fi
