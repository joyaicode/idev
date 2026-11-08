#!/usr/bin/env python3
"""The audit decides whether a book gets re-read, so it gets tested too.

The load-bearing one is `test_covered_matches_detectors`: `COVERED` is a hand
written tuple, and a detector added without updating it would make the audit
report an enforced entry as mere bookkeeping — pointing a re-read at a book
that was already landed correctly.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import re
import sys
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "plugin"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import canon_smells as cs  # noqa: E402

_spec = importlib.util.spec_from_file_location("dra", ROOT / "scripts" / "deep-read-audit.py")
dra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dra)

VIOLATES_ALL = """public class Svc {
    public boolean buildDataHelper(Order o, Cfg c) {
        String s = o.getCustomer().getAddress().getCity();
        if (a) { if (b) { if (c) { g(); } } }
        try { f(); } catch (Exception e) { return false; }
    }
}
"""


class CoveredIsHonest(unittest.TestCase):
    def test_covered_matches_detectors(self):
        """Every number in COVERED fires, and nothing fires that is not in it."""
        sys.path.insert(0, str(ROOT / "scripts" / "plugin"))
        import java_inspect as ji
        titles = [t for _r, _l, t in ji.canon_hits(VIOLATES_ALL, "Svc.java")]
        fired = {re.match(r"(C\d+)", t).group(1) for t in titles if re.match(r"C\d+", t)}
        self.assertEqual(fired, set(cs.COVERED))

    def test_declined_are_not_claimed_as_covered(self):
        self.assertFalse(set(cs.DECLINED) & set(cs.COVERED))


class Layers(unittest.TestCase):
    def setUp(self):
        self.kernel = ROOT

    def test_enforced_entry(self):
        rows, reached = dra.audit(["C22"], self.kernel)
        _num, defined, _trigger, _staged, enforced = rows[0]
        self.assertTrue(defined)
        self.assertTrue(enforced)
        self.assertEqual(reached, 1)

    def test_t_rule_has_trigger(self):
        rows, _ = dra.audit(["T1"], self.kernel)
        _num, defined, trigger, _staged, _enforced = rows[0]
        self.assertTrue(defined and trigger)

    def test_unknown_number_is_not_defined(self):
        rows, reached = dra.audit(["C99"], self.kernel)
        self.assertFalse(rows[0][1])
        self.assertEqual(reached, 0)

    def test_bookkeeping_only_entry_does_not_count_as_reached(self):
        """A defined entry with no trigger, stage, or plugin stays unreachable."""
        with (
            mock.patch.object(dra, "trigger_ids", lambda _kernel: set()),
            mock.patch.object(dra, "staged_ids", lambda _kernel: set()),
            mock.patch.object(dra.canon_smells, "COVERED", ()),
        ):
            rows, reached = dra.audit(["C23"], self.kernel)
        _num, defined, trigger, staged, enforced = rows[0]
        self.assertTrue(defined)
        self.assertFalse(trigger or staged or enforced)
        self.assertEqual(reached, 0)

    def test_stage_ranges_expand_to_every_table_entry(self):
        """A page saying P1–P19 / C1–C40 / A1–A8 / R1–R7 stages every entry."""
        staged = dra.staged_ids(self.kernel)
        expected = {
            "A2", "A3", "A4", "A5", "A6",
            "P10", "P11", "P12", "P13", "P14", "P15", "P18",
            "C3", "C4", "C6", "C8", "C10", "C11", "C13", "C15",
            "C19", "C20", "C21", "C23", "C24", "C25", "C27",
            "R2", "R3", "R4", "R5", "R6",
        }
        self.assertLessEqual(expected, staged)

    def test_agent_failure_modes_reach_their_stages(self):
        rows, _ = dra.audit(["F2", "F5", "F6"], self.kernel)
        self.assertTrue(all(row[3] for row in rows), "F2/F5/F6 must be named on stage pages")


class AllBooks(unittest.TestCase):
    def test_book_reports_are_gap_reports_only(self):
        reports = dra.book_reports(ROOT)
        names = {path.name for path in reports}
        self.assertIn("重构-精读缺口.md", names)
        self.assertIn("测试驱动开发-精读缺口.md", names)
        self.assertNotIn("DDD-精读笔记-Ch1-4.md", names)

    def test_test_smell_rules_reach_the_verifier_stage(self):
        rows, _ = dra.audit(["C26", "C28", "C29", "C30"], ROOT)
        self.assertTrue(all(row[3] for row in rows), "test smells must be named on a stage page")

    def test_all_books_prints_one_summary_and_no_global_bookkeeping(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = dra.main(["--all-books"])
        text = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("# deep-read-audit all books", text)
        self.assertIn("scripts/docs/notes/重构-精读缺口.md", text)
        self.assertIn("scripts/docs/notes/测试驱动开发-精读缺口.md", text)
        self.assertNotIn("全局只有记账", text)
        self.assertIn("PASS", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
