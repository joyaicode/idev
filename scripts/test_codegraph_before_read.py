#!/usr/bin/env python3
"""Code-analysis procedures must update CodeGraph before they read code.

Each case is a procedure section. The first codegraph-sync.sh in that
section must come before the first code-reading instruction.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (file, section start, instructions that read or query code)
CASES = [
    (
        "agents/idev-reviewer.md",
        "## 本步怎么做",
        ["coding-scan.sh", "codegraph_impact"],
    ),
    (
        "agents/idev-coder.md",
        "## 本步怎么做",
        ["codegraph_impact", "coding-scan.sh"],
    ),
    (
        "agents/idev-verifier.md",
        "## kind = verify.plan",
        ["codegraph_impact"],
    ),
    (
        "agents/idev-ops.md",
        "## 共用闭环:假设进台账",
        ["codegraph_impact", "codegraph_context"],
    ),
    (
        "agents/idev-deliver.md",
        "## 需求要落到这个工程上",
        ["codegraph_context", "codegraph_impact", "req-ground.py --feature"],
    ),
    (
        "references/boost.md",
        "### 本地事实工具箱",
        ["codegraph_context", "`Read`"],
    ),
    (
        "SKILL.md",
        "4. 结构问题",
        ["codegraph_context"],
    ),
    (
        "ops/SKILL.md",
        "4. **根因**",
        [],
    ),
]


def locate(text: str, anchor: str, needle: str) -> int:
    start = text.find(anchor)
    if start < 0:
        return -1
    return text.find(needle, start)


def main() -> int:
    failed = 0
    for rel, anchor, reads in CASES:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        sync_at = locate(text, anchor, "codegraph-sync.sh")
        if sync_at < 0:
            print(f"FAIL {rel}: no codegraph-sync.sh after {anchor!r}")
            failed += 1
            continue
        print(f"ok   {rel}: sync present after {anchor}")
        for needle in reads:
            read_at = locate(text, anchor, needle)
            if read_at < 0:
                print(f"FAIL {rel}: missing {needle!r} after {anchor!r}")
                failed += 1
                continue
            if sync_at > read_at:
                print(f"FAIL {rel}: {needle} appears before codegraph-sync.sh")
                failed += 1
            else:
                print(f"ok   {rel}: sync before {needle}")
    if failed:
        print(f"codegraph-before-read FAIL {failed}")
        return 1
    print("codegraph-before-read PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
