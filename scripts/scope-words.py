#!/usr/bin/env python3
"""Flag universal quantifiers in proposals / rule pages (Laziness Protocol sweep).

    scope-words.py <file> [<file> ...]       # per-file line hits
    scope-words.py --check <file> ...        # exit 1 when any hit

Prose rules that say 只有/一律/必须/不得/所有 … carve out scope. Before a
one-off problem is promoted into a general rule or gate (self-evolution's
propose step), the draft should be swept for these words and each hit either
narrowed to the actual scope or kept with a stated reason.

Observation only — a hit is not an error, and this script never edits the
file. --check is for evolve-review drafts and other pipelines that want a
hard signal; plain listing always exits 0.

Learned from joy-dev's check-docs-governance.rb --scope-words; the word list
is the same one, kept here so the kernel does not depend on an external repo.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCOPE_WORDS = (
    "只有", "一律", "全部", "不再", "必须", "不得", "均",
    "所有", "仅", "无一例外",
)


def scan(path: Path) -> list[tuple[int, list[str], str]]:
    """Return (lineno, words, stripped-line) for each line carrying a word."""
    hits: list[tuple[int, list[str], str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"WARN cannot read {path}: {exc}", file=sys.stderr)
        return hits
    for index, line in enumerate(text.splitlines(), start=1):
        found = [word for word in SCOPE_WORDS if word in line]
        if found:
            hits.append((index, found, line.strip()))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="markdown / yaml to sweep")
    parser.add_argument(
        "--check", action="store_true",
        help="exit 1 when any file has a hit (for evolve-review pipelines)",
    )
    args = parser.parse_args(argv)

    total = 0
    for path in args.files:
        if not path.is_file():
            print(f"WARN not a file: {path}", file=sys.stderr)
            continue
        for lineno, words, line in scan(path):
            total += 1
            print(f"{path}:{lineno}: {','.join(words)}\t{line}")

    if total:
        print(
            f"NOTE {total} line(s) carry scope words — a hit narrows or justifies, "
            "it is not an error. PASS here only means no known hard error.",
            file=sys.stderr,
        )
    if args.check and total:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
