#!/usr/bin/env python3
"""Same scope with two actions stays visible. Recall does not keep only the newer row."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lessons.py"


class LessonConflict(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.home = self.repo / ".idev" / "task" / "clash"
        self.home.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, scope: str, action: str, symptom: str = "回写延迟") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo",
                str(self.repo),
                "--feature",
                "clash",
                "add",
                "--event",
                "verified",
                "--scope",
                scope,
                "--symptom",
                symptom,
                "--evidence",
                "ev.log",
                "--action",
                action,
                "--outcome",
                "待核",
                "--not-when",
                "位点连续推进时不适用",
            ],
            capture_output=True,
            text=True,
        )

    def recall(self, scope: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo",
                str(self.repo),
                "--feature",
                "clash",
                "recall",
                "--scope",
                scope,
                "--no-count",
            ],
            capture_output=True,
            text=True,
        )

    def test_same_scope_different_action_is_conflict_and_keeps_the_cutoff_row(self):
        for _ in range(5):
            added = self.add("库存回写", "先看积压")
            self.assertEqual(added.returncode, 0, added.stderr)
        added = self.add("库存回写", "先重启消费者")
        self.assertEqual(added.returncode, 0, added.stderr)
        result = self.recall("库存回写")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CONFLICT L1 L2 L3 L4 L5 L6", result.stdout)
        self.assertIn("先重启消费者", result.stdout)
        self.assertIn("不要改旧行", result.stdout)
        checked = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), "--feature", "clash", "check"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("L1 L2 L3 L4 L5 L6: 同一 scope 动作不同", checked.stderr)

    def test_same_action_and_different_scope_do_not_conflict(self):
        self.assertEqual(self.add("库存回写", "先看积压").returncode, 0)
        self.assertEqual(self.add("库存回写", "先看积压", symptom="另一现象").returncode, 0)
        same = self.recall("库存回写")
        self.assertEqual(same.returncode, 0, same.stderr)
        self.assertNotIn("CONFLICT", same.stdout)
        self.assertEqual(self.add("库存对账", "先重放消息").returncode, 0)
        self.assertEqual(self.add("订单", "先看支付").returncode, 0)
        other = self.recall("库存")
        self.assertEqual(other.returncode, 0, other.stderr)
        self.assertNotIn("CONFLICT", other.stdout)
        self.assertIn("先重放消息", other.stdout)
        self.assertNotIn("先看支付", other.stdout)
