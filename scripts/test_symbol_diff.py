"""symbol_diff spans over a real fixture checkout, four modes covered.

The modes are the contract (proposal 20261117-agent-loop-enhancement, C):
ast may prune a replay, brace/file are PREP nominations, none means callers
behave as before the module existed. Each test pins one mode's behavior with
the smallest checkout that produces it.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import symbol_diff  # noqa: E402


PY_BODY = """import os


def alpha(x):
    return x + 1


def beta(x):
    total = 0
    for i in range(10):
        total += i
    return total


def gamma(x):
    return x * 2
"""

GO_BODY = """package main

func alpha(x int) int {
\treturn x + 1
}

func beta(x int) int {
\ttotal := 0
\tfor i := 0; i < 10; i++ {
\t\ttotal += i
\t}
\treturn total
}
"""


def sh(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class SymbolDiffSpans(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name).resolve()
        self.git = ("git", "-C", str(self.repo))
        sh(*self.git, "init", "-q", cwd=self.repo)
        sh(*self.git, "config", "user.email", "t@t", cwd=self.repo)
        sh(*self.git, "config", "user.name", "t", cwd=self.repo)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _commit_base(self) -> None:
        (self.repo / "app.py").write_text(PY_BODY, encoding="utf-8")
        (self.repo / "svc.go").write_text(GO_BODY, encoding="utf-8")
        sh(*self.git, "add", "-A", cwd=self.repo)
        sh(*self.git, "commit", "-qm", "base", "--no-gpg-sign", cwd=self.repo)

    def _touch(self, path: Path, old: str, new: str) -> None:
        path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    def test_none_when_worktree_clean(self) -> None:
        self._commit_base()
        out = symbol_diff.spans(self.repo)
        self.assertEqual(out["changed"], [])
        self.assertIn("none", out["status"])

    def test_ast_mode_pins_the_changed_function(self) -> None:
        self._commit_base()
        self._touch(self.repo / "app.py", "total += i", "total += i + 1")
        out = symbol_diff.spans(self.repo)
        row = next(r for r in out["changed"] if r["path"] == "app.py")
        self.assertEqual(row["mode"], "ast")
        names = [f["name"] for f in row["symbols"]]
        self.assertEqual(names, ["beta"])
        lo, hi = row["neighborhood"]
        # beta spans lines 8-13; ±10 clamped to the file.
        self.assertEqual((lo, hi), (1, 17))

    def test_brace_mode_reports_but_only_reports(self) -> None:
        self._commit_base()
        self._touch(self.repo / "svc.go", "total += i", "total += i + 1")
        out = symbol_diff.spans(self.repo)
        row = next(r for r in out["changed"] if r["path"] == "svc.go")
        self.assertEqual(row["mode"], "brace")
        self.assertEqual([f["name"] for f in row["symbols"]], ["beta"])

    def test_file_mode_for_frontend_suffixes(self) -> None:
        self._commit_base()
        (self.repo / "page.vue").write_text("<template>\n  <div/>\n</template>\n", encoding="utf-8")
        out = symbol_diff.spans(self.repo)
        row = next(r for r in out["changed"] if r["path"] == "page.vue")
        self.assertEqual(row["mode"], "file")
        self.assertEqual(row["symbols"], [])
        lo, hi = row["neighborhood"]
        # 3 content lines + trailing newline = count("\n")+1 counts the
        # empty final line the file ends with; total is 4, not 3.
        self.assertEqual((lo, hi), (1, 4))

    def test_file_mode_when_python_does_not_parse(self) -> None:
        self._commit_base()
        self._touch(
            self.repo / "app.py",
            "def beta(x):",
            "def beta(x:  # broken\n",
        )
        out = symbol_diff.spans(self.repo)
        row = next(r for r in out["changed"] if r["path"] == "app.py")
        self.assertEqual(row["mode"], "file")
        self.assertEqual(row["symbols"], [])

    def test_lines_outside_any_function_keep_the_file(self) -> None:
        # Module-level constant *inserted and later re-read as a whole file*:
        # no known function contains it, and a neighborhood that hid the
        # constant would hide the exact change a replay needs. The write
        # drops the trailing newline, so git also sees gamma's last line as
        # rewritten — a realistic messy worktree. What must hold: the module
        # never shrinks below the union of what actually changed.
        self._commit_base()
        start = PY_BODY.splitlines()
        body = [start[0], "", 'BANNER = "x"', ""] + start[1:]
        (self.repo / "app.py").write_text("\n".join(body), encoding="utf-8")
        out = symbol_diff.spans(self.repo)
        row = next(r for r in out["changed"] if r["path"] == "app.py")
        lo, hi = row["neighborhood"]
        # gamma's rewrite (trailing-newline drop) is a hit → span nests to
        # 18±10 = 8..29; BANNER's +lines start at 3, so the union floor is 3.
        # The guarantee under test: the span opens exactly where the changed
        # lines begin, never around gamma alone (which would hide the
        # constant from a replay).
        self.assertEqual(row["symbols"][0]["name"], "gamma")
        self.assertEqual((lo, hi), (3, 19))


if __name__ == "__main__":
    unittest.main()
