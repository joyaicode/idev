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

    python3 scripts/turn-budget.py [--max 8] <transcript.jsonl>

Exit 1 when any <user_query> segment hits one of those. Exit 0 otherwise.
Whether several reads share one message is not a pass/fail condition.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

QUERY = re.compile(r"<user_query>")
PING = re.compile(r"(?:^|[\s;&|])(?:claude|agent)\s+-p\b")
SUITE = re.compile(
    r"(?:^|[\s;&|])(?:\S*/)?"
    r"(?:selfcheck\.sh|golden/record\.sh|gate-channel\.sh|lease-channel\.sh"
    r"|healthcheck\.sh|agent-smoke\.sh)\b"
)


def parts(content):
    texts = []
    tools = 0
    if isinstance(content, str) and content.strip():
        texts.append(content)
    for item in content if isinstance(content, list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and str(item.get("text") or "").strip():
            texts.append(item["text"])
        elif item.get("type") == "tool_use":
            tools += 1
    return texts, tools


def shell_cmds(content):
    found = []
    for item in content if isinstance(content, list) else []:
        if not isinstance(item, dict) or item.get("type") != "tool_use":
            continue
        if item.get("name") != "Shell":
            continue
        raw = item.get("input") if isinstance(item.get("input"), dict) else {}
        found.append((str(raw.get("command") or ""), raw.get("block_until_ms")))
    return found


def load(path: Path):
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        content = (obj.get("message") or {}).get("content")
        texts, tools = parts(content)
        events.append((obj.get("role") or "", texts, tools, shell_cmds(content)))
    return events


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
    }


def flush(state, limit, out):
    if not state["on"]:
        return
    seg = state["seg"]
    if state["silent"] > limit:
        out.append(f"silent_before={state['silent']} segment={seg}")
    if state["streak_max"] > limit:
        out.append(f"streak={state['streak_max']} segment={seg}")


def begin(state, limit, out):
    nxt = state["seg"] + 1
    flush(state, limit, out)
    state.update(fresh())
    state["on"] = True
    state["seg"] = nxt


def note_rounds(state, texts, tools):
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


def on_assistant(state, texts, tools, shells, out):
    if not state["on"]:
        return
    note_rounds(state, texts, tools)
    note_shells(state, texts, shells, out)
    state["prev_text"] = bool(texts)


def scan(events, limit):
    state = fresh()
    out = []
    for role, texts, tools, shells in events:
        if role == "user" and QUERY.search("\n".join(texts)):
            begin(state, limit, out)
        elif role == "assistant":
            on_assistant(state, texts, tools, shells, out)
    flush(state, limit, out)
    return out


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--max", type=int, default=8)
    args = parser.parse_args(argv)
    found = scan(load(Path(args.path)), args.max)
    if found:
        print("\n".join(found))
        return 1
    print(f"ok max={args.max}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"turn-budget: {exc}", file=sys.stderr)
        sys.exit(2)
