#!/usr/bin/env python3
"""Canon smell detectors shared by the language plugins.

`coding-tables.md` §2 lists 27 smells. Most are judgement calls, but a few
name a shape a regex can actually see. Those are implemented here so the
recall path stops depending on someone remembering to sweep the table.

Why this file exists: `trigger-check.py` guarantees every canon T# is
reachable from a §2 signal or a §4 thought. C# deliberately has no such
guarantee — smells are swept, not triggered. But the sweep itself was never
verified by anything: `delegation.check_boost` passes a report that declares
`TABLE_HIT: none`, no matter what the diff contains. These detectors close
that gap for the subset a machine can judge, and only that subset.

Deliberately NOT implemented, because a false positive here costs more than
a miss (the plugins are advisory warnings a human reads every round):

  C2  `if (有值) 带上; else 省略/默认` — indistinguishable by shape from a
      legitimate optional-field branch.
  C3  two-line pass-through function — needs call-graph knowledge to tell a
      thin adapter from a pointless one.
  C25 domain concept carried as bare string/number — needs to know which
      strings are domain concepts.

Each detector takes text whose comments and string literals are already
blanked by `mask()`, so offsets still line up with the original.
"""
from __future__ import annotations

import re

# The C# this file actually executes. Single source of truth: deep-read-audit.py
# reads it to tell a landed-but-unenforced entry from an enforced one. Adding a
# detector means adding its number here in the same edit.
COVERED = ("C7", "C9", "C12", "C22")

# Shapes deliberately left to the human sweep, with the reason each one resists
# a regex. deep-read-audit.py prints these so "not covered" never reads as
# "nobody looked at it".
DECLINED = {
    "C2": "与合法的可选分支同形，分不出来",
    "C3": "要看调用图才能分清薄适配与无谓转手",
    "C25": "要先知道哪些 string 是领域概念",
}

# C12: canon.md §2「新增函数名含 util / helper / manager / common / data / tmp」
VAGUE = ("util", "utils", "helper", "manager", "common", "data", "tmp")
_VAGUE_RE = re.compile(r"(?i)(?:^|[_\W]|(?<=[a-z0-9]))(%s)(?:$|[_\W]|(?=[A-Z]))" % "|".join(VAGUE))

# C22: a getter chain, not a fluent/stream API. Two or more no-arg get*/is*
# hops followed by another call is the shape canon names:
# `a.getB().getC().doSomething()`. Both cases cover Go's exported `GetB()`.
_CHAIN = re.compile(r"(?:\.\s*(?:[Gg]et|[Ii]s)[A-Z_]\w*\s*\(\s*\)){2,}\s*\.\s*\w+\s*\(")

# C7: a catch that swallows — empty, or returning only an empty collection.
# Scoped to what C7 actually names: `return []` / `{}` / `false`. `null`/`None`
# is deliberately excluded: "not found" is a legitimate result, and treating
# every `except OSError: return None` as a smell buries the real hits.
_EMPTY_RETURN = r"(?:false|\[\]|\{\}|new\s+\w+\s*(?:<[^>]*>)?\s*\(\s*\))"
_SWALLOW_BRACE = re.compile(
    r"catch\s*(?:\([^)]*\)|\w+)?\s*\{\s*(?:return\s+%s\s*;?\s*)?\}" % _EMPTY_RETURN
)
_SWALLOW_PY = re.compile(
    r"(?m)^([ \t]*)except\b[^\n:]*:\s*(?:\n\1[ \t]+)?(?:pass|return\s+(?:\[\]|\{\}|False))\s*$"
)


def mask(text: str, *span_lists: list[tuple[int, int]]) -> str:
    """Blank out comment and string spans, preserving every byte offset."""
    chars = list(text)
    for spans in span_lists:
        for start, end in spans:
            for i in range(max(0, start), min(len(chars), end)):
                if chars[i] != "\n":
                    chars[i] = " "
    return "".join(chars)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _matching_paren(masked: str, close: int) -> int:
    """Index of the `(` matching the `)` at `close`, or -1."""
    depth = 0
    while close >= 0:
        if masked[close] == ")":
            depth += 1
        elif masked[close] == "(":
            depth -= 1
            if depth == 0:
                return close
        close -= 1
    return -1


