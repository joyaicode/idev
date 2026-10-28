#!/usr/bin/env python3
"""Report add/delete line budget for a kernel window (phase 2 §5).

    deletion-budget.py [--since HEAD~20] [--json]

Counts only tracked source under scripts/ agents/ references/ workflows/
hooks/ cmd/ internal/ — not generatedverify, golden fixtures, or state/.
Exit 0 always; prints the ratio. A ratio above 2.0 is a WARN, not a gate.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHS = ("scripts", "agents", "references", "workflows", "hooks", "cmd", "internal", "ops", "deliver", "verify")


def diff_numstat(since: str) -> tuple[int, int]:
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--numstat", since, "HEAD", "--", *PATHS],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return 0, 0
    added = deleted = 0
    for line in proc.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        a, d = parts[0], parts[1]
        if a.isdigit():
            added += int(a)
        if d.isdigit():
            deleted += int(d)
    return added, deleted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default="HEAD~30")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    added, deleted = diff_numstat(args.since)
    ratio = None if deleted == 0 else round(added / deleted, 2)
    warn = ratio is not None and ratio > 2.0
    report = {
        "since": args.since,
        "added": added,
        "deleted": deleted,
        "add_delete_ratio": ratio,
        "warn_above_2": warn,
        "budget": "each kernel iteration should delete at least as many prompt/rule lines as it adds",
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"# deletion-budget since={args.since}")
        print(f"added={added} deleted={deleted} ratio={ratio}")
        if warn:
            print("WARN ratio > 2.0 — prefer a delete pass before the next kernel growth")
        elif deleted == 0 and added > 0:
            print("WARN no deletions in window — curator --apply and usage-scan are owed")
        else:
            print("OK within or near 2:1 budget (informational)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
