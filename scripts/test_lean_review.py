#!/usr/bin/env python3
"""lean-review.assess: lenses match the ticket, the stage, and the merge.

The lens roster is the whole mechanism, and it has two axes now: what the
ticket can hit (UI items, config paths) and which stage is asking — a code
round owes no product lens, a test round owes no dev lens, and every stage
routes findings to a different carrier (grill / review.md / the dimension
table / the hypothesis ledger). A finding routed to the wrong carrier
either wakes the person for something review.fix would have fixed, or
quietly dies in a file nobody reads.

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

    def test_req_review_owes_no_ops_lens_even_with_config(self) -> None:
        # Five-stage law: ops challenges the arch plan (A6, rollback), not
        # the requirement. A config path in req-review narrows nothing.
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
        self.assertNotIn("ops", self._lenses(result))
        result = self.mod.assess(self.repo, "lr", "arch")
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
        for shard in result["shards"]:
            self.assertEqual(shard["merge"], "grill",
                             "arch findings go to the person via grill: %s" % shard["id"])

    def test_every_lens_names_its_rulers(self) -> None:
        self._baseline('feature: lr\ngoal: "g"\nnon_goal: "n"\nitems:\n  - id: B1\n    must: "m"\n')
        self._deliver("P0")
        result = self.mod.assess(self.repo, "lr", "arch")
        for shard in result["shards"]:
            self.assertTrue(shard["rulers"], "lens %s carries no ruler" % shard["id"])
            self.assertIn("失败场景", shard["scope"], "lens %s brief lost the anti-padding rules" % shard["id"])

    # ---- stage matrix: each stage owes its own lenses and carrier ------

    def _risky(self) -> None:
        self._baseline(
            'feature: lr\ngoal: "g"\nnon_goal: "n"\nassumptions:\n'
            '  - {what: w, basis: b, check: c, if_false: f}\nitems:\n  - id: B1\n    must: "m"\n'
        )
        self._deliver("P0")

    def test_code_round_owes_no_product_or_architect_lens(self) -> None:
        self._risky()
        result = self.mod.assess(self.repo, "lr", "code")
        lenses = self._lenses(result)
        self.assertEqual(lenses, {"dev", "test", "ops"},
                         "code re-audits the implementation, not the sealed plan: %s" % lenses)
        for shard in result["shards"]:
            self.assertEqual(shard["merge"], "review-md",
                             "code findings ride review.fix, not the person: %s" % shard["id"])

    def test_test_round_merges_into_the_dimension_table(self) -> None:
        self._risky()
        result = self.mod.assess(self.repo, "lr", "test")
        for shard in result["shards"]:
            self.assertEqual(shard["merge"], "dimension-table",
                             "test findings fix UNPROVEN or add cases: %s" % shard["id"])

    def test_ops_round_owens_two_lenses_and_the_ledger(self) -> None:
        self._risky()
        result = self.mod.assess(self.repo, "lr", "ops")
        lenses = self._lenses(result)
        self.assertEqual(lenses, {"dev", "ops"},
                         "ops round is the closed loop's own step: %s" % lenses)
        for shard in result["shards"]:
            self.assertEqual(shard["merge"], "hypothesis",
                             "ops findings become falsifiable hypotheses: %s" % shard["id"])

    def test_ops_product_lens_needs_a_user_visible_phenomenon(self) -> None:
        self._risky()
        (self.home / "ops.yaml").write_text("phenomenon: 用户在页面上看不到审批按钮\n", encoding="utf-8")
        result = self.mod.assess(self.repo, "lr", "ops")
        self.assertIn("product", self._lenses(result))
        # and the negative: an infra-only phenomenon drops it
        (self.home / "ops.yaml").write_text("phenomenon: 消费组 lag 堆积\n", encoding="utf-8")
        result = self.mod.assess(self.repo, "lr", "ops")
        self.assertNotIn("product", self._lenses(result))

    def test_render_names_the_wave_merge_per_stage(self) -> None:
        self._risky()
        for stage, expect in (
            ("code", "idev-reviewer"),
            ("test", "idev-verifier"),
            ("ops", "idev-ops"),
            ("req-review", "独立子代理"),
            ("arch", "独立子代理"),
        ):
            result = self.mod.assess(self.repo, "lr", stage)
            text = self.mod.render(result, "lr")
            self.assertIn(expect, text, "stage %s lost its dispatch note" % stage)


if __name__ == "__main__":
    unittest.main()
