#!/usr/bin/env python3
"""test-roster: the three ways a test file passes without testing anything.

Each case builds a throwaway checkout, because the judgement under test is
about a scripts/ tree and its selfcheck.sh — not about this repo's current
one, which would make these cases change meaning every time someone adds a
test.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "test_roster", Path(__file__).resolve().with_name("test-roster.py")
)
tr = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(tr)

PASSING = """#!/usr/bin/env python3
import unittest
class Ok(unittest.TestCase):
    def test_a(self): self.assertTrue(True)
if __name__ == "__main__":
    unittest.main()
"""

NO_ENTRY = """#!/usr/bin/env python3
import unittest
class Silent(unittest.TestCase):
    def test_a(self): self.fail("never runs")
"""

FAILING = """#!/usr/bin/env python3
import unittest
class Red(unittest.TestCase):
    def test_a(self): self.assertEqual(1, 2)
if __name__ == "__main__":
    unittest.main()
"""

ALL_SKIPPED = """#!/usr/bin/env python3
import unittest
class Gone(unittest.TestCase):
    @unittest.skip("dependency absent")
    def test_a(self): self.fail("never runs")
    @unittest.skip("dependency absent")
    def test_b(self): self.fail("never runs")
if __name__ == "__main__":
    unittest.main()
"""

PART_SKIPPED = """#!/usr/bin/env python3
import unittest
class Half(unittest.TestCase):
    @unittest.skip("dependency absent")
    def test_a(self): self.fail("never runs")
    def test_b(self): self.assertTrue(True)
if __name__ == "__main__":
    unittest.main()
"""


def checkout(tests: dict, selfcheck: str = "") -> Path:
    """A tree with scripts/<tests> and the given selfcheck.sh body."""
    root = Path(tempfile.mkdtemp())
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "selfcheck.sh").write_text(selfcheck, encoding="utf-8")
    for name, body in tests.items():
        (scripts / name).write_text(body, encoding="utf-8")
    return root


def check(root: Path, *extra) -> tuple:
    """(exit code, output) of one run against that tree."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = tr.main(["--kernel", str(root), *extra])
    return rc, buf.getvalue()


class Predicates(unittest.TestCase):
    def test_holds_cases_ignores_a_print_and_exit_script(self) -> None:
        import ast

        self.assertTrue(tr.holds_cases(ast.parse(PASSING)))
        self.assertFalse(tr.holds_cases(ast.parse("print('vue-skills PASS')\n")))

    def test_entry_counts_both_spellings(self) -> None:
        import ast

        self.assertTrue(tr.has_entry(ast.parse("import unittest\nunittest.main()\n")))
        # `from unittest import main` then a bare `main()` runs the cases too.
        self.assertTrue(tr.has_entry(ast.parse("from unittest import main\nmain()\n")))
        self.assertFalse(tr.has_entry(ast.parse(NO_ENTRY)))

    def test_can_skip_sees_decorators_and_skiptest(self) -> None:
        import ast

        self.assertTrue(tr.can_skip(ast.parse(ALL_SKIPPED)))
        self.assertTrue(tr.can_skip(ast.parse(
            "import unittest\nclass A(unittest.TestCase):\n"
            "    def test_a(self): self.skipTest('no binary')\n"
        )))
        self.assertFalse(tr.can_skip(ast.parse(PASSING)))

    def test_muted_only_when_that_line_throws_output_away(self) -> None:
        self.assertTrue(tr.muted_by('python3 scripts/test_a.py >/dev/null 2>&1\n', "test_a.py"))
        self.assertFalse(tr.muted_by("run_test test_a.py\n", "test_a.py"))
        # Another test's muted line must not implicate this one.
        self.assertFalse(tr.muted_by('python3 scripts/test_b.py >/dev/null\n', "test_a.py"))

    def test_ran_and_skipped_reads_unittest_summary(self) -> None:
        self.assertEqual(tr.ran_and_skipped("Ran 6 tests in 0.1s\n\nOK (skipped=4)\n"), (6, 4))
        self.assertEqual(tr.ran_and_skipped("Ran 2 tests in 0.1s\n\nOK\n"), (2, 0))


