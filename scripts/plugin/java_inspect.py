#!/usr/bin/env python3
"""Java inspection plugin shipped with idev.

problems-scan.sh runs this file and nothing else. It does not install
IntelliJ or a JDK, and it does not download. A clean result means these
rules are quiet on the diff. It does not mean the IDE Problems panel was opened.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import java_hygiene  # noqa: E402

ARM_TYPES = (
    "FileInputStream",
    "FileOutputStream",
    "FileReader",
    "FileWriter",
    "RandomAccessFile",
    "BufferedReader",
    "BufferedWriter",
    "InputStreamReader",
    "OutputStreamWriter",
    "Scanner",
    "ZipFile",
    "JarFile",
)
_ARM = re.compile(
    r"\bnew\s+(?:[\w$]+\.)*(?:%s)\s*\(" % "|".join(ARM_TYPES)
)
_MOD = r"(?:public|protected|private|static|final|synchronized|native|abstract|default|strictfp)"
_SIG = re.compile(
    rf"(?m)^(?P<indent>[ \t]*)"
    rf"(?P<mods>(?:{_MOD}[ \t]+)*)"
    rf"(?P<ret>[\w.<>\[\],?]+)[ \t]+(?P<name>[A-Za-z_]\w*)[ \t]*"
    rf"\((?P<params>[^)]*)\)[ \t]*(?:throws[ \t]+[\w., \t]+)?[ \t]*\{{"
)
_ENTRY = (
    "Override",
    "Test",
    "ParameterizedTest",
    "Before",
    "After",
    "BeforeEach",
    "AfterEach",
    "BeforeAll",
    "AfterAll",
    "SuppressWarnings",
)
_LIT = re.compile(
    r"^(?:-?\d[\d_]*L?|true|false|null|"
    r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)\'|'
    r"[A-Za-z_]\w*(?:\.[A-Z_][A-Z0-9_]*)+)$"
)
_SERIAL = frozenset({"readObject", "writeObject", "readResolve", "writeReplace"})


def _spans(text: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Comment spans and string spans, both exclusive of the closing mark's end."""
    comments: list[tuple[int, int]] = []
    strings: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("//", i):
            j = text.find("\n", i)
            comments.append((i, n if j < 0 else j))
            i = n if j < 0 else j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            end = n if j < 0 else j + 2
            comments.append((i, end))
            i = end
            continue
        if text[i] in "\"'":
            q = text[i]
            start = i
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == "\n":
                    break
                if text[i] == q:
                    i += 1
                    break
                i += 1
            strings.append((start, i))
            continue
        i += 1
    return comments, strings


def _inside(spans: list[tuple[int, int]], pos: int) -> bool:
    return any(start <= pos < end for start, end in spans)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _split_top(blob: str, comma: bool = True) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in blob:
        if ch in "<([{":
            depth += 1
        elif ch in ">)]}":
            depth = max(0, depth - 1)
        if comma and ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _paren(text: str, open_at: int) -> str | None:
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_at + 1:i]
    return None


def _annotations(text: str, pos: int) -> str:
    line_start = text.rfind("\n", 0, pos) + 1
    prev = text[:line_start].rstrip("\n")
    lines = []
    for raw in reversed(prev.splitlines()):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("@"):
            lines.append(stripped)
            continue
        break
    return " ".join(reversed(lines))


def _statement_start(text: str, pos: int) -> int:
    depth = 0
    i = pos - 1
    while i >= 0:
        ch = text[i]
        if ch in ")]}":
            depth += 1
        elif ch in "([{":
            if depth == 0:
                return i
            depth -= 1
        elif ch == ";" and depth == 0:
            return i
        i -= 1
    return 0


def arm_hits(text: str, rel: str) -> list[tuple[str, int, str]]:
    comments, strings = _spans(text)
    hits = []
    for match in _ARM.finditer(text):
        if _inside(comments, match.start()) or _inside(strings, match.start()):
            continue
        start = _statement_start(text, match.start())
        segment = text[start + 1:match.start()]
        before = text[max(0, start - 12):start + 1]
        if re.search(r"\btry\s*\($", before) or re.search(r"\btry\b|\breturn\b", segment):
            continue
        if "=" not in segment:
            continue
        hits.append((rel, _line(text, match.start()), "可以替换为 try-with-resources"))
    return hits


