#!/usr/bin/env python3
"""Pipeline reference, tool steps, and adjustable membership."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import workflow_compose  # noqa: E402
import workflow_spec as spec  # noqa: E402

_wf = importlib.util.spec_from_file_location("workflow", HERE / "workflow.py")
workflow = importlib.util.module_from_spec(_wf)
_wf.loader.exec_module(workflow)

CATALOG = {
    "schema_version": 1,
    "tools": [
        {"id": "lessons", "summary": "经验", "command": "python3 scripts/lessons.py"},
        {"id": "stage-gate", "summary": "拒过", "command": "python3 scripts/stage-gate.py"},
        {"id": "hypothesis", "summary": "假设", "command": "python3 scripts/hypothesis.py"},
    ],
    "groups": [
        {"id": "evidence", "summary": "论证", "tools": ["stage-gate", "hypothesis", "lessons"]},
    ],
}


def recipe(name: str, steps: list) -> dict:
    return {"schema_version": 1, "id": name, "summary": "x", "steps": steps}


class Compose(unittest.TestCase):
    def test_kernel_recipes_keep_their_step_order(self):
        folder = HERE.parent / "workflows"
        for path in sorted(folder.glob("*.yaml")):
            data = workflow_compose.safeyaml.mapping(path)
            steps, errors = workflow_compose.composed_steps(data, workflow_compose.recipes_under(path))
            self.assertEqual(errors, [], path.name)
            want = [(step["id"], step["kind"]) for step in data["steps"]]
            got = [(step["id"], step["kind"]) for step in steps]
            self.assertEqual(got, want, path.name)

    def test_tool_is_a_step_and_a_group_can_be_reordered(self):
        errors: list[str] = []
        spec.check_recipe(recipe("demo", [{"id": "recall", "tool": "lessons"}]), Path("demo.yaml"), errors)
        self.assertEqual(errors, [])
        parent = recipe("demo", [{
            "id": "wave",
            "tool_group": "evidence",
            "adjust": {"skip": ["lessons"], "order": ["hypothesis", "stage-gate"]},
        }])
        steps, compose_errors = workflow_compose.composed_steps(parent, {"demo": parent}, CATALOG)
        self.assertEqual(compose_errors, [])
        self.assertEqual([step["id"] for step in steps], ["wave--hypothesis", "wave--stage-gate"])
        self.assertEqual(steps[0]["kind"], "tool.step")
        self.assertIn("TOOL python3 scripts/lessons.py", workflow._tool_line({"kind": "tool.step", "tool": "lessons"}))

    def test_a_pipeline_can_adjust_and_be_used_by_another(self):
        child = recipe("child", [
            {"id": "one", "kind": "route.s4"},
            {"id": "two", "kind": "route.s4", "label": "old"},
        ])
        parent = recipe("parent", [{
            "id": "call",
            "use": "child",
            "adjust": {
                "skip": ["one"],
                "replace": {"two": {"label": "new"}},
                "extend": [{"id": "extra", "tool": "lessons"}],
                "order": ["extra", "two"],
            },
        }])
        outer = recipe("outer", [{"id": "wrap", "use": "parent"}])
        book = {"child": child, "parent": parent, "outer": outer}
        steps, errors = workflow_compose.composed_steps(outer, book, CATALOG)
        self.assertEqual(errors, [])
        self.assertEqual([step["id"] for step in steps], ["wrap--call--extra", "wrap--call--two"])
        self.assertEqual(steps[1]["label"], "new")
        self.assertEqual(steps[1]["kind"], "route.s4")

    def test_a_cycle_and_a_second_driver_are_refused(self):
        left = recipe("left", [{"id": "go", "use": "right"}])
        right = recipe("right", [{"id": "back", "use": "left"}])
        _, errors = workflow_compose.composed_steps(left, {"left": left, "right": right}, CATALOG)
        self.assertTrue(any("pipeline cycle" in item for item in errors), errors)
        bad: list[str] = []
        spec.check_recipe(
            recipe("demo", [{"id": "g", "kind": "route.s4", "tool": "lessons"}]),
            Path("demo.yaml"),
            bad,
        )
        self.assertTrue(any("exactly one" in item for item in bad), bad)


if __name__ == "__main__":
    unittest.main()