class Roster(unittest.TestCase):
    def test_a_clean_tree_passes(self) -> None:
        rc, out = check(checkout({"test_ok.py": PASSING}))
        self.assertEqual(rc, 0, out)
        self.assertIn("test roster PASS", out)

    def test_a_file_with_cases_and_no_entry_fails(self) -> None:
        rc, out = check(checkout({"test_silent.py": NO_ENTRY}))
        self.assertEqual(rc, 1)
        self.assertIn("no unittest.main() entry", out)

    def test_an_unnamed_test_actually_runs(self) -> None:
        """Not named by selfcheck means run here — so a red one is caught."""
        rc, out = check(checkout({"test_red.py": FAILING}))
        self.assertEqual(rc, 1)
        self.assertIn("exit 1", out)

    def test_skipping_every_case_is_not_a_pass(self) -> None:
        rc, out = check(checkout({"test_gone.py": ALL_SKIPPED}))
        self.assertEqual(rc, 1)
        self.assertIn("all 2 cases skipped", out)

    def test_skipping_some_cases_is_reported_but_allowed(self) -> None:
        """A missing optional dependency is legitimate; silence is not."""
        rc, out = check(checkout({"test_half.py": PART_SKIPPED}))
        self.assertEqual(rc, 0, out)
        self.assertIn("1 of 2 cases skipped", out)

    def test_a_named_test_is_not_run_twice(self) -> None:
        tree = checkout(
            {"test_red.py": FAILING},
            selfcheck='python3 "${KERNEL}/scripts/test_red.py" >/dev/null 2>&1\n',
        )
        rc, out = check(tree)
        # Named, so its own lock owns the failure; but it can skip? No — so
        # the only finding here must not be an exit-1 from running it again.
        self.assertNotIn("exit 1", out)
        self.assertEqual(rc, 0, out)

    def test_a_skipping_test_may_not_be_muted_by_selfcheck(self) -> None:
        tree = checkout(
            {"test_gone.py": ALL_SKIPPED},
            selfcheck='python3 "${KERNEL}/scripts/test_gone.py" >/dev/null 2>&1\n',
        )
        rc, out = check(tree)
        self.assertEqual(rc, 1)
        self.assertIn("sends its output to /dev/null", out)

    def test_run_test_satisfies_that_rule(self) -> None:
        tree = checkout(
            {"test_gone.py": ALL_SKIPPED},
            selfcheck="run_test test_gone.py \\\n  || fail \"...\"\n",
        )
        rc, out = check(tree)
        self.assertEqual(rc, 0, out)
        self.assertIn("test roster PASS", out)

    def test_an_empty_scripts_tree_is_a_failure_not_a_pass(self) -> None:
        rc, out = check(checkout({}))
        self.assertEqual(rc, 1)
        self.assertIn("no test_*.py", out)


class ShellTests(unittest.TestCase):
    """A roster that only reads .py has the same hole as a hand-typed one:
    four test_*.sh were named in neither selfcheck nor CI."""

    def _tree(self, body: str, selfcheck: str = "") -> Path:
        root = checkout({}, selfcheck=selfcheck)
        (root / "scripts" / "test_shell.sh").write_text(body, encoding="utf-8")
        # Keep one .py around so the "no tests at all" branch is not what fires.
        (root / "scripts" / "test_ok.py").write_text(PASSING, encoding="utf-8")
        return root

    def test_a_shell_test_is_discovered_and_run(self) -> None:
        rc, out = check(self._tree("#!/usr/bin/env bash\nexit 0\n"))
        self.assertEqual(rc, 0, out)
        self.assertIn("2 test files", out)

    def test_a_failing_shell_test_is_caught(self) -> None:
        rc, out = check(self._tree("#!/usr/bin/env bash\necho 'boom' >&2\nexit 1\n"))
        self.assertEqual(rc, 1)
        self.assertIn("test_shell.sh", out)
        self.assertIn("exit 1", out)

    def test_a_shell_test_named_by_selfcheck_is_not_run_again(self) -> None:
        tree = self._tree("#!/usr/bin/env bash\nexit 1\n",
                          selfcheck='bash "${KERNEL}/scripts/test_shell.sh"\n')
        rc, out = check(tree)
        # Named, so its own lock owns the failure; this must not re-run it.
        self.assertEqual(rc, 0, out)
        self.assertNotIn("exit 1", out)

    def test_shell_tests_are_exempt_from_the_entry_point_rule(self) -> None:
        """There is no unittest.main() to look for in a shell script."""
        rc, out = check(self._tree("#!/usr/bin/env bash\nexit 0\n"))
        self.assertNotIn("no unittest.main() entry", out)


if __name__ == "__main__":
    unittest.main()
