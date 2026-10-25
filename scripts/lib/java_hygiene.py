#!/usr/bin/env python3
"""Java yellow bars from conventions/java.md that a regex can see.

Review kept writing 高内聚 / 设计模式 / 语法糖优先 and never opened Problems.
IntelliJ is not available to the reviewer, so `new ArrayList<String>()`
survived. This scans the branch diff for the rows a pattern can decide.
Unboxing stays with Problems: `Number.longValue()` is a real call.
`Collections.<K, V>emptyMap()` is blocking. `Collectors.<T>toList()` is a note.

Default scope is the merge-base diff plus the working tree. `--all` walks
the tree and is not the default: a whole-repo backlog is not this round.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {
    ".git",
    "target",
    "build",
    "node_modules",
    "dist",
    "generated",
    "generatedverify",
    ".idea",
}

RULE_DIAMOND = "显式类型参数可被替换为<>"
RULE_INFER = "显式类型参数可以推断"
RULE_INFER_NOTE = "显式类型参数未判定"
RULE_BOX = "不必要的装箱"
RULE_OF = "java8禁止List.of/Set.of/Map.of"
RULE_UNUSED = "方法从未使用"
RULE_LOMBOK = "可以具有Lombok @Getter"
RULE_LIST_SORT = "可被替换为 List.sort()"
RULE_COMPARING = "可被替换为 Comparator.comparing"
RULE_SLEEP = "在循环中调用 Thread.sleep()"
RULE_SIMILAR_LOG = "类似的日志消息"
# Collections.empty*() / singleton*() are what the IDE calls 可以推断, and
# java.md forbids the explicit form. Collectors.<T>toList() stays a note:
# Java 8 often cannot infer it, and deleting it does not compile.
# Unused / Lombok only look at src/main. A test-only call still counts as
# unused, which is how the IDE reported getIdempotencyKey().
_FACTORIES = frozenset({
    "emptyList",
    "emptyMap",
    "emptySet",
    "emptySortedSet",
    "emptySortedMap",
    "singleton",
    "singletonList",
    "singletonMap",
})
BLOCKING_RULES = frozenset({
    RULE_DIAMOND,
    RULE_INFER,
    RULE_BOX,
    RULE_OF,
    RULE_UNUSED,
    RULE_LOMBOK,
    RULE_LIST_SORT,
    RULE_COMPARING,
    RULE_SLEEP,
    RULE_SIMILAR_LOG,
})

_CTOR = re.compile(r"\bnew\s+[A-Za-z_][\w.]*\s*<")
_DOT_LT = re.compile(r"\.\s*<")
_AFTER_ARGS = re.compile(r"\s*([A-Za-z_][\w]*)\s*\(")
_BOX = re.compile(
    r"\b(?:Integer|Boolean|Long|Double|Float|Short|Byte)\.valueOf\s*\("
)
_OF = re.compile(r"\b(?:List|Set|Map)\.of\s*\(")
_LIST_SORT = re.compile(r"\bCollections\.sort\s*\(")
_COMPARING = re.compile(
    r"\(\s*(\w+)\s*,\s*(\w+)\s*\)\s*->\s*\1\.(\w+)\.compareTo\(\s*\2\.\3\s*\)"
)
_LOG_MSG = re.compile(
    r"""\blog\.(?:trace|debug|info|warn|error)\(\s*"((?:[^"\\]|\\.)*)\""""
)
_LEVEL8 = re.compile(
    r"maven\.compiler\.(?:source|target|release)\s*>\s*1?\.?8\b"
    r"|java\.version\s*>\s*1\.8\b"
    r"|<release>\s*8\b"
    r"|compiler\.source\s*>\s*8\b"
)
_LEVEL17 = re.compile(
    r"maven\.compiler\.(?:source|target|release)\s*>\s*17\b"
    r"|java\.version\s*>\s*17\b"
    r"|<release>\s*17\b"
)


@dataclass(frozen=True)
class Hit:
    rel: str
    line: int
    rule: str
    snippet: str

    def token(self) -> str:
        return f"{self.rel}:{self.line}"

    def cited_in(self, text: str) -> bool:
        if self.token() in text:
            return True
        base = self.rel.rsplit("/", 1)[-1]
        return f"{base}:{self.line}" in text


def detect_level(repo: Path) -> str:
    """compiler level from the root pom and one module down. Unknown stays unknown."""
    blobs = []
    for pom in [repo / "pom.xml", *sorted(repo.glob("*/pom.xml"))]:
        if not pom.is_file():
            continue
        try:
            blobs.append(pom.read_text(encoding="utf-8", errors="replace")[:40000])
        except OSError:
            continue
    blob = "\n".join(blobs)
    if not blob:
        return "unknown"
    if _LEVEL8.search(blob):
        return "8"
    if _LEVEL17.search(blob):
        return "17"
    if "spring-boot-starter-parent" in blob and re.search(r"2\.[67]\.", blob):
        return "8"
    return "unknown"


def _git(repo: Path, args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _kept(rel: str) -> bool:
    parts = Path(rel).parts
    return rel.endswith(".java") and not (set(parts) & SKIP_DIRS)


def _names(repo: Path, args: list[str]) -> list[str]:
    out = _git(repo, args)
    if out is None:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _merge_base(repo: Path) -> str | None:
    for base in ("origin/master", "master", "origin/main", "main"):
        if _git(repo, ["rev-parse", "--verify", "--quiet", base]) is None:
            continue
        found = _git(repo, ["merge-base", "HEAD", base])
        if found:
            return found.strip()
    return None


def changed_java(repo: Path) -> tuple[list[str], str]:
    """Java files in the branch diff and the working tree."""
    if _git(repo, ["rev-parse", "--is-inside-work-tree"]) is None:
        return [], "no git"
    names: set[str] = set()
    base = _merge_base(repo)
    if base:
        names.update(_names(repo, ["diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"]))
        scope = f"diff {base[:12]}...HEAD"
    else:
        scope = "working tree"
    names.update(_names(repo, ["diff", "--name-only", "--diff-filter=ACMR", "HEAD"]))
    names.update(_names(repo, ["diff", "--name-only", "--cached", "--diff-filter=ACMR"]))
    names.update(_names(repo, ["ls-files", "--others", "--exclude-standard"]))
    java = sorted(path for path in names if _kept(path))
    return java, scope + f" ({len(java)} java)"


def all_java(repo: Path) -> list[str]:
    found = []
    for path in repo.rglob("*.java"):
        try:
            rel = path.relative_to(repo).as_posix()
        except ValueError:
            continue
        if _kept(rel):
            found.append(rel)
    return sorted(found)


def _strip_comments(text: str) -> list[str]:
    """One stripped line per source line. Strings and comments become spaces."""
    lines = []
    in_block = False
    for raw in text.splitlines():
        out: list[str] = []
        i = 0
        in_str = False
        str_ch = ""
        while i < len(raw):
            if in_block:
                end = raw.find("*/", i)
                if end < 0:
                    i = len(raw)
                    break
                i = end + 2
                in_block = False
                continue
            ch = raw[i]
            if in_str:
                if ch == "\\":
                    i += 2
                    continue
                if ch == str_ch:
                    in_str = False
                i += 1
                continue
            if ch in "\"'":
                in_str = True
                str_ch = ch
                i += 1
                continue
            if raw.startswith("//", i):
                break
            if raw.startswith("/*", i):
                in_block = True
                i += 2
                continue
            out.append(ch)
            i += 1
        lines.append("".join(out))
    return lines


def _read_args(text: str, lt: int) -> tuple[str, int] | None:
    """Explicit type args starting at `<`. Diamond and unclosed return None."""
    if lt >= len(text) or text[lt] != "<":
        return None
    if lt + 1 < len(text) and text[lt + 1] == ">":
        return None
    depth = 0
    for j in range(lt, len(text)):
        ch = text[j]
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
            if depth == 0:
                args = text[lt + 1 : j].strip()
                if not args:
                    return None
                return args, j + 1
    return None


def _anonymous(text: str, paren: int) -> bool:
    """True when the constructor at `paren` is `new T<...>(...) {`."""
    depth = 0
    for j in range(paren, len(text)):
        ch = text[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[j + 1 :].lstrip().startswith("{")
        elif ch == ";":
            return False
    return False


def hits_in(text: str, rel: str, level: str) -> list[Hit]:
    """Yellow bars in one compilation unit. `level` is 8, 17, or unknown."""
    found: list[Hit] = []
    lines = _strip_comments(text)
    for lineno, line in enumerate(lines, start=1):
        snippet = " ".join(line.split())
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
        for match in _CTOR.finditer(line):
            parsed = _read_args(line, match.end() - 1)
            if parsed is None:
                continue
            _args, end = parsed
            rest = line[end:].lstrip()
            if not rest.startswith("("):
                continue
            paren = end + (len(line[end:]) - len(rest))
            # Java 8 cannot diamond an anonymous class. Unknown follows 8.
            if level in ("8", "unknown") and _anonymous(line, paren):
                continue
            found.append(Hit(rel, lineno, RULE_DIAMOND, snippet))
        for match in _DOT_LT.finditer(line):
            parsed = _read_args(line, match.end() - 1)
            if parsed is None:
                continue
            _args, end = parsed
            name = _AFTER_ARGS.match(line[end:])
            if not name:
                continue
            rule = RULE_INFER if name.group(1) in _FACTORIES else RULE_INFER_NOTE
            found.append(Hit(rel, lineno, rule, snippet))
        if _BOX.search(line):
            found.append(Hit(rel, lineno, RULE_BOX, snippet))
        if level == "8" and _OF.search(line):
            found.append(Hit(rel, lineno, RULE_OF, snippet))
        if _LIST_SORT.search(line):
            found.append(Hit(rel, lineno, RULE_LIST_SORT, snippet))
        if _COMPARING.search(line):
            found.append(Hit(rel, lineno, RULE_COMPARING, snippet))
    found.extend(_sleep_in_loop(rel, lines))
    found.extend(_similar_logs(rel, text))
    return found


def _sleep_in_loop(rel: str, lines: list[str]) -> list[Hit]:
    """Thread.sleep directly inside while/for. TimeUnit.sleep is not this bar."""
    text = "\n".join(lines)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line) + 1)
    stack: list[bool] = []
    pending = 0
    parens = 0
    hits: list[Hit] = []
    i = 0
    while i < len(text):
        word = ""
        if text.startswith("while", i):
            word = "while"
        elif text.startswith("for", i):
            word = "for"
        if word and _word_at(text, i, word):
            pending += 1
            i += len(word)
            continue
        if text.startswith("Thread.sleep", i) and _word_at(text, i, "Thread") and any(stack):
            line = _line_at(starts, i)
            snippet = " ".join(lines[line - 1].split())
            hits.append(Hit(rel, line, RULE_SLEEP, snippet))
            i += len("Thread.sleep")
            continue
        ch = text[i]
        if ch == "(":
            parens += 1
        elif ch == ")":
            parens = max(0, parens - 1)
        elif ch == "{":
            stack.append(pending > 0)
            if pending > 0:
                pending -= 1
        elif ch == "}":
            if stack:
                stack.pop()
            if parens == 0:
                pending = 0
        elif ch == ";" and parens == 0:
            pending = 0
        i += 1
    return hits


def _word_at(text: str, index: int, word: str) -> bool:
    if not text.startswith(word, index):
        return False
    before = text[index - 1] if index else " "
    after_at = index + len(word)
    after = text[after_at] if after_at < len(text) else " "
    return not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_")


def _line_at(starts: list[int], index: int) -> int:
    line = 1
    for start in starts[1:]:
        if index < start:
            break
        line += 1
    return line


def _similar_logs(rel: str, text: str) -> list[Hit]:
    """Identical log text within 40 lines. The IDE calls that 类似的日志消息."""
    seen: dict[str, int] = {}
    hits: list[Hit] = []
    marked: set[int] = set()
    for match in _LOG_MSG.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        msg = match.group(1)
        prev = seen.get(msg)
        seen[msg] = line
        if prev is None or line - prev > 40 or line == prev:
            continue
        for at in (prev, line):
            if at in marked:
                continue
            marked.add(at)
            raw = text.splitlines()[at - 1]
            hits.append(Hit(rel, at, RULE_SIMILAR_LOG, " ".join(raw.split())))
    return hits


_GETTER = re.compile(
    r"(?m)^[ \t]*(?:public|protected|private)[ \t]+[\w.<>,?\[\] \t]+[ \t]+"
    r"(get[A-Z]\w*)[ \t]*\([ \t]*\)[ \t]*\{[ \t\n]*return[ \t]+([A-Za-z_]\w*)[ \t]*;[ \t\n]*\}"
)
_CLASS = re.compile(r"\bclass[ \t]+([A-Za-z_]\w*)")
_LOMBOK_POM = re.compile(r"<artifactId>\s*lombok\s*</artifactId>")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _module_root(repo: Path, rel: str) -> Path:
    """Nearest directory with a pom, else the maven module at the repo top."""
    cur = (repo / rel).parent
    while cur != repo and repo in cur.parents:
        if (cur / "pom.xml").is_file():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    top = rel.split("/", 1)[0]
    candidate = repo / top
    return candidate if (candidate / "pom.xml").is_file() else repo


def _has_lombok(module: Path) -> bool:
    pom = module / "pom.xml"
    if not pom.is_file():
        return False
    return _LOMBOK_POM.search(_read(pom)) is not None


def _main_texts(module: Path) -> list[str]:
    root = module / "src" / "main" / "java"
    if not root.is_dir():
        return []
    texts = []
    for path in root.rglob("*.java"):
        if not _kept(path.as_posix()):
            continue
        texts.append(_read(path))
    return texts


def _enclosing_class(text: str, index: int) -> tuple[str, bool]:
    """Simple class name above index, and whether that class already has @Getter."""
    pre = text[:index]
    matches = list(_CLASS.finditer(pre))
    if not matches:
        return "", False
    match = matches[-1]
    window = pre[max(0, match.start() - 240):match.start()]
    return match.group(1), "@Getter" in window


def _type_vars(texts: list[str], simple: str) -> set[str]:
    """Names declared with this class as their type, in main sources."""
    if not simple:
        return set()
    found = set()
    pattern = re.compile(r"\b(?:[\w.]+\.)?%s\s+([A-Za-z_]\w*)" % re.escape(simple))
    for text in texts:
        found.update(pattern.findall(text))
    return found


def accessor_hits(repo: Path, rels: list[str]) -> list[Hit]:
    """Trivial getters: unused in src/main, or still handwritten where Lombok exists.

    A call that exists only in src/test does not count. That is the IDE's
    reading of getIdempotencyKey(). Custom getters (anything other than
    `return field;`) are left alone.
    """
    hits: list[Hit] = []
    seen: set[tuple[str, int, str]] = set()
    modules: dict[Path, tuple[bool, list[str]]] = {}
    for rel in rels:
        rel = rel.replace("\\", "/")
        if "/src/main/" not in rel or not rel.endswith(".java"):
            continue
        path = repo / rel
        text = _read(path)
        if not text:
            continue
        module = _module_root(repo, rel)
        if module not in modules:
            modules[module] = (_has_lombok(module), _main_texts(module))
        lombok, mains = modules[module]
        for match in _GETTER.finditer(text):
            name, field = match.group(1), match.group(2)
            line = text.count("\n", 0, match.start()) + 1
            before = text[max(0, match.start() - 80):match.start()]
            if "@Override" in before:
                continue
            simple, class_getter = _enclosing_class(text, match.start())
            if class_getter:
                continue
            vars_ = _type_vars(mains, simple)
            used = False
            call = re.compile(r"\b(?:%s)\.%s\s*\(" % ("|".join(re.escape(v) for v in vars_) or r"(?!)", re.escape(name)))
            if vars_:
                for src in mains:
                    if call.search(src):
                        used = True
                        break
            snippet = " ".join(text.splitlines()[line - 1].split())
            if not used:
                rule = RULE_UNUSED
            elif lombok:
                rule = RULE_LOMBOK
            else:
                continue
            key = (rel, line, rule)
            if key in seen:
                continue
            seen.add(key)
            hits.append(Hit(rel, line, rule, "%s %s" % (name, snippet)))
    return hits


def scan_files(repo: Path, rels: list[str], level: str | None = None) -> list[Hit]:
    use = level or detect_level(repo)
    hits: list[Hit] = []
    present = []
    for rel in rels:
        path = repo / rel
        if not path.is_file():
            continue
        text = _read(path)
        if not text and not path.is_file():
            continue
        rel_norm = rel.replace("\\", "/")
        present.append(rel_norm)
        hits.extend(hits_in(text, rel_norm, use))
    hits.extend(accessor_hits(repo, present))
    return hits


def scan(repo: Path, level: str | None = None, everything: bool = False) -> tuple[list[Hit], str, str]:
    """Returns hits, scope label, compiler level."""
    repo = repo.resolve()
    use = level or detect_level(repo)
    if everything:
        rels = all_java(repo)
        scope = f"all ({len(rels)} java)"
    else:
        rels, scope = changed_java(repo)
    return scan_files(repo, rels, use), scope, use


def missing(hits: list[Hit], review_text: str, shard: str = "") -> list[Hit]:
    """Blocking hits whose file:line is not in the review. A shard only owes its module."""
    owed = []
    for hit in hits:
        if hit.rule not in BLOCKING_RULES:
            continue
        if shard:
            first = hit.rel.split("/", 1)[0]
            if first != shard and not hit.rel.startswith(shard + "/"):
                continue
        if not hit.cited_in(review_text):
            owed.append(hit)
    return owed


def format_report(hits: list[Hit], scope: str, level: str) -> str:
    blocking = [hit for hit in hits if hit.rule in BLOCKING_RULES]
    notes = [hit for hit in hits if hit.rule not in BLOCKING_RULES]
    lines = [
        f"scope: {scope}",
        f"level: {level}",
        f"blocking: {len(blocking)}",
        f"note: {len(notes)}",
    ]
    for hit in blocking:
        lines.append(f"{hit.token()}: {hit.rule}: {hit.snippet}")
    if blocking:
        lines.append(
            "REVIEW_GATE: copy every blocking file:line into review.md as an I* "
            "before 总则 / 五轴 / 内聚. A principle paragraph does not clear these."
        )
    for hit in notes:
        lines.append(f"note {hit.token()}: {hit.rule}: {hit.snippet}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--level", choices=("8", "17", "unknown"))
    parser.add_argument("--all", action="store_true", help="scan every Java file, not the diff")
    parser.add_argument("--shard", default="", help="only require hits under this module")
    parser.add_argument("--check-review", type=Path, help="exit 1 when a hit is absent from this file")
    parser.add_argument("paths", nargs="*", help="scan these files instead of the diff")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    level = args.level or detect_level(repo)
    if args.paths:
        rels = []
        for raw in args.paths:
            path = Path(raw)
            if not path.is_absolute():
                path = repo / path
            try:
                rels.append(path.resolve().relative_to(repo).as_posix())
            except ValueError:
                rels.append(path.resolve().as_posix())
        hits = scan_files(repo, rels, level)
        scope = f"paths ({len(rels)})"
    else:
        hits, scope, level = scan(repo, level, everything=args.all)
    text = format_report(hits, scope, level)
    if args.check_review:
        try:
            review = args.check_review.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"BLOCKED cannot read {args.check_review}: {exc}", file=sys.stderr)
            return 2
        owed = missing(hits, review, args.shard)
        print(text)
        if owed:
            print(f"MISSING {len(owed)}", file=sys.stderr)
            for hit in owed[:12]:
                print(f"MISSING {hit.token()}: {hit.rule}", file=sys.stderr)
            return 1
        print("CHECK review cites every java hygiene hit")
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
