"""The page excerpt, include paths, and agent header a step starts from."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import read_ledger
import roots
import safeyaml

_TOOLS = re.compile(r"^tools:\s*(.*)$", re.M)

LIMIT_LINES = 80
LIMIT_CHARS = 4000


def excerpt(path: Path) -> dict | None:
    if not path.is_file():
        return None
    data = path.read_bytes()
    lines = data.decode("utf-8", "replace").splitlines()
    text = "\n".join(lines[:LIMIT_LINES])
    if len(text) > LIMIT_CHARS:
        text = text[:LIMIT_CHARS]
    end = text.count("\n") + 1 if text else 0
    if end < 1:
        return None
    return {"sha256": hashlib.sha256(data).hexdigest(), "end": end, "text": text}


def header(agent: str) -> dict:
    """Stable identity of one executor: definition bytes and declared tools."""
    path = roots.kernel_root() / "agents" / f"{agent}.md"
    if not path.is_file():
        return {"agent": agent, "sha256": "", "tools": ""}
    data = path.read_bytes()
    text = data.decode("utf-8", "replace")
    tools = ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        front = text[3:end] if end != -1 else ""
        match = _TOOLS.search(front)
        if match:
            tools = match.group(1).strip()
    return {"agent": agent, "sha256": hashlib.sha256(data).hexdigest(), "tools": tools}


def includes(ticket: Path) -> list[str]:
    arch = ticket / "arch.yaml"
    data = safeyaml.mapping(arch) if arch.is_file() else {}
    out = []
    for row in (data or {}).get("impact_candidates") or []:
        if isinstance(row, dict) and row.get("include") is True and str(row.get("path") or "").strip():
            out.append(str(row["path"]).strip())
    return out


def attach(brief: dict, ticket: Path, step_id: str) -> dict:
    brief["packet_includes"] = includes(ticket)
    page = Path(str(brief.get("must_read") or ""))
    shown = excerpt(page)
    if not shown:
        return brief
    brief["packet_sha256"] = shown["sha256"]
    brief["packet_end"] = shown["end"]
    brief["packet_text"] = shown["text"]
    read_ledger.note(ticket, step_id, f"{page}:1:{shown['end']}", shown["sha256"])
    return brief
