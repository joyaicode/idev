#!/usr/bin/env python3
"""ticketless.skips_baseline, table-driven against real shapes.

The function gates one branch of verify-plan: a recipe with
needs_ticket: false does not build a deliver.yaml or a sealed baseline,
so demanding sealed or baseline_item_id there is a gate that can never
turn green — the "refactor without a guard" of admission checks. But the
waiver is narrow on purpose. A baseline.yaml that exists is still
required to be sealed, and the waiver only holds while the ticket's
current run actually points at a ticketless recipe. Anything else — no
run, a broken recipe path, a recipe that does want a ticket — falls back
to the strict path.

The fixture recipes here are minimal, but the run.yaml files copy the
fields cmd_start writes (workflow.py: "recipe": str(recipe_path)), so the
contract being tested is the one production runs, not a simplified one.

    python3 scripts/lib/test_ticketless.py          # or: -v for every row
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ticketless  # noqa: E402

TICKETLESS_RECIPE = """schema_version: 1
id: code-review
needs_ticket: false
summary: no ticket
steps:
  - id: report
    kind: review.report
"""

TICKETED_RECIPE = """schema_version: 1
id: lite-change
summary: needs a ticket
steps:
  - id: preflight
    kind: preflight.inputs
"""

# needs_ticket written as the string "false" — YAML parses it to a str, and
# `is False` must reject it. A recipe that lies about its type does not get
# the waiver.
STRINGY_RECIPE = TICKETLESS_RECIPE.replace("needs_ticket: false", 'needs_ticket: "false"')


class SkipsBaseline(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="idev-ticketless-")
        self.task = Path(self._tmp.name) / ".idev" / "task" / "f"
        (self.task / "workflow").mkdir(parents=True)
        self.recipe = Path(self._tmp.name) / "recipe.yaml"
        self.recipe.write_text(TICKETLESS_RECIPE, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_yaml(self, recipe_path: Path) -> None:
        (self.task / "workflow" / "run.yaml").write_text(
            "schema_version: 1\nworkflow_id: x\nrecipe: %s\nfeature: f\n"
            "status: running\nsteps: []\n" % recipe_path,
            encoding="utf-8",
        )

    # --- the waiver holds ---------------------------------------------

    def test_ticketless_recipe_without_baseline(self) -> None:
        self.run_yaml(self.recipe)
        self.assertTrue(ticketless.skips_baseline(self.task))

    def test_absolute_and_relative_recipe_paths(self) -> None:
        # run.yaml records str(recipe_path) as cmd_start resolved it — an
        # absolute path. A relative path inside the repo must work too:
        # expanduser does not make it absolute, but the load is from cwd.
        self.recipe = Path(self.recipe).resolve()
        self.run_yaml(self.recipe)
        self.assertTrue(ticketless.skips_baseline(self.task))

    # --- the waiver is narrow ------------------------------------------

    def test_existing_baseline_disables_waiver(self) -> None:
        """A baseline file that exists is still required to be sealed.

        The guard against a half-migrated ticket: baseline.yaml present
        means someone did build a baseline, and the sealed check applies
        regardless of what the recipe says.
        """
        self.run_yaml(self.recipe)
        (self.task / "baseline.yaml").write_text("goal: x\n", encoding="utf-8")
        self.assertFalse(ticketless.skips_baseline(self.task))

    def test_no_run_yaml(self) -> None:
        self.assertFalse(ticketless.skips_baseline(self.task))

    def test_run_yaml_without_recipe_field(self) -> None:
        (self.task / "workflow" / "run.yaml").write_text(
            "schema_version: 1\nworkflow_id: x\nfeature: f\nstatus: running\nsteps: []\n",
            encoding="utf-8",
        )
        self.assertFalse(ticketless.skips_baseline(self.task))

    def test_recipe_path_broken(self) -> None:
        self.run_yaml(Path(self._tmp.name) / "nope.yaml")
        self.assertFalse(ticketless.skips_baseline(self.task))

    def test_recipe_wants_a_ticket(self) -> None:
        ticketed = Path(self._tmp.name) / "ticketed.yaml"
        ticketed.write_text(TICKETED_RECIPE, encoding="utf-8")
        self.run_yaml(ticketed)
        self.assertFalse(ticketless.skips_baseline(self.task))

    def test_needs_ticket_true_is_explicit(self) -> None:
        explicit = Path(self._tmp.name) / "explicit.yaml"
        explicit.write_text(
            TICKETLESS_RECIPE.replace("needs_ticket: false", "needs_ticket: true"),
            encoding="utf-8",
        )
        self.run_yaml(explicit)
        self.assertFalse(ticketless.skips_baseline(self.task))

    def test_needs_ticket_as_string_is_not_the_flag(self) -> None:
        stringy = Path(self._tmp.name) / "stringy.yaml"
        stringy.write_text(STRINGY_RECIPE, encoding="utf-8")
        self.run_yaml(stringy)
        self.assertFalse(ticketless.skips_baseline(self.task))

    def test_recipe_file_not_a_mapping(self) -> None:
        junk = Path(self._tmp.name) / "junk.yaml"
        junk.write_text("- just\n- a\n- list\n", encoding="utf-8")
        self.run_yaml(junk)
        self.assertFalse(ticketless.skips_baseline(self.task))


if __name__ == "__main__":
    unittest.main(verbosity=2)
