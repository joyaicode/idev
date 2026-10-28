#!/usr/bin/env python3
"""beforeSubmitPrompt / UserPromptSubmit: append the person's words to prompts.log.

The log lives under IDEV_DATA (default ~/.idev), outside any product checkout.
Only appends; never rewrites. workflow.py record --quote looks here for the
exact words a person typed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def prompt_text(payload: dict) -> str:
    for key in ("prompt", "text", "content", "message", "user_prompt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    # Cursor sometimes nests the prompt.
    for key in ("input", "request", "data"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = prompt_text(nested)
            if found:
                return found
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", default="cursor", choices=("cursor", "claude"))
    args = parser.parse_args(argv)
    payload = lib.read_stdin()
    text = prompt_text(payload)
    if text.strip():
        lib.append_jsonl(lib.prompts_log(), {
            "at": lib.now_iso(),
            "client": args.client,
            "sha256": lib.sha256_text(text),
            "text": text,
            "cwd": str(Path.cwd()),
            "conversation_id": str(
                payload.get("conversation_id")
                or payload.get("parent_conversation_id")
                or payload.get("session_id")
                or ""
            ),
        })
    return lib.allow()


if __name__ == "__main__":
    raise SystemExit(main())
