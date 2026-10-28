#!/usr/bin/env python3
"""subagentStop / SubagentStop: append facts to IDEV_DATA/subagent-stops.jsonl.

Every row carries duration_ms and tool_call_count (0 when the host omitted
them) so timing coverage of the log is 100%. delegation.py copies into a
record the row of that record's own agent and workspace, found by id so no
row serves two records; CHANGED must be ⊆ modified_files.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def as_int(value, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", default="cursor", choices=("cursor", "claude"))
    args = parser.parse_args(argv)
    payload = lib.read_stdin()
    modified = as_list(
        payload.get("modified_files")
        or payload.get("modifiedFiles")
        or payload.get("files_modified")
    )
    row = {
        "id": uuid.uuid4().hex,
        "at": lib.now_iso(),
        "client": args.client,
        "status": str(payload.get("status") or ""),
        "subagent_type": str(payload.get("subagent_type") or payload.get("subagentType") or ""),
        "description": str(payload.get("description") or "")[:200],
        "duration_ms": as_int(payload.get("duration_ms") or payload.get("durationMs"), 0),
        "tool_call_count": as_int(
            payload.get("tool_call_count") or payload.get("toolCallCount"), 0
        ),
        "message_count": as_int(payload.get("message_count") or payload.get("messageCount"), 0),
        "loop_count": as_int(payload.get("loop_count") or payload.get("loopCount"), 0),
        "workspace_roots": as_list(payload.get("workspace_roots") or payload.get("workspaceRoots")),
        "conversation_id": str(payload.get("conversation_id") or payload.get("session_id") or ""),
        "generation_id": str(payload.get("generation_id") or ""),
        "model": str(payload.get("model") or ""),
        "modified_files": modified,
        "transcript": str(
            payload.get("agent_transcript_path")
            or payload.get("transcript_path")
            or payload.get("agentTranscriptPath")
            or ""
        ),
        "task": str(payload.get("task") or "")[:500],
    }
    lib.append_jsonl(lib.data_dir() / "subagent-stops.jsonl", row)
    out = {"ok": True, "duration_ms": row["duration_ms"], "tool_call_count": row["tool_call_count"]}
    if not str(payload.get("summary") or "").strip():
        out["followup_message"] = (
            "idev: subagent stopped without a summary; "
            "submit the delegation return (CHANGED / CONCLUSION) before the conductor records"
        )
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
