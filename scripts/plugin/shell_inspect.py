#!/usr/bin/env python3
"""Shell inspection plugin shipped with idev.

lang-scan.sh runs this file. It does not install shellcheck and it does not
download.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import source_diff  # noqa: E402

_EXP = re.compile(r"\$\{[A-Za-z0-9_]+\}|\$[A-Za-z_][A-Za-z0-9_]*|\$[0-9]|\$[@*]")


def _mask(text: str) -> str:
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("#", i):
            j = text.find("\n", i)
            end = n if j < 0 else j
            out.append(" " * (end - i))
            i = end
            continue
        if text[i] in "\"'":
            quote = text[i]
            start = i
            i += 1
            while i < n:
                if text[i] == "\\" and quote == '"':
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                if text[i] == "\n":
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


def _assignment(masked: str, pos: int) -> bool:
    line_start = masked.rfind("\n", 0, pos) + 1
    prefix = masked[line_start:pos]
    return re.search(
        r"(?:^|[;&|(])[ \t]*(?:(?:local|export|readonly|declare|typeset)[ \t]+)?"
        r"[A-Za-z_][A-Za-z0-9_]*[ \t]*=[ \t]*$",
        prefix,
    ) is not None


def inspect_text(text: str, rel: str) -> list[tuple[str, int, str]]:
    masked = _mask(text)
    hits = []
    for match in _EXP.finditer(masked):
        if _assignment(masked, match.start()):
            continue
        hits.append((rel, _line(text, match.start()), "变量没有加引号"))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print("lang: UNPROVEN")
        return 2
    rels, scope = source_diff.changed(args.repo, (".sh", ".bash"), "shell")
    print("plugin: shell_inspect.py")
    print("engine: plugin")
    print("scope: %s" % scope)
    if not rels:
        print("lang: no shell diff")
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
