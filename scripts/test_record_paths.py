#!/usr/bin/env python3
"""Every reader of a delegation record finds what delegation.py wrote.

1a4b224 moved records into delegations/<run_id>/ and left the readers on the
flat directory. The guards in workflow.py then read nothing: four let through
what they exist to stop, independent verification refused what it should
pass, and the metrics undercounted. Nothing went red because each guard
treats "no record" as "nothing to check". These cases pin the layout from
the writer's side and from every reader's side.

    python3 scripts/test_record_paths.py
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))

import record_paths  # noqa: E402
import safeyaml  # noqa: E402


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


workflow = _load("workflow", "workflow.py")
agent_metrics = _load("agent_metrics", "agent-metrics.py")
langfuse_export = _load("langfuse_export", "langfuse-export.py")


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safeyaml.dump(data), encoding="utf-8")


def _record(step: str, attempt: int = 1, agent: str = "idev-reviewer", raw: str = "STATUS: PASS\n", **extra) -> dict:
    return {"step": step, "attempt": attempt, "agent": agent, "report": {"raw": raw}, **extra}


class RunDir(unittest.TestCase):
    def test_a_run_id_gets_its_own_directory(self) -> None:
        base = Path("/d")
        self.assertEqual(record_paths.run_dir(base, {"run_id": "01ABC"}), base / "01ABC")

    def test_no_run_id_is_flat(self) -> None:
        base = Path("/d")
        self.assertEqual(record_paths.run_dir(base, {}), base)
        self.assertEqual(record_paths.run_dir(base, None), base)

    def test_an_unsafe_run_id_is_flat(self) -> None:
        base = Path("/d")
        for rid in ("../x", "a/b", "..", " "):
            self.assertEqual(record_paths.run_dir(base, {"run_id": rid}), base, rid)


class WorkflowReadsTheRunDirectory(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.ticket = Path(self._tmp.name) / "ticket"
        self.run = self.ticket / "workflow" / "run.yaml"
        self.run.parent.mkdir(parents=True)
        self.run.write_text("run_id: RUN2\nstatus: running\nsteps: []\n", encoding="utf-8")
        self.flat = self.run.parent / "delegations"
        self.own = self.flat / "RUN2"
        self.other = self.flat / "RUN1"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_latest_delegation_finds_this_runs_record(self) -> None:
        _write(self.own / "review-1.yaml", _record("review"))
        found = workflow.latest_delegation(self.run, "review")
        self.assertIsNotNone(found)
        self.assertEqual(found["attempt"], 1)

    def test_another_runs_record_is_not_this_runs(self) -> None:
        _write(self.own / "review-1.yaml", _record("review", 1))
        _write(self.other / "review-2.yaml", _record("review", 2))
        _write(self.flat / "review-3.yaml", _record("review", 3))
        self.assertEqual(workflow.latest_delegation(self.run, "review")["attempt"], 1)

    def test_unanswered_sees_the_signal(self) -> None:
        _write(self.own / "run-1.yaml", _record("run", agent="idev-verifier", signals=["[承重] x"]))
        self.assertEqual(workflow.unanswered(self.run, "run"), ["[承重] x"])

    def test_decide_refuses_a_signal_the_record_never_raised(self) -> None:
        _write(self.own / "run-1.yaml", _record("run", agent="idev-verifier", signals=["[承重] x"]))
        with self.assertRaises(workflow.Blocked):
            workflow.append_decision(self.run, "run", {
                "signal": "[承重] y", "question": "q", "answer": "a", "quote": "1",
            })

    def test_changed_paths_reads_the_report(self) -> None:
        _write(self.own / "c-1.yaml", _record("c", agent="idev-coder", raw="STATUS: PASS\nCHANGED: src/a.py\n"))
        self.assertEqual(workflow.changed_paths(self.run, "c"), ["src/a.py"])

    def test_independent_verification_finds_the_verifier_record(self) -> None:
        (self.ticket / "docs").mkdir()
        (self.ticket / "docs" / "x.md").write_text("reviewed\n", encoding="utf-8")
        _write(self.own / "review-1.yaml", _record("review", raw="STATUS: PASS\nEVIDENCE: docs/x.md\n"))
        step = {"id": "code-pass", "delegated": {"agent": "idev-coder"}}
        self.assertEqual(workflow.independent_refusal(self.run, step, "idev-reviewer", "docs/x.md"), "")

    def test_a_verifier_record_from_another_run_does_not_count(self) -> None:
        (self.ticket / "docs").mkdir()
        (self.ticket / "docs" / "x.md").write_text("reviewed\n", encoding="utf-8")
        _write(self.other / "review-1.yaml", _record("review", raw="STATUS: PASS\nEVIDENCE: docs/x.md\n"))
        step = {"id": "code-pass", "delegated": {"agent": "idev-coder"}}
        refusal = workflow.independent_refusal(self.run, step, "idev-reviewer", "docs/x.md")
        self.assertIn("no report from idev-reviewer", refusal)

    def test_a_run_without_run_id_still_reads_flat(self) -> None:
        self.run.write_text("status: running\nsteps: []\n", encoding="utf-8")
        _write(self.flat / "review-1.yaml", _record("review"))
        self.assertIsNotNone(workflow.latest_delegation(self.run, "review"))


class MetricsCountBothLayouts(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        base = self.repo / "docs" / "task" / "feat" / "workflow" / "delegations"
        _write(base / "review-1.yaml", _record("review", feature="feat"))
        _write(base / "RUN2" / "review-1.yaml", _record("review", feature="feat"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_agent_metrics_counts_flat_and_per_run(self) -> None:
        by_agent = agent_metrics.collect(self.repo, None)[0]
        self.assertEqual(by_agent["idev-reviewer"].delegated, 2)

    def test_langfuse_export_takes_flat_and_per_run(self) -> None:
        self.assertEqual(len(langfuse_export.collect(self.repo, None, None)), 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
