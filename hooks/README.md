# idev client hooks

Best-effort guards that run inside Cursor and Claude Code. They are **not**
the security boundary: the record-side checks in `workflow.py` /
`delegation.py` still decide. Hooks catch the common oversteps before they
hit disk.

| Script | Cursor event | Claude event | What it does |
|---|---|---|---|
| `prompt_log.py` | `beforeSubmitPrompt` | `UserPromptSubmit` | Append person text to `$IDEV_DATA/prompts.log` |
| `pre_tool.py` | `preToolUse`, `beforeShellExecution` | `PreToolUse` | Deny signoff-field edits, `git push`, `IDEV_ENGINE=python`, lease-outside writes |
| `subagent_stop.py` | `subagentStop` | `SubagentStop` | Append `modified_files` + always `duration_ms` / `tool_call_count` to `subagent-stops.jsonl` |
| `stop_trace.py` | `stop` | `Stop` | Write a weekly-audit-shaped YAML skeleton (`scenario` / `calls` / `extensions`) |
| `fill_thinking.py` | (CLI) | (CLI) | Conductor replaces the placeholder `thinking.summary` with one real line |
| `timing_coverage.py` | (CLI) | (CLI) | Exit 0 only when subagent-stops timing coverage is 100% |

## Install

```bash
# user-wide (~/.cursor + ~/.claude)
bash scripts/install-idev-hooks.sh

# one product checkout
bash scripts/install-idev-hooks.sh --repo /path/to/product

# remove the idev block only
bash scripts/install-idev-hooks.sh --uninstall
# or: bash scripts/install-idev-hooks.sh --repo /path/to/product --uninstall
```

After install, `record --quote` auto-checks `prompts.log` when that log already
has a recent entry for the current cwd. Force on/off:

```bash
export IDEV_PROMPT_LOG_CHECK=1   # always check
export IDEV_PROMPT_LOG_CHECK=0   # never check (golden / selfcheck)
```

Optional: `export IDEV_REQUIRE_RETURN_JSON=1` to refuse delegation reports that
lack a fenced `json idev-return` block. When a valid block is present it is
already the main path (STATUS/CHANGED/EVIDENCE come from JSON).

## Tests

```bash
python3 scripts/test_hooks.py
python3 scripts/test_delegation_return.py
```
