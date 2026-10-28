#!/usr/bin/env python3
"""doc form: six design headings, intent ids, and a report that only indexes."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_feature", Path(__file__).resolve().with_name("check-feature.py")
)
cf = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(cf)


class DocForm(unittest.TestCase):
    def test_example_shape_passes(self) -> None:
        repo = Path(tempfile.mkdtemp())
        root = repo / "ticket"
        root.mkdir()
        (root / "design.md").write_text(
            "\n".join(
                [
                    "## 目标",
                    "一句。",
                    "## 方案",
                    "无",
                    "## 契约",
                    "无",
                    "## 影响面",
                    "无",
                    "## 回退",
                    "无",
                    "## 用例",
                    "- alpha",
                ]
            ),
            encoding="utf-8",
        )
        (root / "verify").mkdir()
        errors: list[str] = []
        cf.check_doc_form(
            repo,
            "nope",
            root,
            {"case_intents": [{"id": "alpha", "slice_id": "s", "baseline_item_id": "B1"}]},
            {"cases": [{"id": "c1", "slice_id": "s", "baseline_item_id": "B1", "goal": "short"}]},
            {"items": [{"id": "B1"}]},
            errors,
        )
        self.assertEqual(errors, [])

    def test_missing_heading_and_copied_goal_fail(self) -> None:
        repo = Path(tempfile.mkdtemp())
        root = repo / "ticket"
        root.mkdir()
        (root / "design.md").write_text("## 目标\n只有目标\n", encoding="utf-8")
        (root / "verify").mkdir()
        goal = "When approval.enabled is false, the method runs."
        (root / "verify" / "report.md").write_text(goal + "\n", encoding="utf-8")
        errors: list[str] = []
        prd = repo / "docs" / "prd"
        prd.mkdir(parents=True)
        (prd / "demo.md").write_text("只写了别的事\n", encoding="utf-8")
        cf.check_doc_form(
            repo,
            "demo",
            root,
            {"case_intents": [{"id": "alpha", "slice_id": "s", "baseline_item_id": "B1"}]},
            {
                "cases": [
                    {
                        "id": "c1",
                        "slice_id": "other",
                        "baseline_item_id": "B9",
                        "goal": goal,
                    }
                ]
            },
            {"items": [{"id": "B1"}]},
            errors,
        )
        blob = "\n".join(errors)
        self.assertIn("missing ## 方案", blob)
        self.assertIn("missing case_intent alpha", blob)
        self.assertIn("missing case for alpha", blob)
        self.assertIn("copies the goal", blob)
        self.assertIn("missing case c1", blob)
        self.assertIn("missing item B1", blob)


if __name__ == "__main__":
    unittest.main()
