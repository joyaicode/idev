#!/usr/bin/env python3
"""A grouped record sees ticket files that changed after the wave was stamped."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import workflow


class DiskWrites(unittest.TestCase):
    def test_extra_file_is_outside_the_group(self) -> None:
        ticket = Path(tempfile.mkdtemp())
        (ticket / "review.md").write_text("old\n", encoding="utf-8")
        run = {
            "steps": [
                {"id": "plan", "group": "check", "writes": ["verify/plan.yaml"], "status": "pending"},
                {"id": "review", "group": "check", "writes": ["review.md"], "status": "pending"},
            ]
        }
        workflow.stamp_open_group(run, ticket)
        (ticket / "verify").mkdir()
        (ticket / "verify" / "notes.md").write_text("extra\n", encoding="utf-8")
        (ticket / "review.md").write_text("new\n", encoding="utf-8")
        outside = workflow.disk_outside_group(run, run["steps"][1], ticket)
        self.assertEqual(outside, ["verify/notes.md"])

    def test_sibling_write_is_allowed(self) -> None:
        ticket = Path(tempfile.mkdtemp())
        run = {
            "steps": [
                {"id": "plan", "group": "check", "writes": ["verify/plan.yaml"], "status": "pending"},
                {"id": "review", "group": "check", "writes": ["review.md"], "status": "pending"},
            ]
        }
        workflow.stamp_open_group(run, ticket)
        (ticket / "verify").mkdir()
        (ticket / "verify" / "plan.yaml").write_text("case\n", encoding="utf-8")
        outside = workflow.disk_outside_group(run, run["steps"][1], ticket)
        self.assertEqual(outside, [])


if __name__ == "__main__":
    unittest.main()
