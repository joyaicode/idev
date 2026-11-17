"""Symbol-level spans for files the working tree changed, one shared source.

Three existing parts piped together, no new parser:

    source_diff.changed()       file names (merge-base diff + worktree)
    plugin/<lang>_inspect       per-language function facts already collected
    git diff -U0                the changed line numbers

The four levels, written down because "which mode am I in" is the first
question every caller asks:

    ast    python files the ast module could parse        — replay may prune
    brace  go/java via brace_func_spans (plugin-grade)    — PREP nominees only
    file   js/ts/vue, parse failures, lines outside       — whole-file span
           any known function
    none   no diff, or nothing changed at all             — callers behave as
                                                           before this module

Per the 2026-11-17 grilling (state/proposals/20261117-agent-loop-enhancement),
only the `ast` mode ever prunes a replay; brace and file are advisory
nominations for the review PREP (coding-scan), where a wrong span costs a
look, not a lost context. A nomination is not a license: spans are things
the executor may load, never things it must skip reading.

The plugin interface reused here is the funcs-list shape each inspector
already builds for canon_smells.func_*_hits — {name, line, lines} for
python (lineno via ast), {name, line, start, end} byte offsets for the
brace languages (brace_func_spans). Byte offsets convert to line numbers
once, at this module's edge, so callers only ever see line spans.
"""
from __future__ import annotations

import re
from pathlib import Path

import source_diff

# Lines of neighborhood above and below a changed function. A constant, not a
# config: T8 — a knob nobody asked to turn is a new branch and a new test
# surface. Revisit with measurements, not by guessing bigger.
NEIGHBORHOOD = 10

AST_SUFFIX = (".py",)
BRACE_SUFFIX = (".go", ".java")

LANG_FOR_SUFFIX = {
    ".py": "python",
    ".go": "go",
    ".java": "java",
    ".js": "file",
    ".ts": "file",
    ".tsx": "file",
    ".vue": "file",
}