def _matches_if(masked: str, brace: int) -> bool:
    """True when the `{` at `brace` is the body of an `if`.

    Two shapes, because Go writes `if err != nil {` with no parentheses
    while Java/JS/C write `if (cond) {`. A `} else if` is not a new level:
    the closing brace already popped its own frame.
    """
    i = brace - 1
    while i >= 0 and masked[i].isspace():
        i -= 1
    if i >= 0 and masked[i] == ")":
        start = _matching_paren(masked, i)
        if start < 0:
            return False
        return re.search(r"\bif$", masked[:start].rstrip()) is not None
    line_start = masked.rfind("\n", 0, brace) + 1
    head = masked[line_start:brace]
    return re.match(r"\s*(?:\}\s*else\s+)?if\b", head) is not None


def chain_hits(masked: str, rel: str) -> list[tuple[str, int, str]]:
    """C22 — a caller reaching through two objects to get at a third."""
    return [
        (rel, _line(masked, m.start()), "C22 跨对象链式取值：让直接协作者提供服务方法")
        for m in _CHAIN.finditer(masked)
    ]


def naming_hits(masked: str, rel: str, decl: re.Pattern) -> list[tuple[str, int, str]]:
    """C12 — a function named after no concept. `decl` must capture the name."""
    hits = []
    for m in decl.finditer(masked):
        name = m.group("name")
        vague = _VAGUE_RE.search(name)
        if vague:
            hits.append((
                rel,
                _line(masked, m.start("name")),
                "C12 名字里的「%s」说不出概念：按它做的事命名" % vague.group(1),
            ))
    return hits


def nesting_hits(masked: str, rel: str, limit: int = 2) -> list[tuple[str, int, str]]:
    """C9 — `if` nested deeper than `limit` in a brace language."""
    hits: list[tuple[str, int, str]] = []
    stack: list[bool] = []
    reported: set[int] = set()
    for i, ch in enumerate(masked):
        if ch == "{":
            is_if = _matches_if(masked, i)
            stack.append(is_if)
            line = _line(masked, i)
            if is_if and sum(stack) > limit and line not in reported:
                reported.add(line)
                hits.append((rel, line, "C9 if 嵌套超过两层：抽函数或提前返回"))
        elif ch == "}":
            if stack:
                stack.pop()
    return hits


def nesting_hits_indent(
    masked: str,
    rel: str,
    limit: int = 2,
    statement_lines: set[int] | None = None,
) -> list[tuple[str, int, str]]:
    """C9 for an indentation language: `if` at a third nested level.

    `statement_lines` lets a language plugin hand in AST-verified `if`
    statement lines. Without it the regex is still useful for tests and
    non-Python callers, but Python callers should pass the set: a multiline
    ternary puts `if` on a continuation line and is not a nesting level.
    """
    hits = []
    stack: list[int] = []
    for n, raw in enumerate(masked.splitlines(), 1):
        body = raw.strip()
        if not body:
            continue
        indent = len(raw) - len(raw.lstrip())
        while stack and indent <= stack[-1]:
            stack.pop()
        is_statement = statement_lines is None or n in statement_lines
        if is_statement and re.match(r"(?:el)?if\b", body):
            stack.append(indent)
            if len(stack) > limit:
                hits.append((rel, n, "C9 if 嵌套超过两层：抽函数或提前返回"))
    return hits


def swallow_hits(masked: str, rel: str, python: bool = False) -> list[tuple[str, int, str]]:
    """C7 — a catch/except that turns a failure into an empty value."""
    pattern = _SWALLOW_PY if python else _SWALLOW_BRACE
    return [
        (rel, _line(masked, m.start()), "C7 吞掉失败：该失败就失败，降级要写明条件")
        for m in pattern.finditer(masked)
    ]
