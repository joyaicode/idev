#!/usr/bin/env python3
"""check_idea: the coding.md 念头表 declaration, on synthetic records.

delegation.py check_boost carries this check; these cases pin its contract:
declared-zero is a PASS, a missing line is a FAIL (silence and zero are
different facts), and a made-up number is a FAIL (no second numbering).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import delegation  # noqa: E402

BASE = (
    "STATUS: PASS\n"
    "EVIDENCE: /tmp/does-not-exist.md\n"
    "CHANGE_KIND: 追加行为\n"
    "CANON_TRIGGER: 无\n"
    "TABLE_HIT: 零命中\n"
    "IDEA_HITS: 零命中\n"
)


def record(raw: str, agent: str = "idev-coder", hints: list | None = None) -> dict:
    brief = {"ticket_home": "t", "repo": "r", "stage": "code", "must_read": "m"}
    if hints is not None:
        brief["pattern_hints"] = hints
    return {
        "agent": agent,
        "kind": "deliver.code_pass",
        "step": "code",
        "brief": brief,
        "report": {"status": "PASS", "raw": raw},
    }


def idea(raw: str) -> dict[str, str]:
    return {k: v for k, v in delegation.run_checks(record(raw), None).items() if k.startswith("idea-")}


class IdeaDeclared(unittest.TestCase):
    def test_missing_line_fails(self) -> None:
        bare = BASE.replace("IDEA_HITS: 零命中\n", "")
        self.assertIn("FAIL", idea(bare)["idea-declared"])

    def test_zero_hit_passes(self) -> None:
        self.assertEqual(idea(BASE + "IDEA_HITS: 零命中\n")["idea-declared"], "PASS")

    def test_no_hit_words_pass(self) -> None:
        self.assertEqual(idea(BASE + "IDEA_HITS: 无\n")["idea-declared"], "PASS")


class IdeaNumbered(unittest.TestCase):
    def test_legal_composite_passes(self) -> None:
        bare = BASE.replace("IDEA_HITS: 零命中\n", "")
        checks = idea(bare + "IDEA_HITS: 底线 1 + T1 / F1；C12 名字带 util；P6 想抽接口\n")
        self.assertEqual(checks["idea-declared"], "PASS")
        self.assertEqual(checks["idea-numbered"], "PASS")

    def test_boundary_numbers_pass(self) -> None:
        # C40 and P19 are the top of their §3.5 ranges, not made up.
        bare = BASE.replace("IDEA_HITS: 零命中\n", "")
        checks = idea(bare + "IDEA_HITS: C40；P19\n")
        self.assertEqual(checks.get("idea-numbered"), "PASS")

    def test_made_up_number_fails(self) -> None:
        bare = BASE.replace("IDEA_HITS: 零命中\n", "")
        checks = idea(bare + "IDEA_HITS: C41 编了个号\n")
        self.assertIn("C41", checks["idea-numbered"])
        self.assertIn("FAIL", checks["idea-numbered"])

    def test_zero_hit_has_no_number_check(self) -> None:
        self.assertNotIn("idea-numbered", idea(BASE + "IDEA_HITS: 零命中\n"))


class IdeaScope(unittest.TestCase):
    def test_other_agents_not_checked(self) -> None:
        checks = delegation.run_checks(record(BASE, agent="idev-reviewer"), None)
        self.assertNotIn("idea-declared", checks)


HINTS = [{"slice_id": "skip-when-disabled", "signal": "开关分流", "candidates": "P2"}]


def forecast(raw: str, hints: list | None = HINTS) -> dict[str, str]:
    checks = delegation.run_checks(record(raw, hints=hints), None)
    return {k: v for k, v in checks.items() if k.startswith("forecast-")}


class ForecastDeclared(unittest.TestCase):
    def test_brief_without_hints_demands_nothing(self) -> None:
        self.assertEqual(forecast(BASE, hints=None), {})

    def test_missing_line_fails(self) -> None:
        self.assertIn("FAIL", forecast(BASE)["forecast-declared"])

    def stated(self, line: str) -> None:
        checks = forecast(BASE + line)
        self.assertEqual(checks["forecast-declared"], "PASS")

    def test_prediction_hit_passes(self) -> None:
        self.stated("FORECAST: 预判 P2 命中\n")

    def test_prediction_overthrown_with_reason_passes(self) -> None:
        self.stated("FORECAST: 预判 P5 未命中,原因:实际只有 1 个实现,写具体类型\n")

    def test_stated_none_passes(self) -> None:
        self.stated("FORECAST: 无预判\n")


class ForecastNumbered(unittest.TestCase):
    def test_in_range_passes(self) -> None:
        checks = forecast(BASE + "FORECAST: 预判 P2 命中\n")
        self.assertEqual(checks.get("forecast-numbered"), "PASS")

    def test_made_up_p20_fails(self) -> None:
        checks = forecast(BASE + "FORECAST: 预判 P20 命中\n")
        self.assertIn("P20", checks["forecast-numbered"])
        self.assertIn("FAIL", checks["forecast-numbered"])

    def test_stated_none_has_no_number_check(self) -> None:
        self.assertNotIn("forecast-numbered", forecast(BASE + "FORECAST: 无预判\n"))


if __name__ == "__main__":
    unittest.main()