class _Git:
    """Diff lines per file, asked twice: staged-vs-HEAD and worktree."""

    _HUNK = re.compile(r"^@@[^+]*\+(\d+)(?:,(\d+))?")

    def __init__(self, repo: Path) -> None:
        self.repo = repo

    def touched(self, rel: str) -> set[int]:
        import subprocess

        lines: set[int] = set()
        for args in (["diff", "-U0", "HEAD", "--", rel], ["diff", "-U0", "--", rel]):
            try:
                proc = subprocess.run(
                    ["git", "-C", str(self.repo), *args],
                    capture_output=True, text=True, timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if proc.returncode != 0:
                continue
            for header in proc.stdout.splitlines():
                match = self._HUNK.match(header)
                if not match:
                    continue
                # -U0 makes the sides unambiguous: +start,count names the
                # side that exists; count 0 (pure deletion) adds nothing,
                # which matches how replays need spans that still exist.
                start = int(match.group(1))
                count = int(match.group(2) or 1)
                if count > 0:
                    lines.update(range(start, start + count))
        return lines


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _python_funcs(text: str) -> list[dict] | None:
    """name/line/lines from the python plugin's own _ast_funcs, span widened.

    The plugin reports lineno/lines (no end line); this module needs an end.
    Rebuilding from ast directly would copy the plugin's parsing — instead
    read the same facts and derive end = line + lines - 1, which is exactly
    the span the plugin itself measured. None means unparsable: the caller
    drops to file mode rather than guessing spans."""
    try:
        import ast

        tree = ast.parse(text)
    except SyntaxError:
        return None
    rows = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rows.append({
                "name": node.name,
                "start": node.lineno,
                "end": node.end_lineno or node.lineno,
            })
    return rows or None


def _brace_funcs(text: str, lang: str) -> list[dict] | None:
    """name/line/start/end from the plugins' declaration regexes.

    Each inspector keeps its own declaration regex (they differ in exactly
    the ways §2.4 documents: go's receiver parens, java's modifiers and
    annotation gates). Reusing those regexes here instead of a shared one
    keeps this module agreeing with the threshold detectors about what
    counts as a function in each language. The java annotation gates are
    NOT applied — test/entry methods' files still change and their spans
    still matter to a replay even when their length does not to §2.4."""
    try:
        import importlib.util

        root = Path(__file__).resolve().parents[1] / "plugin"
        module = {"go": "go_inspect", "java": "java_inspect"}[lang]
        spec = importlib.util.spec_from_file_location(module, root / f"{module}.py")
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        import canon_smells

        if lang == "go":
            decls = list(mod._DECL.finditer(text))
        else:
            decls = list(mod._SIG_PARAMS.finditer(text))
        rows = []
        for func in canon_smells.brace_func_spans(text, decls):
            rows.append({
                "name": func["name"],
                "start": _line_of(text, func["start"]),
                "end": _line_of(text, func["end"]),
            })
        return rows or None
    except Exception:
        # A parse blow-up on one odd file must not take the scan down with
        # it; file mode for that one file is the floor, not a failure.
        return None


def spans(repo: Path) -> dict:
    """Changed symbols per file, with the mode each file resolved to.

    The keys are repo-relative posix paths; the shape is the contract:

        changed:  [{path, symbols: [{name, start, end}],
                    neighborhood: (lo, hi), mode}]
        status:   a line for the caller to print or ignore

    mode `none` (nothing changed) means callers behave exactly as they did
    before this module existed — no pruning, no nominations. Changed lines
    that fall outside every known function keep the file whole (`hits`
    empty → all funcs): an over-eager neighborhood boundary around a
    module-level constant would hide the change a replay most needs.
    """
    repo = repo.resolve()
    source, _ = source_diff.changed(
        repo, AST_SUFFIX + BRACE_SUFFIX + tuple(LANG_FOR_SUFFIX), "symbol_diff",
    )
    if not source:
        return {"changed": [], "status": "symbol-diff none (no changed files)"}

    git = _Git(repo)
    changed: list[dict] = []
    for rel in sorted(set(source)):
        suffix = Path(rel).suffix.lower()
        lang = LANG_FOR_SUFFIX.get(suffix)
        path = repo / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total = text.count("\n") + 1
        touched = git.touched(rel)
        if lang == "python":
            funcs = _python_funcs(text)
            mode = "ast"
        elif lang in ("go", "java"):
            funcs = _brace_funcs(text, lang)
            mode = "brace"
        else:
            funcs, mode = None, "file"
        if funcs:
            hits = [f for f in funcs if any(f["start"] <= n <= f["end"] for n in touched)]
        else:
            hits = []
        if not funcs or not hits:
            changed.append({
                "path": rel, "symbols": [],
                "neighborhood": (1, total), "mode": "file" if funcs is None else mode,
            })
            continue
        # The span covers the union of the hit functions ±N and every
        # changed line. A module-level constant outside any function counts
        # as changed too; a neighborhood nested around only the hit
        # functions would hide exactly the line a replay most needs.
        lo = min(max(1, min(f["start"] for f in hits) - NEIGHBORHOOD), min(touched, default=1))
        hi = max(min(total, max(f["end"] for f in hits) + NEIGHBORHOOD), max(touched, default=1))
        changed.append({
            "path": rel, "symbols": hits,
            "neighborhood": (lo, hi),
            "mode": mode,
        })
    return {"changed": changed, "status": "symbol-diff ok (%d files)" % len(changed)}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="repository root")
    args = parser.parse_args()
    out = spans(Path(args.repo).resolve())
    print(out["status"])
    for row in out["changed"]:
        lo, hi = row["neighborhood"]
        names = ",".join(f["name"] for f in row["symbols"]) or "-"
        print("  %-6s %s:%d:%d  %s" % (row["mode"], row["path"], lo, hi, names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
