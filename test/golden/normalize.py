#!/usr/bin/env python3
"""Make a recorded command output comparable across runs and machines.

A golden file is worthless if it also records the clock, the temp directory
and a random id — every replay would differ for reasons that have nothing to
do with behaviour. These substitutions are the contract between the Python
recording and the Go replay (design §20.4), so both sides must apply exactly
this list, in this order.

    python3 normalize.py --work /tmp/xxx --idev /path/to/idev < raw > clean
"""
from __future__ import annotations

import argparse
import re
import sys

# Order matters: longer, more specific patterns first, so a timestamp inside
# a filename is not half-replaced by the bare-timestamp rule.
RULES = (
    # run-20261015-203344.yaml -> run-<TS>.yaml (rotated run files)
    (re.compile(r"run-\d{8}-\d{6}\.yaml"), "run-<TS>.yaml"),
    # 20261015-001.yaml -> <DATE>-<NNN>.yaml (trace round names)
    (re.compile(r"\b\d{8}-\d{3}\.yaml\b"), "<DATE>-<NNN>.yaml"),
    # 2026-10-15T20:33:44+08:00 / ...Z / ...  -> <TS>
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<TS>"),
    # A ULID is 26 Crockford base32 characters starting with a digit.
    (re.compile(r"\b[0-7][0-9A-HJKMNP-TV-Z]{25}\b"), "<ULID>"),
    # 3m05s / 185s -> <DUR>
    (re.compile(r"\b\d+m\d{2}s\b"), "<DUR>"),
)


def normalize(text: str, work: str = "", idev: str = "") -> str:
    # Paths first and longest-first, so a scratch dir inside /tmp does not
    # get partly rewritten by a shorter prefix.
    for value, token in sorted(
        [(work, "$WORK"), (idev, "$IDEV")], key=lambda p: len(p[0]), reverse=True
    ):
        if value:
            text = text.replace(value, token)
    for pattern, token in RULES:
        text = pattern.sub(token, text)
    return text


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", default="", help="scratch dir to replace with $WORK")
    parser.add_argument("--idev", default="", help="kernel root to replace with $IDEV")
    args = parser.parse_args(argv)
    sys.stdout.write(normalize(sys.stdin.read(), args.work, args.idev))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
