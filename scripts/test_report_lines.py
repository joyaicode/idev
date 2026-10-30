#!/usr/bin/env python3
"""A report field's value sits on its own line: an empty field never borrows the next one.

    python3 scripts/test_report_lines.py
"""
from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
sys.path.insert(0, str(HERE))
import delegation  # noqa: E402
import delegation_return  # noqa: E402


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent_metrics = load("agent_metrics", "agent-metrics.py")
langfuse_export = load("langfuse_export", "langfuse-export.py")

FIELD = re.compile(r"\^.*?([A-Z][A-Z_]+):")
EXPECTED = {
    "STATUS", "EVIDENCE", "FACTS", "DOC_DRIFT", "ASSUMED", "SCOPE", "READ", "CHANGED",
    "REVERT", "RED_FIRST", "CHANGE_KIND", "CANON_TRIGGER", "TABLE_HIT", "ARTIFACT",
    "SUGGEST", "GUIDE", "DOMAIN", "CONCLUSION",
}
REPORT = (
    "STATUS: PASS\n"
    "EVIDENCE: docs/task/x/review.md\n"
    "FACTS: codegraph 查到 src/app.py:main 的调用方\n"
    "DOC_DRIFT: 无\n"
    "ASSUMED:\n"
    "SUGGEST:\n"
    "CONCLUSION: 已审完，3 条待签收。\n"
)


def line_fields(*modules) -> dict[str, tuple[str, re.Pattern[str]]]:
    """Every multi-line `^ … NAME:` pattern that captures the field's value."""
    found = {}
    for module in modules:
        for name, value in vars(module).items():
            if isinstance(value, re.Pattern) and value.flags & re.M and value.groups:
                hit = FIELD.search(value.pattern)
                if hit:
                    found[f"{module.__name__}.{name}"] = (hit.group(1), value)
    return found


def reviewer(raw: str) -> dict:
    return {
        "agent": "idev-reviewer", "kind": "review.report", "step": "report",
        "brief": {"ticket_home": "t", "repo": "r", "stage": "code", "must_read": "m", "idev_root": "i"},
        "report": {"status": "PASS", "raw": raw},
    }


class EmptyFieldStaysEmpty(unittest.TestCase):
    def test_no_field_pattern_reads_past_its_line(self) -> None:
        fields = line_fields(delegation, delegation_return, agent_metrics, langfuse_export)
        self.assertLessEqual(EXPECTED, {label for label, _ in fields.values()})
        for where, (label, pattern) in sorted(fields.items()):
            with self.subTest(pattern=where):
                self.assertIsNotNone(pattern.search(f"{label}: MATCH on its own line\n"))
                self.assertIsNone(pattern.search(f"{label}:\nMATCH on the next line\n"))

    def test_reviewer_changed_stays_on_the_review(self) -> None:
        quiet = delegation.run_checks(reviewer(REPORT), None)
        self.assertNotIn("gate-held", quiet)
        ok = delegation.run_checks(reviewer(REPORT + "CHANGED: docs/task/x/review.md\n"), None)
        self.assertEqual(ok["gate-held"], "PASS")
        shard = delegation.run_checks(reviewer(REPORT + "CHANGED: review/shards/api.md\n"), None)
        self.assertEqual(shard["gate-held"], "PASS")
        none = delegation.run_checks(reviewer(REPORT + "CHANGED: 无\n"), None)
        self.assertEqual(none["gate-held"], "PASS")
        moved = delegation.run_checks(reviewer(REPORT + "CHANGED: src/App.java\n"), None)
        self.assertTrue(moved["gate-held"].startswith("FAIL"), moved["gate-held"])

    def test_an_empty_assumed_line_declares_nothing(self) -> None:
        checks = delegation.run_checks(reviewer(REPORT), None)
        self.assertTrue(checks["assumption-declared"].startswith("FAIL"), checks["assumption-declared"])
        self.assertEqual(checks["assumption-tagged"], "PASS")

    def test_suggest_and_conclusion_land_in_their_own_fields(self) -> None:
        lifted = delegation.lift(REPORT)
        self.assertEqual(lifted["suggest"], "")
        self.assertEqual(lifted["conclusion"], "已审完，3 条待签收。")
        self.assertEqual(delegation.lift("SUGGEST: 委派包缺 must_read\nGUIDE:\nDOMAIN: 无\n"),
                         {"suggest": "委派包缺 must_read", "guide": "", "domain": "", "conclusion": ""})

    def test_rewriting_a_line_from_json_keeps_the_next_line(self) -> None:
        raw = "STATUS:\nEVIDENCE: docs/task/x/review.md\nCONCLUSION: done\n"
        self.assertEqual(
            delegation_return.apply_as_main(raw, {"status": "PASS"}),
            "STATUS: PASS\nEVIDENCE: docs/task/x/review.md\nCONCLUSION: done\n",
        )

    def test_readers_take_no_status_from_an_empty_line(self) -> None:
        record = {"report": {"raw": "STATUS:\nEVIDENCE: x.md\n"}}
        self.assertEqual(agent_metrics.status_of(record), "")
        self.assertEqual(langfuse_export.status_of(record), "")
        self.assertEqual(langfuse_export.evidence_of({"report": {"raw": "EVIDENCE:\nSTATUS: PASS\n"}}), "")


if __name__ == "__main__":
    unittest.main(verbosity=1)
