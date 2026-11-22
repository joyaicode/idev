#!/usr/bin/env python3
"""req-ground.check_item: a sealed requirement must name the code it lands on.

The seal at req-review is the measuring stick for everything after it, and
req-ground is the last check before that seal. What it can and cannot judge
is stated in its own docstring: presence, not correctness. The locks here
cover that presence contract — a baseline item without a grounding block,
touches without file:symbol anchors, a conflict declared without a grill
question, and a conflict whose grill question was never asked.

    python3 scripts/test_req_ground.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "req-ground.py"


def load_req_ground():
    spec = importlib.util.spec_from_file_location("req_ground", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckItem(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_req_ground()

    def _findings(self, item: dict, grills: set[str] | None = None) -> dict[str, object]:
        out: list = []
        self.mod.check_item(item, grills or set(), out)
        return {f.rule: f for f in out}

    def test_no_grounding_block(self) -> None:
        found = self._findings({"id": "b1"})
        self.assertIn("no-grounding", found)

    def test_touches_need_symbol_anchor(self) -> None:
        found = self._findings({"id": "b1", "grounding": {"touches": ["src/auth.py"]}})
        self.assertIn("touches-not-anchored", found)

    def test_anchored_touches_pass(self) -> None:
        found = self._findings(
            {"id": "b1", "grounding": {"touches": ["src/auth.py:resolve"]}}
        )
        self.assertNotIn("no-grounding", found)
        self.assertNotIn("touches-not-anchored", found)
        self.assertNotIn("no-touches", found)

    def test_conflict_without_grill_ref_is_a_finding(self) -> None:
        g = {"touches": ["src/auth.py:resolve"],
             "conflicts": [{"where": "src/auth.py:resolve", "existing": "denies", "tension": "must allow"}]}
        found = self._findings({"id": "b1", "grounding": g})
        kinds = {k for k in found if k.startswith("conflict")}
        self.assertTrue(kinds, f"a declared conflict without a grill ref must produce a finding, got {kinds}")

    def test_declared_grill_never_asked_is_a_finding(self) -> None:
        g = {"touches": ["src/auth.py:resolve"],
             "conflicts": [{"where": "src/auth.py:resolve", "existing": "denies",
                            "tension": "must allow", "grill": "Q3"}]}
        found = self._findings({"id": "b1", "grounding": g}, grills=set())
        kinds = set(found)
        self.assertTrue(any("grill" in k for k in kinds), f"unasked Q3 must be a finding, got {kinds}")

    def test_declared_grill_already_asked_is_clean(self) -> None:
        # boundary/direction are separate presence checks; pass them so the
        # lock isolates the conflict-grill rule.
        g = {"touches": ["src/auth.py:resolve"],
             "boundary": "none", "direction": "same",
             "conflicts": [{"where": "src/auth.py:resolve", "existing": "denies",
                            "tension": "must allow", "grill": "Q3"}]}
        found = self._findings({"id": "b1", "grounding": g}, grills={"Q3"})
        conflict_findings = {k for k in found if "conflict" in k or "grill" in k}
        self.assertEqual(conflict_findings, set(), found)


if __name__ == "__main__":
    unittest.main()
