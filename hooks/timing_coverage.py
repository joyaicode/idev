#!/usr/bin/env python3
"""Report timing coverage of IDEV_DATA/subagent-stops.jsonl.

Every row must carry numeric duration_ms and tool_call_count (phase 1 §4).
Exit 0 only when coverage is 100% (or the log is empty / missing).

    python3 hooks/timing_coverage.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def coverage(path: Path | None = None) -> dict:
    path = path or (lib.data_dir() / "subagent-stops.jsonl")
    if not path.is_file():
        return {"rows": 0, "ok": 0, "coverage": 1.0, "missing": []}
    rows = 0
    ok = 0
    missing = []
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        rows += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            missing.append(f"line {i}: not json")
            continue
        dur = row.get("duration_ms")
        tools = row.get("tool_call_count")
        if isinstance(dur, (int, float)) and isinstance(tools, (int, float)):
            ok += 1
        else:
            missing.append(f"line {i}: duration_ms={dur!r} tool_call_count={tools!r}")
    return {
        "rows": rows,
        "ok": ok,
        "coverage": 1.0 if rows == 0 else round(ok / rows, 4),
        "missing": missing,
    }


def main() -> int:
    got = coverage()
    print(json.dumps(got, ensure_ascii=False))
    if got["coverage"] < 1.0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
