#!/usr/bin/env python3
"""JS and Vue inspection plugin shipped with idev.

lang-scan.sh runs this file. It does not install eslint or Node, and it does
not download.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import source_diff  # noqa: E402

# The second "=" of "===" must not count as "==". Same for "!==".
_EQ = re.compile(r"(?<![!=])([=!]=)(?!=)")
_NULL = re.compile(r"^[ \t]*(?:null|undefined)\b")
_VAR = re.compile(r"\bvar[ \t]+[A-Za-z_$]")
_TAG = re.compile(r"<([A-Za-z][\w:-]*)\b[^>]*>")
_ATTR = re.compile(r'=\s*"([^"]*)"')
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def _mask(text: str) -> str:
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("<!--", i):
            j = text.find("-->", i + 4)
            end = n if j < 0 else j + 3
            chunk = text[i:end]
            out.append("".join("\n" if ch == "\n" else " " for ch in chunk))
            i = end
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            end = n if j < 0 else j
            out.append(" " * (end - i))
            i = end
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            end = n if j < 0 else j + 2
            chunk = text[i:end]
            out.append("".join("\n" if ch == "\n" else " " for ch in chunk))
            i = end
            continue
        if text[i] in "\"'`":
            quote = text[i]
            start = i
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                if text[i] == "\n" and quote != "`":
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
    for match in _EQ.finditer(masked):
        after = masked[match.end():]
        if _NULL.match(after):
            continue
        title = "用 ===" if match.group(1) == "==" else "用 !=="
        hits.append((rel, _line(text, match.start()), title))
    for match in _VAR.finditer(masked):
        hits.append((rel, _line(text, match.start()), "用 let 或 const"))
    if rel.endswith(".vue"):
        for match in _TAG.finditer(masked):
            tag = match.group(0)
            if "v-for" not in tag:
                continue
            if ":key" in tag or "v-bind:key" in tag:
                continue
            hits.append((rel, _line(text, match.start()), "v-for 缺少 key"))
        visible = _HTML_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
        for attr in _ATTR.finditer(visible):
            for eq in _EQ.finditer(attr.group(1)):
                if _NULL.match(attr.group(1)[eq.end():]):
                    continue
                title = "用 ===" if eq.group(1) == "==" else "用 !=="
                hits.append((rel, _line(text, attr.start(1) + eq.start()), title))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print("lang: UNPROVEN")
        return 2
    rels, scope = source_diff.changed(
        args.repo,
        (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue"),
        "js",
    )
    print("plugin: js_inspect.py")
    print("engine: plugin")
    print("scope: %s" % scope)
    if not rels:
        print("lang: no js diff")
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
