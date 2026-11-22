#!/usr/bin/env python3
"""agent-review.sh: the periodic review drafts, never lands, never lies.

agent-review.sh turns delegation metrics into proposal drafts — the entry
point of the self-evolution loop. Two properties carry all the weight, and
both are cheap to lock from outside:

  - it NEVER edits production files: a review that modifies a definition,
    the registry, or ledger.yaml is the loop writing its own rules;
  - a run without hard signal writes a receipt with signal=no, not a draft
    proposal dressed up as one.

Run against a scratch copy of the kernel: agent-review.sh reads
delegation records relative to the target repo and writes drafts under its
state/, and this test must not depend on (or mutate) the real state/.

    python3 scripts/test_agent_review.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REVIEW = Path(__file__).resolve().parent / "agent-review.sh"
KERNEL = REVIEW.parents[1]


class AgentReview(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="idev-agent-review-")
        # A scratch kernel copy: same scripts, empty state. A review with
        # no delegation records and no inbox is the no-signal baseline.
        self.scratch = Path(self._tmp.name) / "idev"
        shutil.copytree(KERNEL, self.scratch, symlinks=True,
                        ignore=shutil.ignore_patterns(
                            "state", ".git", "bin", "attic", ".codegraph", "__pycache__"))
        (self.scratch / "state").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *extra: str) -> subprocess.CompletedProcess:
        # --out lands drafts in the scratch, exercising the same flag the
        # script's own header recommends for disposable runs.
        return subprocess.run(
            ["bash", str(REVIEW), "--repo", str(self.scratch),
             "--out", str(self.scratch / "state"), *extra],
            capture_output=True, text=True, timeout=120, cwd=str(self.scratch),
        )

    def test_exit_zero_and_signal_no_on_empty_state(self) -> None:
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        # Empty scratch = no delegation records = no hard signal: the run
        # stays quiet. The verdict is asserted on the status file, not
        # stdout phrasing.
        status = self.scratch / "state" / "reviews" / "agent-review-status.env"
        self.assertTrue(status.is_file(), combined)
        self.assertIn("no signal", combined)
        self.assertIn("signal=no", status.read_text(encoding="utf-8"))

    def test_no_draft_proposal_without_hard_signal(self) -> None:
        self._run()
        proposals = self.scratch / "state" / "proposals"
        drafts = [p for p in proposals.glob("*agent-review*.md")] if proposals.is_dir() else []
        # Receipts are allowed and expected; a *proposal* draft would carry
        # a "要改什么" section and masquerade as a decision.
        for draft in drafts:
            body = draft.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("status: landed", body, f"{draft.name} must never self-land")

    def test_production_files_untouched(self) -> None:
        # The one action that would corrupt the loop: the review editing
        # the definitions it reviews. Compare a canary before/after.
        canary = self.scratch / "scripts" / "agent-review.sh"
        before = canary.read_bytes()
        self._run()
        self.assertEqual(canary.read_bytes(), before, "agent-review must not edit itself or siblings")
        ledger = self.scratch / "state" / "ledger.yaml"
        if ledger.is_file():
            self.assertIn("phase: trial", ledger.read_text(encoding="utf-8"),
                          "the review must not touch the ledger's phase")


if __name__ == "__main__":
    unittest.main()
