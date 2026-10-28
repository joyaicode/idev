#!/usr/bin/env python3
"""subagentStop / SubagentStop: append facts to IDEV_DATA/subagent-stops.jsonl.

Every row carries duration_ms and tool_call_count (0 when the host omitted
them) so timing coverage of the log is 100%. delegation.py copies the latest
row into the record; CHANGED must be ⊆ modified_files.
"""
from __future__ import annotations

import argparse
import json
import sys
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
        "at": lib.now_iso(),
        "client": args.client,
        "status": str(payload.get("status") or ""),
        "subagent_type": str(payload.get("subagent_type") or payload.get("subagentType") or ""),
        "duration_ms": as_int(payload.get("duration_ms") or payload.get("durationMs"), 0),
        "tool_call_count": as_int(
            payload.get("tool_call_count") or payload.get("toolCallCount"), 0
        ),
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
