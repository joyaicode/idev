#!/usr/bin/env python3
"""Python inspection plugin shipped with idev.

lang-scan.sh runs this file. It does not install ruff, pylint, or a Python
toolchain, and it does not download. A clean result means these rules are
quiet on the diff. It does not mean an IDE Problems panel was opened.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import source_diff  # noqa: E402

_NONE = re.compile(r"[=!]=\s*None\b")
_EXCEPT = re.compile(r"(?m)^[ \t]*except[ \t]*:")
_DEF = re.compile(r"(?m)^[ \t]*def[ \t]+\w+[ \t]*\([^)]*\)")
_MUTABLE = re.compile(r"=(?:[ \t]*)(?:\[\]|\{\}|set\(\))")


def _spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("#", i):
            j = text.find("\n", i)
            spans.append((i, n if j < 0 else j))
            i = n if j < 0 else j
            continue
        if text[i] in "\"'":
            quote = text[i]
            triple = text.startswith(quote * 3, i)
            mark = quote * 3 if triple else quote
            start = i
            i += len(mark)
            while i < n:
                if text.startswith(mark, i):
                    i += len(mark)
                    break
                if text[i] == "\\" and not triple:
                    i += 2
                    continue
                i += 1
            spans.append((start, i))
            continue
        i += 1
    return spans


def _inside(spans: list[tuple[int, int]], pos: int) -> bool:
    return any(start <= pos < end for start, end in spans)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def inspect_text(text: str, rel: str) -> list[tuple[str, int, str]]:
    spans = _spans(text)
    hits = []
    for match in _NONE.finditer(text):
        if _inside(spans, match.start()):
            continue
        title = "用 is None" if "==" in match.group(0) else "用 is not None"
        hits.append((rel, _line(text, match.start()), title))
    for match in _EXCEPT.finditer(text):
        if _inside(spans, match.start()):
            continue
        hits.append((rel, _line(text, match.start()), "不要裸 except"))
    for match in _DEF.finditer(text):
        if _inside(spans, match.start()):
            continue
        if _MUTABLE.search(match.group(0)):
            hits.append((rel, _line(text, match.start()), "不要用可变默认参数"))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print("lang: UNPROVEN")
        return 2
    rels, scope = source_diff.changed(args.repo, (".py",), "python")
    print("plugin: python_inspect.py")
    print("engine: plugin")
    print("scope: %s" % scope)
    if not rels:
        print("lang: no python diff")
        print("convention: 0")
        return 0
    hits: list[tuple[str, int, str]] = []
    for rel in rels:
        hits.extend(inspect_text((args.repo / rel).read_text(encoding="utf-8", errors="replace"), rel))
    print("convention: %d" % len(hits))
    for rel, line, title in hits[:40]:
        print("%s:%s WARNING %s" % (rel, line, title))
    if len(hits) > 40:
        print("... %d more" % (len(hits) - 40))
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
