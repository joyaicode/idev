"""Shared helpers for idev client hooks.

Hooks are best-effort client guards, not the security boundary. They read JSON
on stdin, print JSON on stdout, and exit 0 (ok) or 2 (deny). Other non-zero
exits fail open unless the host sets failClosed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def data_dir() -> Path:
    raw = (os.environ.get("IDEV_DATA") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".idev").resolve()


def prompts_log() -> Path:
    return data_dir() / "prompts.log"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_stdin() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    return data if isinstance(data, dict) else {"_value": data}


def allow(extra: dict | None = None) -> int:
    out: dict[str, Any] = {"permission": "allow"}
    if extra:
        out.update(extra)
    print(json.dumps(out, ensure_ascii=False))
    return 0


def deny(user_message: str, agent_message: str = "") -> int:
    # Both hosts get the verdict, each through the channel it reads:
    # Cursor consumes the stdout JSON; Claude Code's command hook reads the
    # deny reason from stderr (its docs: exit 2 blocks, stderr feeds back
    # to the model). Until 2026-11-17 the reason never reached Claude Code —
    # the deny fired with empty stderr and the host printed a bare
    # "No stderr output", leaving the model to guess which of four refusals
    # it hit. Same JSON, same exit code, one extra line of stderr.
    body = json.dumps({
        "permission": "deny",
        "user_message": user_message,
        "agent_message": agent_message or user_message,
    }, ensure_ascii=False)
    print(body)
    print(user_message, file=sys.stderr)
    return 2


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# Signoff / gate fields a person writes through the CLI. An agent editing these
# with Write/Edit is the path the pre-tool hook blocks.
SIGNOFF_FIELD_RE = (
    r"(?m)^\s*(sealed|accepted|aligned|resolved|reopen_baseline)\s*:"
    r"|semantic_gate\."
    r"|^\s*by\s*:\s*\S+"
    r"|^\s*human_signoff\s*:"
    r"|^\s*signoff\s*:"
)
