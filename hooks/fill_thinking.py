#!/usr/bin/env python3
"""Replace the placeholder thinking.summary on a stop-hook skeleton.

    python3 hooks/fill_thinking.py --skeleton PATH --summary 'one line'
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PLACEHOLDER = "CONDUCTOR: replace with one thinking line"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args(argv)
    path = Path(args.skeleton)
    if not path.is_file():
        print(f"BLOCKED no skeleton: {path}", file=sys.stderr)
        return 2
    summary = " ".join(args.summary.split())
    if not summary:
        print("BLOCKED --summary is empty", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")
    if "thinking:" not in text:
        print("BLOCKED skeleton has no thinking block", file=sys.stderr)
        return 2
    updated, n = re.subn(
        r'(?m)^([ \t]+summary:\s*)".*"\s*$',
        rf'\1"{summary}"',
        text,
        count=1,
    )
    if n != 1:
        print("BLOCKED could not find thinking.summary to replace", file=sys.stderr)
        return 2
    path.write_text(updated, encoding="utf-8")
    print(f"OK  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
