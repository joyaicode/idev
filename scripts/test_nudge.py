#!/usr/bin/env python3
"""A short reply that only says go is not a stop and not a baseline edit.

    python3 scripts/test_nudge.py
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import workflow_spec as w  # noqa: E402

NUDGE = HERE / "nudge.py"
TRACE = HERE / "trace.py"


def load_trace():
    spec = importlib.util.spec_from_file_location("idev_trace_nudge", TRACE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TRACE_MOD = load_trace()

BODY = """schema_version: 2
at: "2026-11-01T20:40:00+08:00"
feature: demo
intent: "往下推"
invoke:
  trigger: "{trigger}"
  matched: "往下推"
  how: continuation
route:
  module: deliver
  scenario: S2
  convention_class: coding
  stage: code
  risk_tier: P1
  why: "当前阶段还开着"
thinking:
  summary: "做还开着的事"
check_feature: ""
stop: "{stop}"
next: "{nxt}"
"""


class Nudge(unittest.TestCase):
    def test_proceed(self):
        for quote in ("验收", "继续", "确认", "通过", "通过了", "验收，继续",
                      "确认，继续", "看着差不多", "验收通过", "OK", "好"):
            with self.subTest(quote=quote):
                self.assertEqual(w.nudge_kind(quote), "proceed")
                self.assertTrue(w.is_nudge(quote))

    def test_named_reply_and_work(self):
        self.assertEqual(w.nudge_kind("打开基线"), "named")
        self.assertEqual(w.nudge_kind("解除密封"), "named")
        self.assertEqual(w.nudge_kind("回退到实现"), "named")
        self.assertEqual(w.nudge_kind("不要解除密封"), "reply")
        self.assertEqual(w.nudge_kind("不要继续"), "reply")
        self.assertEqual(w.nudge_kind("验收？"), "reply")
        self.assertEqual(w.nudge_kind("先别验收"), "reply")
        self.assertEqual(w.nudge_kind(""), "reply")
        self.assertEqual(w.nudge_kind("确认密封"), "work")
        self.assertEqual(w.nudge_kind("把三张票的编码做完"), "work")

    def test_acceptance_is_not_a_signoff_word(self):
        got = w.parse_confirm("验收")
        self.assertFalse(got.ok)
        self.assertEqual(got.reason, "no-verb")

    def test_non_answers_include_acceptance(self):
        for quote in ("验收", "继续，验收", "OK", "好的。"):
            with self.subTest(quote=quote):
                self.assertFalse(w.is_answer(quote))
        for quote in ("确认", "1", "不是,先清库"):
            with self.subTest(quote=quote):
                self.assertTrue(w.is_answer(quote))

    def test_a_restatement_is_rejected_and_a_real_hold_stays(self):
        restated = w.nudge_errors("验收", "验收没有写入。这句没有打开基线", "")
        self.assertEqual(restated, [w.NUDGE_STOP])
        self.assertEqual(w.nudge_errors("验收", "", "等下一句"), [w.NUDGE_STOP])
        self.assertEqual(w.nudge_errors("验收", "", ""), [])
        self.assertEqual(w.nudge_errors("验收", "frontier 非空", ""), [])
        self.assertEqual(w.nudge_errors("把编码做完", "验收没有写入", "等"), [])

    def test_decide_refusal_is_the_golden_line(self):
        golden = (HERE.parent / "test/golden/legacy/decide-non-answer.txtar").read_text(encoding="utf-8")
        self.assertIn("BLOCKED " + w.NUDGE_DECIDE, golden)
        src = (HERE / "workflow.py").read_text(encoding="utf-8")
        self.assertIn("raise Blocked(NUDGE_DECIDE)", src)

    def test_cli_prints_proceed(self):
        done = subprocess.run(
            [sys.executable, str(NUDGE), "--quote", "验收"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("NUDGE proceed\nBASELINE_ITEMS no\nSTOP no\n", done.stdout)

    def test_append_rejects_a_nudge_stop_and_keeps_a_clean_one(self):
        bad = BODY.format(trigger="验收", stop="验收没有写入。关卡没有变化", nxt="")
        errors = TRACE_MOD.validate(bad, for_append=True)
        self.assertIn(w.NUDGE_STOP, errors)
        clean = BODY.format(trigger="验收", stop="", nxt="")
        self.assertEqual(TRACE_MOD.validate(clean, for_append=True), [])

        env = os.environ.copy()
        with tempfile.TemporaryDirectory() as tmp:
            env["IDEV_TRACE_DIR"] = tmp
            env.pop("IDEV_RUN_ID", None)
            refused = subprocess.run(
                [sys.executable, str(TRACE), "append", "-"],
                input=bad, capture_output=True, text=True, check=False, env=env,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn(w.NUDGE_STOP, refused.stderr)
            self.assertEqual(list(Path(tmp).glob("*.yaml")), [])
            kept = subprocess.run(
                [sys.executable, str(TRACE), "append", "-"],
                input=clean, capture_output=True, text=True, check=False, env=env,
            )
            self.assertEqual(kept.returncode, 0, kept.stderr)
            self.assertTrue(list(Path(tmp).glob("*.yaml")))


if __name__ == "__main__":
    unittest.main()
