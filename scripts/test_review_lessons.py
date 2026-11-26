#!/usr/bin/env python3
"""Digest resolved findings into lessons candidates — six answers or none.

Bugbot learns rules automatically; idev only promotes a candidate a person
confirmed with a bypass reproduction. These tests lock the in-between step:
what a digest may never do — guess an action, duplicate a candidate, write
on dry-run.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "review-lessons.py"

REVIEW = """# Review

### I1 已解决
src/main/FooService.java:requirePlatform — 缺 platform 改返回空
修复: 缺 platform 改立刻 400
结果: verify t-require-platform 绿

### I2 已解决
src/main/Bar.java:parse — 空串返回空列表（没写修复行）

### I3 待签收
src/main/Baz.java:handle — 别的问题
"""


class ReviewLessons(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve() / "one"
        self.work = self.repo / ".idev" / "task" / "demo"
        self.work.mkdir(parents=True)
        # lessons.py refuses a ticket home that does not exist; the review.md
        # we write below makes the work dir real on its own.
        (self.work / "review.md").write_text(REVIEW, encoding="utf-8")

    def run_cmd(self, *extra: str) -> tuple[int, str]:
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *extra],
            capture_output=True, text=True, timeout=60,
        )
        return done.returncode, done.stdout + done.stderr

    def ledger(self) -> Path:
        return self.work / "lessons.yaml"

    def test_six_answers_land_a_candidate(self) -> None:
        rc, out = self.run_cmd("digest", "--feature", "demo")
        self.assertEqual(rc, 0)
        self.assertIn("OK   I1", out)
        text = self.ledger().read_text(encoding="utf-8")
        self.assertIn("requirePlatform", text)
        self.assertIn("单次出现且无复现", text)

    def test_a_finding_without_a_fix_line_does_not_land(self) -> None:
        rc, out = self.run_cmd("digest", "--feature", "demo")
        self.assertEqual(rc, 0)
        # I2 has no 修复: line — printed, skipped, never guessed.
        self.assertIn("SKIP I2", out)
        text = self.ledger().read_text(encoding="utf-8")
        self.assertNotIn("Bar.java:parse", text)

    def test_pending_findings_are_not_digested(self) -> None:
        rc, out = self.run_cmd("digest", "--feature", "demo")
        text = self.ledger().read_text(encoding="utf-8")
        self.assertNotIn("Baz.java:handle", text)

    def test_dry_run_writes_nothing(self) -> None:
        rc, out = self.run_cmd("digest", "--feature", "demo", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("DRY", out)
        self.assertFalse(self.ledger().exists())

    def test_rerun_does_not_duplicate(self) -> None:
        self.run_cmd("digest", "--feature", "demo")
        before = self.ledger().read_text(encoding="utf-8").count("id: L")
        rc, out = self.run_cmd("digest", "--feature", "demo")
        self.assertEqual(rc, 0)
        self.assertIn("SKIP I1", out)
        after = self.ledger().read_text(encoding="utf-8").count("id: L")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
