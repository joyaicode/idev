#!/usr/bin/env python3
"""resume_pack assembles existing stores; it never writes a judgment.

Proposal 20261117-agent-loop-enhancement B2: the bundle is the mechanism
behind the HANDOFF line's promise. Every test below pins one clause of that
contract — and the negative clauses (no warnings-turned-errors, no bundle
without a ticket) matter as much as the positive ones, because this runs
inside `trace.sh append`, a write point that fires every round.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "lib"))

import trace  # noqa: E402


TRACE_BODY = """schema_version: 2
at: 2026-11-17T10:00:00+08:00
feature: demo
intent: 推进 demo
route:
  scenario: S8
  module: workflows
  stage: code
  why: 命中别名
thinking:
  summary: 一行
calls: []
"""


def sh(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class ResumePack(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve()
        self.ticket = self.repo / ".idev" / "task" / "demo"
        (self.ticket / "workflow").mkdir(parents=True)
        # product_repo() keys on a .git directory — the marker file is for
        # other layers; a checkout is what this one needs.
        sh("git", "init", "-q", ".", cwd=self.repo)
        self._cwd = Path.cwd()
        import os

        os.chdir(self.repo)
        self.addCleanup(os.chdir, self._cwd)

    def _write_run(self) -> None:
        run = """schema_version: 1
workflow_id: lite-change
feature: demo
status: running
steps:
  - id: done-step
    kind: shell.confirmed
    status: PASS
  - id: plan
    kind: verify.plan
  - id: gate-plan
    kind: human.gate
"""
        (self.ticket / "workflow" / "run.yaml").write_text(run, encoding="utf-8")

    def test_no_bundle_without_a_run(self) -> None:
        self.assertIsNone(trace.resume_pack(TRACE_BODY, 100, 300000))

    def test_bundle_assembles_only_existing_fields(self) -> None:
        import yaml

        self._write_run()
        source = self.repo / "src" / "app.py"
        source.parent.mkdir()
        source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
        import read_ledger

        read_ledger.note(
            self.ticket, "plan", "src/app.py:1:2",
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        dest = trace.resume_pack(TRACE_BODY, 120, 342326)
        self.assertIsNotNone(dest)
        bundle = yaml.safe_load(dest.read_text(encoding="utf-8"))
        # Every field traces to an existing store — these are those stores.
        self.assertEqual(bundle["feature"], "demo")
        self.assertEqual(bundle["open"], ["plan", "gate-plan"])
        self.assertEqual(bundle["progress"], "PROGRESS closed=1/3 open=plan,gate-plan")
        self.assertEqual(
            bundle["reads"],
            [{"step": "plan", "span": "src/app.py:1:2",
              "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
        )
        # prior_failures: no delegation record exists for the open steps,
        # so the bundle says nothing — assembly, never invention.
        self.assertEqual(bundle["prior_failures"], {})
        self.assertIn("HANDOFF rounds=120", bundle["handoff_note"])
        # Reads body text never enters the bundle (disk replays it).
        self.assertNotIn("return 1", dest.read_text(encoding="utf-8"))

    def test_feature_absent_means_no_bundle(self) -> None:
        bare = TRACE_BODY.replace("feature: demo", "feature: -")
        self.assertIsNone(trace.resume_pack(bare, 100, 1))

    def test_unparsable_run_yaml_is_none_not_crash(self) -> None:
        (self.ticket / "workflow" / "run.yaml").write_text("steps: [", encoding="utf-8")
        self.assertIsNone(trace.resume_pack(TRACE_BODY, 100, 1))


if __name__ == "__main__":
    unittest.main()
