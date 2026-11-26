#!/usr/bin/env python3
"""The finding ledger: four states, anchors, dismissal reasons, recurrence.

Bugbot tracks each finding's resolution. idev's review.md carried two
states and no checks; these tests lock the four-state machine the push
gate and ticket-metrics now consume — especially the two shapes that were
silent before: a dismissal without a reason, and a "resolved" finding that
came back.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "review-findings.py"


def _load():
    spec = importlib.util.spec_from_file_location("rf", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FindingLedger(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve() / "one"
        (self.repo / ".idev" / "task" / "demo").mkdir(parents=True)
        self.rf = _load()

    def write_review(self, text: str) -> Path:
        path = self.repo / ".idev" / "task" / "demo" / "review.md"
        path.write_text(text, encoding="utf-8")
        return path

    def run_cmd(self, *extra: str) -> tuple[int, str]:
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *extra],
            capture_output=True, text=True, timeout=60,
        )
        return done.returncode, done.stdout + done.stderr

    # --- the four states parse ------------------------------------------

    def test_all_four_states_parse(self) -> None:
        items = self.rf.parse(
            "### I1 待签收\na\n### I2 已签收\nb\n### I3 已解决\nc\n### I4 已驳回\nd\n")
        self.assertEqual([i["status"] for i in items],
                         ["待签收", "已签收", "已解决", "已驳回"])

    # --- check: anchor and reason ---------------------------------------

    def test_a_finding_without_an_anchor_fails(self) -> None:
        self.write_review("### I1 待签收\n某处有个问题,说不清在哪\n")
        rc, out = self.run_cmd("check", "--feature", "demo")
        self.assertEqual(rc, 1)
        self.assertIn("finding-needs-anchor", out)

    def test_a_dismissal_without_a_reason_fails(self) -> None:
        self.write_review(
            "### I1 已驳回\nFoo.java:parse — 重复报,不修\n")
        rc, out = self.run_cmd("check", "--feature", "demo")
        self.assertEqual(rc, 1)
        self.assertIn("dismissed-needs-why", out)

    def test_a_dismissal_with_a_reason_passes(self) -> None:
        self.write_review(
            "### I1 已驳回\nFoo.java:parse — 重复报\n驳回: C14 例外,coding.md 明文允许\n")
        rc, out = self.run_cmd("check", "--feature", "demo")
        self.assertEqual(rc, 0)

    def test_clean_report_passes(self) -> None:
        self.write_review(
            "### I1 待签收\nFoo.java:parse — 空串返回空列表\n"
            "### I2 已解决\nBar.java:handle — 修复: 补 guard\n结果: verify 绿\n")
        rc, out = self.run_cmd("check", "--feature", "demo")
        self.assertEqual(rc, 0)

    def test_no_review_md_passes(self) -> None:
        rc, out = self.run_cmd("check", "--feature", "never-reviewed")
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    # --- recurrence ------------------------------------------------------

    def test_a_resolved_anchor_come_back_warns(self) -> None:
        review = self.write_review(
            "### I1 待签收\nFoo.java:parse — 又回来了\n\n## 既往轮次\n"
            "### I9 已解决\nFoo.java:parse — 上次修过\n")
        items = self.rf.parse(review.read_text(encoding="utf-8"))
        # resolved_before reads the 既往轮次 section
        rc = self.rf.check(items, self.rf._resolved_before(
            review, review.read_text(encoding="utf-8")))
        # check() only FAILs on errors; the recurrence is a WARN on stderr.
        # Assert the warning fired through the command instead.
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo),
             "check", "--feature", "demo"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0)
        self.assertIn("finding-recurred", done.stderr)

    # --- stats -----------------------------------------------------------

    def test_stats_counts_all_four_states(self) -> None:
        self.write_review(
            "### I1 待签收\nFoo.java:parse — a\n### I2 已签收\nFoo.java:x — b\n"
            "### I3 已解决\nBar.java:y — c\n### I4 已驳回\nBaz.java:z — d\n"
            "驳回: 误报\n")
        rc, out = self.run_cmd("stats", "--feature", "demo")
        self.assertEqual(rc, 0)
        self.assertIn("findings: 4", out)
        self.assertIn("签收 1", out)
        self.assertIn("解决 1", out)
        self.assertIn("驳回 1", out)
        self.assertIn("open 2", out)


if __name__ == "__main__":
    unittest.main()
