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
COVERED = ("C1", "C7", "C9", "C12", "C22")

# coding-tables.md §2.4 quantitative thresholds the plugins can carry. The
# same numbers appear in the table; they live here once so a threshold change
# is one edit, not five.
FUNC_LINE_LIMIT = 20
PARAM_LIMIT = 3
COMPLEXITY_LIMIT = 10

# Shapes deliberately left to the human sweep, with the reason each one resists
# a regex. deep-read-audit.py prints these so "not covered" never reads as
# "nobody looked at it".
DECLINED = {
    "C2": "与合法的可选分支同形，分不出来",
    "C3": "要看调用图才能分清薄适配与无谓转手",
    "C25": "要先知道哪些 string 是领域概念",
    "C32": "要先知道方法是否可覆写（virtual / final / private），正则分不出来",
    "C33": "要先知道循环不变式是否已写出（语义层面），正则分不出来",
    "C34": "要先知道闭包/goroutine/defer 是否捕获了循环变量（语义层面），正则分不出来",
    "C35": "要先知道表达式是否依赖隐式优先级/求值顺序（语义层面），正则分不出来",
    "C36": "要先知道 `=` 是赋值还是比较（语义层面，且合法赋值在条件里也常见），正则分不出来",
    "C37": "要先知道整数运算是否可能溢出（类型与值域层面），正则分不出来",
    "C38": "要先知道代码在库/模块还是入口（调用层级），正则分不出来",
    "C39": "要先知道类型是否持有资源/身份/锁（值语义 vs 引用语义，语义层面），正则分不出来",
    "C40": "要先知道内层声明是否遮蔽了外层同名变量/字段（作用域与命名层面），正则分不出来",
    "重复代码": "§2.4 的三次重复要跨文件比对相似度，正则判不了（与 C3 同类），靠 §0 第 5 步扫表",
    "箭头函数阈值": "跨行箭头函数的边界正则判不稳，JS/TS 只判 function 声明",
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


# --- §2.4 quantitative thresholds -------------------------------------------
#
# The four function-level thresholds from coding-tables.md §2.4. They land on
# C1 (length / params — the table itself says 多为「并且」职责 → C1 拆开) and
# C1/P5 (complexity — 拆函数 / 提策略). Per §2.4 these lines are "stop and
# look" signals, not auto-rejections: the plugin output is an advisory warning
# the coder answers in review.md, either by fixing or by writing the reason.
#
# Each language plugin collects its own `funcs` list (name, line, span, params)
# — Python via AST, the brace languages via their declaration regexes and a
# brace-matching span — and hands it to these three detectors.


def func_length_hits(funcs: list[dict], rel: str, limit: int = FUNC_LINE_LIMIT) -> list[tuple[str, int, str]]:
    """§2.4 函数长度 — over the line is usually two jobs wearing one name."""
    return [
        (rel, f["line"], "C1 函数 %s 长达 %d 行（§2.4 线 %d）：多为「并且」职责，拆开；review.md 说得出理由就记理由" % (f["name"], f["lines"], limit))
        for f in funcs
        if f.get("lines", 0) > limit
    ]


def param_count_hits(funcs: list[dict], rel: str, limit: int = PARAM_LIMIT) -> list[tuple[str, int, str]]:
    """§2.4 参数数量 — over the line is multi-responsibility or a missing value object."""
    return [
        (rel, f["line"], "C1 函数 %s 有 %d 个参数（§2.4 线 %d）：多职责或缺值对象；互斥创建看 C8" % (f["name"], f["params"], limit))
        for f in funcs
        if f.get("params", 0) > limit
    ]


def complexity_hits(funcs: list[dict], rel: str, limit: int = COMPLEXITY_LIMIT) -> list[tuple[str, int, str]]:
    """§2.4 圈复杂度 — over the line wants smaller functions or a strategy."""
    return [
        (rel, f["line"], "C1 函数 %s 圈复杂度 %d（§2.4 线 %d）：拆函数 / 提策略（P5）；review.md 说得出理由就记理由" % (f["name"], f["complexity"], limit))
        for f in funcs
        if f.get("complexity", 0) > limit
    ]


# Branch keywords/ops that add an independent path in the brace languages.
# The count is + 1 per §2.4's 测量方法 (独立分支路径数 +1), so complexity
# starts at 1 for the straight-line body.
_BRANCH_KEYWORD = re.compile(r"\b(?:if|for|while|case|catch)\b")
_BRANCH_OP = re.compile(r"&&|\|\|")


def brace_complexity(body: str) -> int:
    """Path count of a masked function body: keywords + short-circuit ops + 1.

    `else` is deliberately absent: an else adds no path its `if` did not
    already count. Ternaries (`? :`) are absent too — a `?` in masked text
    can also be a wildcard generic, and one miscounted path is not worth
    the false positives (the DECLINED-table trade, applied inline).
    """
    return 1 + len(_BRANCH_KEYWORD.findall(body)) + len(_BRANCH_OP.findall(body))


def brace_func_spans(masked: str, decls: list[re.Match]) -> list[dict]:
    """Function dicts for brace languages: name, line, span, params.

    `decls` are the language plugin's declaration matches; every one must
    capture group `name`. The body span runs from the declaration's own
    body brace to its matching `}`. The brace is located by scanning
    forward for the first `{` that sits before any statement separator
    (`;` or a non-annotation identifier line) — but the declaration regexes
    end at or just past the params `)`, so the first `{` after the return
    type is the body; a declaration without a brace (interface / abstract
    method / forward decl) is skipped, and so is a `{` that belongs to the
    enclosing type because `masked.find` from a body-less declaration
    would fall through to it — the `;` guard below is what catches that.
    """
    funcs = []
    for m in decls:
        # The declaration regex may already end at the body brace; when it
        # does, that brace is the match's last character and the search
        # must start one earlier or it will look past the whole method.
        brace_at = m.end() - 1 if masked[m.end() - 1:m.end()] == "{" else m.end()
        open_brace = masked.find("{", brace_at)
        if open_brace < 0:
            continue
        if masked.find(";", m.end(), open_brace) >= 0:
            continue  # `... someMethod();` — no body to measure
        depth = 0
        close = -1
        for i in range(open_brace, len(masked)):
            if masked[i] == "{":
                depth += 1
            elif masked[i] == "}":
                depth -= 1
                if depth == 0:
                    close = i
                    break
        if close < 0:
            continue
        params = m.group("params") if "params" in (m.groupdict() or {}) else ""
        count = len([p for p in params.split(",") if p.strip()]) if params else 0
        funcs.append({
            "name": m.group("name"),
            "line": _line(masked, m.start("name")),
            "start": open_brace,
            "end": close,
            "lines": masked.count("\n", open_brace, close) + 1,
            "params": count,
        })
    return funcs