def _param_names(params: str) -> list[str]:
    names = []
    for part in _split_top(params):
        if not part or "..." in part:
            names.append("")
            continue
        tokens = re.findall(r"[A-Za-z_]\w*", part)
        names.append(tokens[-1] if tokens else "")
    return names


def _methods(text: str) -> list[dict]:
    comments, _strings = _spans(text)
    found = []
    for match in _SIG.finditer(text):
        if _inside(comments, match.start("name")):
            continue
        mods = match.group("mods")
        if "abstract" in mods.split() or "private" not in mods.split():
            continue
        name = match.group("name")
        if name in _SERIAL:
            continue
        ann = _annotations(text, match.start())
        if any(tag in ann for tag in _ENTRY):
            continue
        found.append({
            "name": name,
            "name_at": match.start("name"),
            "paren": match.end("name"),
            "params": _param_names(match.group("params")),
            "line": _line(text, match.start("name")),
        })
    return found


def _calls(text: str, name: str, name_at: int) -> list[str]:
    comments, strings = _spans(text)
    args = []
    for match in re.finditer(r"\b%s\s*\(" % re.escape(name), text):
        if match.start() == name_at:
            continue
        if _inside(comments, match.start()) or _inside(strings, match.start()):
            continue
        blob = _paren(text, match.end() - 1)
        if blob is None:
            continue
        args.append(blob)
    return args


def method_hits(text: str, rel: str) -> list[tuple[str, int, str]]:
    methods = _methods(text)
    names = {}
    for method in methods:
        names[method["name"]] = names.get(method["name"], 0) + 1
    hits = []
    for method in methods:
        if names[method["name"]] != 1:
            continue
        calls = _calls(text, method["name"], method["name_at"])
        if not calls and "::%s" % method["name"] not in text:
            hits.append((rel, method["line"], "私有方法没有调用"))
            continue
        params = method["params"]
        if not calls or len(calls) < 2:
            continue
        for index, pname in enumerate(params):
            if not pname:
                continue
            literals = []
            same = True
            for blob in calls:
                parts = _split_top(blob)
                if index >= len(parts) or not _LIT.match(parts[index].strip()):
                    same = False
                    break
                literals.append(parts[index].strip())
            if same and literals and len(set(literals)) == 1:
                hits.append((
                    rel,
                    method["line"],
                    "形参 %s 在每个调用处都是 %s" % (pname, literals[0]),
                ))
    return hits


def inspect_text(text: str, rel: str) -> list[tuple[str, int, str]]:
    return arm_hits(text, rel) + method_hits(text, rel)


def inspect_repo(repo: Path, module: str = "") -> tuple[list[tuple[str, int, str]], str]:
    repo = repo.resolve()
    rels, scope = java_hygiene.changed_java(repo)
    if module:
        rels = [rel for rel in rels if rel == module or rel.startswith(module.rstrip("/") + "/")]
        scope = "%s module %s" % (scope, module)
    hits: list[tuple[str, int, str]] = []
    for rel in rels:
        path = repo / rel
        if not path.is_file():
            continue
        text = java_hygiene._read(path)
        hits.extend(inspect_text(text, rel))
    return hits, scope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("module", nargs="?")
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print("problems: UNPROVEN", file=sys.stderr)
        print("plugin: repo is not a directory", file=sys.stderr)
        return 2
    hits, scope = inspect_repo(args.repo, args.module or "")
    print("plugin: java_inspect.py")
    print("engine: plugin")
    print("scope: %s" % scope)
    if scope.endswith("(0 java)") or " (0 java)" in scope:
        print("problems: no java diff")
        print("convention: 0")
        return 0
    print("convention: %d" % len(hits))
    for rel, line, title in hits[:40]:
        print("%s:%s WARNING %s" % (rel, line, title))
    if len(hits) > 40:
        print("... %d more" % (len(hits) - 40))
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
