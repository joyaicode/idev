#!/usr/bin/env python3
"""Go inspection plugin shipped with idev.

lang-scan.sh runs this file. It does not install golangci-lint or a Go
toolchain, and it does not download.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import source_diff  # noqa: E402


def _mask(text: str) -> str:
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("//", i):
            j = text.find("\n", i)
            end = n if j < 0 else j
            out.append(" " * (end - i))
            i = end
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            end = n if j < 0 else j + 2
            out.append(" " * (end - i))
            i = end
            continue
        if text.startswith("`", i):
            j = text.find("`", i + 1)
            end = n if j < 0 else j + 1
            chunk = text[i:end]
            out.append("".join("\n" if ch == "\n" else " " for ch in chunk))
            i = end
            continue
        if text[i] == '"':
            start = i
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                i += 1
            chunk = text[start:i]
            out.append("".join("\n" if ch == "\n" else " " for ch in chunk))
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def inspect_text(text: str, rel: str) -> list[tuple[str, int, str]]:
    masked = _mask(text)
    hits = []
    stack: list[str] = []
    pending = False
    i = 0
    n = len(masked)
    while i < n:
        if masked.startswith("for", i) and (i == 0 or not masked[i - 1].isalnum()) and (
            i + 3 == n or not masked[i + 3].isalnum()
        ):
            pending = True
            i += 3
            continue
        if masked.startswith("time.Sleep", i) and "for" in stack:
            hits.append((rel, _line(text, i), "循环里的 time.Sleep"))
            i += len("time.Sleep")
            continue
        ch = masked[i]
        if ch == "{":
            stack.append("for" if pending else "block")
            pending = False
        elif ch == "}":
            if stack:
                stack.pop()
            pending = False
        elif pending and ch == "\n":
            pending = False
        i += 1
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print("lang: UNPROVEN")
        return 2
    rels, scope = source_diff.changed(args.repo, (".go",), "go")
    print("plugin: go_inspect.py")
    print("engine: plugin")
    print("scope: %s" % scope)
    if not rels:
        print("lang: no go diff")
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
