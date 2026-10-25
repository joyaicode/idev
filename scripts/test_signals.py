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

    def test_domain_block_does_not_stop_for_a_person(self):
        raw = "STATUS: BLOCKED(domain)\nDOMAIN: idev-ops\nGUIDE: 无\nASSUMED: 无\n"
        self.assertEqual(delegation.signals_of(record(raw)), [])

    def test_domain_directive(self):
        blocked = {
            "agent": "idev-coder",
            "step": "code-pass",
            "domain": "idev-ops",
            "guide": "断言必须挂 baseline item (plan.yaml:12)",
            "brief": {},
            "report": {"raw": "STATUS: BLOCKED(domain)\n"},
        }
        lines = delegation.domain_directive(blocked)
        self.assertTrue(any(line.startswith("HANDOFF guide: 断言必须挂") for line in lines))
        self.assertTrue(any(line.startswith("CONSULT idev-ops") for line in lines))
        self.assertEqual(delegation.signals_of(blocked), [])

        nested = dict(blocked, brief={"咨询": "code-pass"}, guide="")
        self.assertTrue(any(line.startswith("CONSULT none") for line in delegation.domain_directive(nested)))
        self.assertEqual(delegation.signals_of(nested), ["consult does not nest"])

        missing = dict(blocked, domain="", guide="")
        self.assertTrue(any(line.startswith("REBRIEF domain missing") for line in delegation.domain_directive(missing)))
        self.assertTrue(any(
            line.startswith("REBRIEF domain self")
            for line in delegation.domain_directive(dict(blocked, domain="idev-coder", guide=""))
        ))
        self.assertEqual(
            delegation.domain_directive({
                "agent": "idev-coder",
                "guide": "",
                "report": {"raw": "STATUS: PASS\n"},
            }),
            [],
        )

    def test_guide_lifts_and_none_domain_stays_empty(self):
        raw = "GUIDE: 断言必须挂 baseline item (plan.yaml:12)\nDOMAIN: 无\n"
        self.assertEqual(
            delegation.optional_line(raw, delegation.GUIDE_LINE),
            "断言必须挂 baseline item (plan.yaml:12)",
        )
        self.assertEqual(delegation.optional_line(raw, delegation.DOMAIN_LINE), "")

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
