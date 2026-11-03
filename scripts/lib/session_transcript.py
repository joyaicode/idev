#!/usr/bin/env python3
"""Where this session's own transcript is, and what it says.

The client writes one jsonl per session under its project folder. That folder
is named for the working directory with both separators and dots turned into
dashes — `coding.jd.com/joypaas` becomes `coding-jd-com-joypaas`. Only
replacing the slashes misses every repo with a dot in its name, which is most
of them. The newest jsonl in that folder is the session running now.

A client that keeps no such file simply has none. Callers read that as "no
answer" and carry on: a check that cannot see a transcript must not become a
check that fails.

Only the Claude Code layout is located here. turn-budget.py reads the Cursor
transcript shape too, but where Cursor keeps its file is not something this
module knows — hand those in by path.

    python3 scripts/lib/session_transcript.py        # prints the path, or nothing
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

CTX_FIELDS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
_PARSED: dict[tuple[str, int, float], list[dict]] = {}


def slug(cwd: Path | None = None) -> str:
    return re.sub(r"[/.]", "-", str((cwd or Path.cwd()).resolve()))


def folder(cwd: Path | None = None) -> Path:
    return Path.home() / ".claude" / "projects" / slug(cwd)


def newest(cwd: Path | None = None) -> Path | None:
    """This session's transcript, or None when the client keeps no such file."""
    try:
        files = [p for p in folder(cwd).glob("*.jsonl") if p.is_file()]
    except OSError:
        return None
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def rows(path: Path | None) -> list[dict]:
    """A transcript's parsed lines, cached for this process.

    One round asks the same file several things — how many rounds, which pages
    were opened, what the person last said. A transcript runs to megabytes, so
    parsing it once per question is waste. Size and mtime are part of the key,
    so a file that grew mid-round is not served stale; only the newest answer
    is kept, because one transcript at a time is all anyone asks about.
    """
    if path is None:
        return []
    try:
        info = path.stat()
        key = (str(path), info.st_size, info.st_mtime)
    except OSError:
        return []
    hit = _PARSED.get(key)
    if hit is not None:
        return hit
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    parsed: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            parsed.append(obj)
    _PARSED.clear()
    _PARSED[key] = parsed
    return parsed


def when(obj: dict) -> dt.datetime | None:
    raw = str(obj.get("timestamp") or "").strip()
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def rounds(path: Path | None) -> tuple[int, int]:
    """Assistant rounds in a transcript, and the context size of the last one.

    `None` means there is no transcript, and answers (0, 0). Asking about this
    session is `session()`: a caller that already looked and found nothing must
    not be handed the current conversation in its place.
    """
    count = 0
    ctx = 0
    for obj in rows(path):
        if obj.get("type") != "assistant":
            continue
        count += 1
        usage = (obj.get("message") or {}).get("usage") or {}
        size = sum(int(usage.get(key) or 0) for key in CTX_FIELDS)
        if size:
            ctx = size
    return count, ctx


def session(cwd: Path | None = None) -> tuple[int, int]:
    """This session's rounds.

    The conversation running now, not the folder's history: a directory whose
    newest transcript is an empty session answers 0, which is the right answer
    to "how long has this one gone on".
    """
    return rounds(newest(cwd))


def tool_uses(path: Path | None,
              since: dt.datetime | None = None,
              until: dt.datetime | None = None) -> list[tuple[str, dict]]:
    """Every tool call in a transcript as (name, input), oldest first.

    A line whose timestamp cannot be read stays in: dropping a call that
    really happened is worse than keeping one from a neighbouring round.
    Callers get the raw name and input — what a given tool means is theirs
    to decide, not this module's.
    """
    out: list[tuple[str, dict]] = []
    for obj in rows(path):
        if obj.get("type") != "assistant":
            continue
        stamp = when(obj)
        if stamp is not None:
            if since is not None and stamp <= since:
                continue
            if until is not None and stamp > until:
                continue
        for block in (obj.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            raw = block.get("input")
            out.append((str(block.get("name") or ""),
                        raw if isinstance(raw, dict) else {}))
    return out


def last_prompt(path: Path | None) -> str:
    """The person's most recent words in a transcript, or "".

    A tool result is not the person talking, and neither is a meta line, so
    both are skipped on the way back. The words come out as written; what to
    do about length or newlines is the caller's call.
    """
    for obj in reversed(rows(path)):
        if obj.get("type") != "user" or obj.get("isMeta"):
            continue
        content = (obj.get("message") or {}).get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            spoken = "\n".join(
                str(block.get("text") or "") for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
            if spoken.strip():
                return spoken
    return ""


if __name__ == "__main__":
    found = newest()
    if found:
        print(found)
    else:
        sys.exit(1)
