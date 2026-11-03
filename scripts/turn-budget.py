#!/usr/bin/env python3
"""Fail a transcript that stalls the way a person actually waits.

One assistant message is one round. The checks are the ones in SKILL.md
「回合预算」 that a jsonl can decide:

- more than --max tool-only rounds before the first sentence
- more than --max tool-only rounds in a row, including after a sentence
- a Shell whose block_until_ms is over 30000, with no sentence in that
  message or the assistant message just before it
- a command that runs `claude -p` or `agent -p`
- selfcheck, golden record, gate-channel, lease-channel, healthcheck,
  or agent-smoke with block_until_ms over 30000, even after a sentence
- read-only calls spread one per round instead of shared: a segment with
  at least --min-reads of them, averaging under --min-ratio per round that
  carries one. One read per round is the shape a person waits through.

Two transcript shapes are read. The Cursor one has a top-level `role` and
marks segments with <user_query>. The Claude Code one has a top-level
`type`, and every real user message starts a segment. Shell and Bash are
the same tool. A Bash command counts as read-only only when it opens with
a plainly read-only word and carries no redirect or write verb — a script
whose own subcommands decide is left out, because the command line cannot
say, and a miss costs less here than a false alarm.

    python3 scripts/turn-budget.py [--max 8] [<transcript.jsonl>]

With no path it reads this session's own transcript. A check that has to be
handed a path under ~/.claude/projects is a check nobody runs.

Exit 1 when any segment hits one of those. Exit 2 when a named path is not a
file. Exit 0 otherwise, including when there is no transcript to read: having
none is not a budget failure.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import session_transcript  # noqa: E402

QUERY = re.compile(r"<user_query>")
PING = re.compile(r"(?:^|[\s;&|])(?:claude|agent)\s+-p\b")
SUITE = re.compile(
    r"(?:^|[\s;&|])(?:\S*/)?"
    r"(?:selfcheck\.sh|golden/record\.sh|gate-channel\.sh|lease-channel\.sh"
    r"|healthcheck\.sh|agent-smoke\.sh)\b"
)
SHELLS = frozenset({"Shell", "Bash", "shell"})
READ_TOOLS = frozenset({"Read", "Grep", "Glob", "NotebookRead"})
READ_PREFIX = ("mcp__codegraph__", "codegraph_")
READ_CMD = re.compile(
    r"^\s*(?:ls|cat|head|tail|wc|grep|rg|egrep|find|file|stat|du|df|pwd|which|type"
    r"|git\s+(?:status|log|diff|show|branch|remote|ls-files))\b"
)
WRITE_SIGN = re.compile(
    r">>?\s*\S"
    r"|\b(?:rm|mv|cp|mkdir|touch|chmod|chown|ln|tee|install|truncate|dd)\b"
    r"|\bsed\s+-i\b"
    r"|\bgit\s+(?:add|commit|push|checkout|switch|reset|rebase|merge|stash|tag)\b"
)
MIN_READS = 6
MIN_RATIO = 1.5


def readonly(name: str, raw: dict) -> bool:
    """True when this call only looks. Unsure counts as not read-only."""
    if name in READ_TOOLS or name.startswith(READ_PREFIX):
        return True
    if name not in SHELLS:
        return False
    cmd = str(raw.get("command") or raw.get("cmd") or "")
    return bool(READ_CMD.search(cmd)) and not WRITE_SIGN.search(cmd)


def parts(content):
    """Sentences and tool calls in one message, either transcript shape."""
    texts = []
    tools = []
    if isinstance(content, str) and content.strip():
        texts.append(content)
    for item in content if isinstance(content, list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and str(item.get("text") or "").strip():
            texts.append(item["text"])
        elif item.get("type") == "tool_use":
            raw = item.get("input") if isinstance(item.get("input"), dict) else {}
            tools.append((str(item.get("name") or ""), raw))
    return texts, tools


def shell_cmds(tools):
    found = []
    for name, raw in tools:
        if name in SHELLS:
            found.append((str(raw.get("command") or raw.get("cmd") or ""),
                          raw.get("block_until_ms")))
    return found


def is_tool_result(content) -> bool:
    for item in content if isinstance(content, list) else []:
        if isinstance(item, dict) and item.get("type") == "tool_result":
            return True
    return False


def event(obj):
    """One transcript line as (role, starts, texts, tools), or None.

    `starts` says this line opens a segment. Cursor marks that with
    <user_query>; in Claude Code every real user message does, so a tool
    result and a meta line do not.
    """
    role = obj.get("role")
    shape_claude = role is None
    if shape_claude:
        kind = obj.get("type")
        if kind not in ("user", "assistant"):
            return None
        role = kind
    content = (obj.get("message") or {}).get("content")
    if content is None and not shape_claude:
        content = obj.get("content")
    texts, tools = parts(content)
    starts = False
    if role == "user":
        if shape_claude:
            starts = not obj.get("isMeta") and not is_tool_result(content)
        else:
            starts = bool(QUERY.search("\n".join(texts)))
    return role, starts, texts, tools


def load(path: Path):
    """Events from a transcript, oldest first, either shape.

    Reading and parsing live in lib/session_transcript.py so there is one
    answer to what a transcript line is, and one rule for a line that will
    not parse: skip it. A transcript being written to mid-round should still
    be judgeable, and a single torn line is not worth refusing the whole file
    over.
    """
    return [found for found in
            (event(obj) for obj in session_transcript.rows(path)) if found]


def as_ms(value):
    if isinstance(value, bool) or value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def fresh():
    return {
        "on": False, "seg": 0, "silent": 0, "seen": False,
        "streak": 0, "streak_max": 0, "prev_text": False,
        "reads": 0, "read_rounds": 0,
    }


def flush(state, limit, out, min_reads=MIN_READS, min_ratio=MIN_RATIO):
    if not state["on"]:
        return
    seg = state["seg"]
    if state["silent"] > limit:
        out.append(f"silent_before={state['silent']} segment={seg}")
    if state["streak_max"] > limit:
        out.append(f"streak={state['streak_max']} segment={seg}")
    rounds = state["read_rounds"]
    reads = state["reads"]
    if reads >= min_reads and rounds and reads < min_ratio * rounds:
        out.append(f"serial_reads={reads} rounds={rounds} "
                   f"ratio={reads / rounds:.2f} segment={seg}")


def begin(state, limit, out, min_reads, min_ratio):
    nxt = state["seg"] + 1
    flush(state, limit, out, min_reads, min_ratio)
    state.update(fresh())
    state["on"] = True
    state["seg"] = nxt


def note_rounds(state, texts, tools):
    reads = sum(1 for name, raw in tools if readonly(name, raw))
    if reads:
        state["reads"] += reads
        state["read_rounds"] += 1
    if texts:
        state["seen"] = True
        state["streak"] = 0
        return
    if not tools:
        return
    if not state["seen"]:
        state["silent"] += 1
    state["streak"] += 1
    if state["streak"] > state["streak_max"]:
        state["streak_max"] = state["streak"]


def note_shells(state, texts, shells, out):
    seg = state["seg"]
    for cmd, block in shells:
        ms = as_ms(block)
        if PING.search(cmd):
            out.append(f"ping segment={seg}")
        if ms > 30000 and not texts and not state["prev_text"]:
            out.append(f"long_block={ms} segment={seg}")
        if ms > 30000 and SUITE.search(cmd):
            out.append(f"suite_block={ms} segment={seg}")


def on_assistant(state, texts, tools, out):
    if not state["on"]:
        return
    note_rounds(state, texts, tools)
    note_shells(state, texts, shell_cmds(tools), out)
    state["prev_text"] = bool(texts)


def scan(events, limit, min_reads=MIN_READS, min_ratio=MIN_RATIO):
    state = fresh()
    out = []
    for role, starts, texts, tools in events:
        if role == "user" and starts:
            begin(state, limit, out, min_reads, min_ratio)
        elif role == "assistant":
            on_assistant(state, texts, tools, out)
    flush(state, limit, out, min_reads, min_ratio)
    return out


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?",
                        help="transcript jsonl; omitted means this session's own")
    parser.add_argument("--max", type=int, default=8)
    parser.add_argument("--min-reads", type=int, default=MIN_READS,
                        help="read-only calls a segment needs before its ratio is judged")
    parser.add_argument("--min-ratio", type=float, default=MIN_RATIO,
                        help="read-only calls per round that carries one")
    args = parser.parse_args(argv)
    if args.path:
        path = Path(args.path)
        # rows() answers [] for a file it cannot read, which would otherwise
        # turn a wrong path into a cheerful "ok".
        if not path.is_file():
            print(f"turn-budget: {path} is not a file", file=sys.stderr)
            return 2
    else:
        found = session_transcript.newest()
        if found is None:
            print("no transcript for this working directory")
            return 0
        path = found
    found = scan(load(path), args.max, args.min_reads, args.min_ratio)
    if found:
        print("\n".join(found))
        return 1
    print(f"ok max={args.max} min_ratio={args.min_ratio}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except OSError as exc:
        print(f"turn-budget: {exc}", file=sys.stderr)
        sys.exit(2)
