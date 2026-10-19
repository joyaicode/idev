#!/usr/bin/env python3
"""Which reports stop the run for a person, and which replies count as an answer.

    python3 scripts/test_signals.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
sys.path.insert(0, str(HERE))
import workflow_spec as w  # noqa: E402

_spec = importlib.util.spec_from_file_location("delegation", HERE / "delegation.py")
delegation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(delegation)


def record(raw: str) -> dict:
    return {"agent": "idev-ops", "kind": "ops.classify", "report": {"raw": raw}}


class Signals(unittest.TestCase):
    def test_quiet_report_raises_nothing(self):
        raw = "STATUS: PASS\nASSUMED: [非承重] 日志时区是 UTC\nARTIFACT: MATCH\n"
        self.assertEqual(delegation.signals_of(record(raw)), [])

    def test_each_signal(self):
        cases = {
            "STATUS: BLOCKED(logic)\nASSUMED: 无\n": ["BLOCKED(logic)"],
            "STATUS: PASS\nASSUMED: [承重] 测试库是空的\n": ["[承重] 测试库是空的"],
            "STATUS: PASS\nASSUMED: 无\nARTIFACT: UNKNOWN(镜像无构建号)\n": ["ARTIFACT UNKNOWN"],
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(delegation.signals_of(record(raw)), want)

    def test_ahead_has_a_fixed_next_move(self):
        raw = "STATUS: PASS\nASSUMED: 无\nARTIFACT: AHEAD(源码新 3 个提交)\n"
        self.assertEqual(delegation.signals_of(record(raw)), [])

    def test_untagged_assumption_fails_the_check(self):
        checks = delegation.check_accuracy(record("STATUS: PASS\nASSUMED: 测试库是空的\n"))
        self.assertTrue(checks["assumption-tagged"].startswith("FAIL"))
        checks = delegation.check_accuracy(record("STATUS: PASS\nASSUMED: 无\n"))
        self.assertEqual(checks["assumption-tagged"], "PASS")


class Answers(unittest.TestCase):
    def test_non_answers(self):
        for quote in ("", "继续", "OK", "好的。", " go "):
            with self.subTest(quote=quote):
                self.assertFalse(w.is_answer(quote))

    def test_answers(self):
        for quote in ("1", "1a", "不是,先清库", "每次 CI 新建"):
            with self.subTest(quote=quote):
                self.assertTrue(w.is_answer(quote))


if __name__ == "__main__":
    unittest.main()
