#!/usr/bin/env python3
"""Every canon rule must be reachable without remembering it exists.

    trigger-check.py [--kernel DIR]

canon.md §3 defines the rules. §2 is the table of signals you can grep out of
a diff or a plan, and §4 is the table of thoughts you have before you type.
Those two are what §2's own heading promises: 「不依赖你"想没想到"」. A rule
that appears in neither is only reachable by someone who already decided to
open it — which is the one case the design was built to remove.

Each rule's own entry carries a TRIGGER line too. That line is not enough on
its own: you only read it after opening the rule.

Two directions are checked:
  - every T# defined in §3 appears in §2 or §4
  - every T# named in §2 or §4 is defined in §3 (a typo points at nothing)

C# is deliberately not checked. Smells are swept, not triggered —
coding.md §0 step 5 scans the whole table on every new function, and Review
step 4 scans it again. That is a different recall path, and demanding
signals for it would be inventing a rule nobody wrote.

Exit 1 on a gap, 0 otherwise.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from product_sink import kernel_root  # noqa: E402

RULE_RE = re.compile(r"^### (T\d+)", re.M)
REF_RE = re.compile(r"\bT\d+\b")


def section(text: str, start: str, end: str = r"\n## ") -> str:
    found = re.search(start, text)
    if not found:
        return ""
    rest = text[found.end():]
    stop = re.search(end, rest)
    return rest[:stop.start()] if stop else rest


def order(name: str) -> int:
    return int(name[1:])


def audit(canon: str) -> tuple[list[str], list[str]]:
    rules = section(canon, r"## 3\. 规则")
    signals = section(canon, r"## 2\. 可观察信号")
    thoughts = section(canon, r"## 4\. 念头触发表")
    defined = {m for m in RULE_RE.findall(rules)}
    reachable = set(REF_RE.findall(signals)) | set(REF_RE.findall(thoughts))
    unreachable = sorted(defined - reachable, key=order)
    dangling = sorted(reachable - defined, key=order)
    return unreachable, dangling


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kernel", default=str(kernel_root()))
    args = ap.parse_args(argv)
    path = Path(args.kernel).expanduser().resolve() / "conventions" / "canon.md"
    try:
        canon = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"trigger-check: {exc}", file=sys.stderr)
        return 2
    unreachable, dangling = audit(canon)
    for name in unreachable:
        print(f"FAIL {name} 在 §2 信号表和 §4 念头表里都没有行 —— "
              f"只有先想到去开它才会被用上", file=sys.stderr)
    for name in dangling:
        print(f"FAIL {name} 被 §2 或 §4 点名，但 §3 没有定义它", file=sys.stderr)
    if unreachable or dangling:
        print("每条规则至少要有一行可 grep 的信号，或一句动手前会冒出来的念头",
              file=sys.stderr)
        return 1
    rules = len(RULE_RE.findall(section(canon, r"## 3\. 规则")))
    print(f"PASS {rules} 条规则都能从 §2 信号或 §4 念头到达")
    return 0


if __name__ == "__main__":
    sys.exit(main())
