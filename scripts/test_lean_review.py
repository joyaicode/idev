#!/usr/bin/env python3
"""lean-review.assess: the lenses match what the ticket can actually hit.

The lens roster is the whole mechanism: a UI-only ticket that ships an ops
lens (or a config-touching arch that drops one) either wastes a reviewer or
misses the finding. Each case below builds the smallest ticket that should
trigger one selection and asserts both directions.

    python3 scripts/test_lean_review.py
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "lean-review.py"


def load_lean():
    spec = importlib.util.spec_from_file_location("lean_review", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LensAssess(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_lean()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="idev-lean-")
        self.repo = Path(self._tmp.name)
        self.home = self.repo / "docs" / "task" / "lr"
        self.home.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _baseline(self, body: str) -> None:
        (self.home / "baseline.yaml").write_text(body, encoding="utf-8")

    def _deliver(self, tier: str = "P1") -> None:
        (self.home / "deliver.yaml").write_text("risk_tier: %s\n" % tier, encoding="utf-8")

    def _lenses(self, result: dict) -> set[str]:
        return {s["id"] for s in result["shards"]}

    def test_p1_with_no_risk_skips(self) -> None:
        self._baseline('feature: lr\ngoal: "g"\nnon_goal: "n"\nitems:\n  - id: B1\n    must: "m"\n')
        self._deliver("P1")
        result = self.mod.assess(self.repo, "lr", "req-review")
        self.assertEqual(result["decision"], "SKIP")

    def test_p0_triggers_even_on_a_plain_ticket(self) -> None:
        self._baseline('feature: lr\ngoal: "g"\nnon_goal: "n"\nitems:\n  - id: B1\n    must: "m"\n')
        self._deliver("P0")
        result = self.mod.assess(self.repo, "lr", "req-review")
        self.assertEqual(result["decision"], "LENS")
        self.assertIn("product", self._lenses(result))
        self.assertNotIn("architect", self._lenses(result), "plain req-review owes no architect lens")

    def test_ui_item_adds_ui_lens_only_where_it_exists(self) -> None:
        self._baseline(
            'feature: lr\ngoal: "g"\nnon_goal: "n"\nassumptions:\n'
            '  - {what: w, basis: b, check: c, if_false: f}\n'
            'items:\n  - id: B1\n    must: "m"\n    ui:\n      screen: s\n'
        )
        self._deliver()
        result = self.mod.assess(self.repo, "lr", "req-review")
        self.assertIn("ui", self._lenses(result))
        self.assertNotIn("ops", self._lenses(result), "req-review without config touch owes no ops lens")

    def test_config_touch_adds_ops_lens(self) -> None:
        self._baseline(
            'feature: lr\ngoal: "g"\nnon_goal: "n"\nassumptions:\n'
            '  - {what: w, basis: b, check: c, if_false: f}\nitems:\n  - id: B1\n    must: "m"\n'
        )
        self._deliver()
        (self.home / "arch.yaml").write_text(
            'approach: "a"\ninclude:\n  - "src/main/resources/application-config.yml"\n',
            encoding="utf-8",
        )
        result = self.mod.assess(self.repo, "lr", "req-review")
        self.assertIn("ops", self._lenses(result))

    def test_arch_stage_widens_the_roster(self) -> None:
        self._baseline('feature: lr\ngoal: "g"\nnon_goal: "n"\nitems:\n  - id: B1\n    must: "m"\n')
        self._deliver("P0")
        (self.home / "arch.yaml").write_text(
            'approach: "a"\ninclude:\n  - "src/x.py"\nimpact_candidates: ["x"]\n',
            encoding="utf-8",
        )
        result = self.mod.assess(self.repo, "lr", "arch")
        lenses = self._lenses(result)
        self.assertEqual(lenses, {"product", "architect", "dev", "test", "ops"},
                         "arch stage without a ui block drops the ui lens: %s" % lenses)

    def test_every_lens_names_its_rulers(self) -> None:
        self._baseline('feature: lr\ngoal: "g"\nnon_goal: "n"\nitems:\n  - id: B1\n    must: "m"\n')
        self._deliver("P0")
        result = self.mod.assess(self.repo, "lr", "arch")
        for shard in result["shards"]:
            self.assertTrue(shard["rulers"], "lens %s carries no ruler" % shard["id"])
            self.assertIn("失败场景", shard["scope"], "lens %s brief lost the anti-padding rules" % shard["id"])


if __name__ == "__main__":
    unittest.main()
