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
_HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def _hide(visible: list[bool], text: str, start: int, end: int) -> None:
    for i in range(start, min(end, len(text))):
        if text[i] != "\n":
            visible[i] = False


def _matching(text: str, i: int, open_mark: str, close_mark: str) -> int:
    """Index just after the close that matches open_mark at an earlier i. Respects quotes."""
    n = len(text)
    depth = 1
    while i < n and depth:
        if text.startswith("'", i) or text.startswith('"', i):
            quote = text[i]
            i += 1
            while i < n and text[i] != quote:
                if text[i] == "\\" and quote == '"':
                    i += 2
                    continue
                i += 1
            i = min(n, i + 1)
            continue
        if text.startswith(open_mark, i):
            depth += 1
            i += len(open_mark)
            continue
        if text.startswith(close_mark, i):
            depth -= 1
            i += len(close_mark)
            continue
        i += 1
    return i


def _heredoc_end(text: str, mark_at: int) -> int:
    found = _HEREDOC.match(text, mark_at)
    if not found:
        return mark_at
    delim = found.group(2)
    line_end = text.find("\n", found.end())
    if line_end < 0:
        return len(text)
    k = line_end + 1
    while k <= len(text):
        nxt = text.find("\n", k)
        line = text[k: len(text) if nxt < 0 else nxt]
        if line.strip() == delim:
            return len(text) if nxt < 0 else nxt
        if nxt < 0:
            return len(text)
        k = nxt + 1
    return len(text)


def _mask(text: str) -> str:
    """Blank the places where an unquoted expansion is not word-split.

    Double quotes stay closed across $(...) so "${var}" inside a substitution
    is not reported. Heredoc bodies, [[ ]], and $(( )) do not word-split.
    """
    n = len(text)
    visible = [True] * n

    def parse(i: int, paren: int, in_dquote: bool) -> int:
        while i < n:
            if text[i] == "\\":
                _hide(visible, text, i, min(n, i + 2))
                i += 2 if i + 1 < n else 1
                continue
            if not in_dquote and text[i] == "'":
                j = text.find("'", i + 1)
                j = n if j < 0 else j + 1
                _hide(visible, text, i, j)
                i = j
                continue
            if text[i] == '"':
                if in_dquote:
                    return i + 1
                i = parse(i + 1, 0, True)
                continue
            if not in_dquote and text[i] == "#":
                j = text.find("\n", i)
                j = n if j < 0 else j
                _hide(visible, text, i, j)
                i = j
                continue
            if not in_dquote and text.startswith("<<", i) and _HEREDOC.match(text, i):
                j = _heredoc_end(text, i)
                _hide(visible, text, i, j)
                i = j
                continue
            if not in_dquote and text.startswith("[[", i):
                j = _matching(text, i + 2, "[[", "]]")
                _hide(visible, text, i, j)
                i = j
                continue
            if not in_dquote and text.startswith("((", i):
                j = _matching(text, i + 2, "((", "))")
                _hide(visible, text, i, j)
                i = j
                continue
            if text.startswith("$((", i):
                j = _matching(text, i + 2, "(", ")")
                _hide(visible, text, i, j)
                i = j
                continue
            if text.startswith("$(", i):
                i = parse(i + 2, 1, False)
                continue
            if text[i] == "`":
                i += 1
                while i < n and text[i] != "`":
                    if text[i] == "'":
                        j = text.find("'", i + 1)
                        j = n if j < 0 else j + 1
                        _hide(visible, text, i, j)
                        i = j
                        continue
                    if text[i] == '"':
                        i = parse(i + 1, 0, True)
                        continue
                    if text.startswith("$(", i):
                        i = parse(i + 2, 1, False)
                        continue
                    i += 1
                i = min(n, i + 1)
                continue
            if in_dquote and text[i] == "$" and not text.startswith("$(", i):
                j = i + 1
                if j < n and text[j] == "{":
                    end = text.find("}", j)
                    j = n if end < 0 else end + 1
                elif j < n and text[j] in "@*#?!-_$" or text[j].isdigit():
                    j += 1
                else:
                    while j < n and (text[j].isalnum() or text[j] == "_"):
                        j += 1
                _hide(visible, text, i, j)
                i = j
                continue
            if text[i] == "(" and paren > 0 and not in_dquote:
                paren += 1
                i += 1
                continue
            if text[i] == ")" and paren > 0 and not in_dquote:
                paren -= 1
                i += 1
                if paren == 0:
                    return i
                continue
            i += 1
        return i

    parse(0, 0, False)
    return "".join(text[i] if visible[i] else ("\n" if text[i] == "\n" else " ") for i in range(n))


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


def _disabled(text: str, pos: int) -> bool:
    """A shellcheck SC2086 disable covers this expansion, including a continued line."""
    lines = text.splitlines()
    number = _line(text, pos)
    index = number - 1
    if 0 <= index < len(lines) and "SC2086" in lines[index]:
        return True
    steps = 0
    while index > 0 and steps < 6:
        prev = lines[index - 1]
        if "SC2086" in prev:
            return True
        if prev.rstrip().endswith("\\") or prev.strip().startswith("#") or not prev.strip():
            index -= 1
            steps += 1
            continue
        return False
    return False


def inspect_text(text: str, rel: str) -> list[tuple[str, int, str]]:
    masked = _mask(text)
    hits = []
    for match in _EXP.finditer(masked):
        if _assignment(masked, match.start()):
            continue
        if _disabled(text, match.start()):
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
