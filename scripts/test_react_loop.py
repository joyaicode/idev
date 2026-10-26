#!/usr/bin/env python3
"""Bounded ReAct joint: candidate set, hop cap, predefined exit, trace copy."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import workflow_spec as spec  # noqa: E402

_wf = importlib.util.spec_from_file_location("workflow", HERE / "workflow.py")
workflow = importlib.util.module_from_spec(_wf)
_wf.loader.exec_module(workflow)

_tr = importlib.util.spec_from_file_location("trace", HERE / "trace.py")
trace = importlib.util.module_from_spec(_tr)
_tr.loader.exec_module(trace)


def loop(*args: str, folder: Path) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(HERE / "react_loop.py"), *args, "--dir", str(folder)]
    return subprocess.run(cmd, capture_output=True, text=True)


def recipe(step: dict) -> dict:
    return {"schema_version": 1, "id": "demo", "summary": "x", "steps": [step]}


TRACE = """\
schema_version: 2
at: "2026-10-26T12:00:00+08:00"
feature: "demo"
intent: "react hop"
invoke:
  trigger: "react"
  matched: "joint"
  how: explicit
  skills:
    - name: idev
route:
  module: deliver
  scenario: S1
  why: "joint"
thinking:
  summary: "copy the hop"
react: "%s"
"""


class ReactLoop(unittest.TestCase):
    def test_unregistered_tool_is_refused_before_a_loop_exists(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            opened = loop(
                "open", "--feature", "demo", "--step", "look",
                "--candidate", "not-a-tool", folder=folder,
            )
            self.assertEqual(opened.returncode, 1)
            self.assertIn("unknown tool", opened.stderr)
            self.assertEqual(list(folder.glob("*.yaml")), [])
        errors: list[str] = []
        known = spec.check_catalog(
            {"schema_version": 1, "tools": [
                {"id": "stage-gate", "summary": "gate", "command": "python3 scripts/stage-gate.py"},
            ]},
            Path("tools.yaml"),
            errors,
        )
        self.assertEqual(errors, [])
        spec.check_tool_refs(
            recipe({"id": "look", "kind": "route.s4", "react": {"candidates": ["not-a-tool"]}}),
            set(known),
            Path("demo.yaml"),
            errors,
        )
        self.assertTrue(any("unknown tool not-a-tool" in item for item in errors))

    def test_unknown_tool_does_not_record(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            opened = loop("open", "--feature", "demo", "--step", "look", "--candidate", "stage-gate", folder=folder)
            self.assertEqual(opened.returncode, 0, opened.stderr)
            acted = loop(
                "act", "--feature", "demo", "--step", "look",
                "--thought", "try another", "--action", "other-tool", folder=folder,
            )
            self.assertEqual(acted.returncode, 2)
            self.assertIn("REJECT", acted.stderr)
            text = (folder / "demo--look.yaml").read_text(encoding="utf-8")
            self.assertNotIn("other-tool", text)

    def test_tool_failure_takes_the_exit_and_the_trace_copies_the_hop(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            self.assertEqual(
                loop("open", "--feature", "demo", "--step", "look", "--candidate", "stage-gate",
                     "--on-exhaust", "human", "--on-fail", "stop", folder=folder).returncode,
                0,
            )
            acted = loop(
                "act", "--feature", "demo", "--step", "look",
                "--thought", "check the gate", "--action", "stage-gate", folder=folder,
            )
            self.assertEqual(acted.returncode, 0, acted.stderr)
            self.assertIn("TOOL python3 scripts/stage-gate.py", acted.stdout)
            failed = loop(
                "observe", "--feature", "demo", "--step", "look",
                "--text", "gate red", "--fail", folder=folder,
            )
            self.assertEqual(failed.returncode, 3)
            self.assertTrue(failed.stdout.startswith("EXIT stop"))
            notes = list((folder / "inbox").glob("*.yaml"))
            self.assertEqual(len(notes), 1)
            note = notes[0].read_text(encoding="utf-8")
            self.assertIn("tags:", note)
            self.assertIn("- react-tool-fail", note)
            self.assertIn("action stage-gate", note)
            self.assertIn("observation gate red", note)
            self.assertNotIn("status: consumed", note)
            shown = loop("show", "--feature", "demo", folder=folder)
            self.assertEqual(shown.returncode, 0, shown.stderr)
            self.assertIn("stage-gate", shown.stdout)
            self.assertIn("fail", shown.stdout)
            self.assertIn("WHY check the gate", shown.stdout)
            self.assertIn("RESULT gate red", shown.stdout)
            self.assertIn("TOOL python3 scripts/stage-gate.py", shown.stdout)
            path = folder / "demo--look.yaml"
            merged, err = trace.merge_react(TRACE % path)
            self.assertEqual(err, "")
            self.assertIn("kind: tool", merged)
            self.assertIn("stage-gate", merged)
            self.assertIn("gate red", merged)
            self.assertIn("python3 scripts/stage-gate.py", merged)

    def test_hop_cap_does_not_record_another_action(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            loop("open", "--feature", "demo", "--step", "look", "--candidate", "stage-gate",
                 "--max-hops", "1", folder=folder)
            loop("act", "--feature", "demo", "--step", "look",
                 "--thought", "once", "--action", "stage-gate", folder=folder)
            loop("observe", "--feature", "demo", "--step", "look", "--text", "seen", folder=folder)
            exhausted = loop(
                "act", "--feature", "demo", "--step", "look",
                "--thought", "again", "--action", "stage-gate", folder=folder,
            )
            self.assertEqual(exhausted.returncode, 3)
            self.assertTrue(exhausted.stdout.startswith("EXIT human"))
            text = (folder / "demo--look.yaml").read_text(encoding="utf-8")
            self.assertEqual(text.count("thought:"), 1)
            self.assertIn("status: exhausted", text)

    def test_recipe_rejects_a_gate_and_keeps_a_plain_step(self):
        ok: list[str] = []
        spec.check_recipe(
            recipe({"id": "look", "kind": "route.s4", "react": {"candidates": ["stage-gate"]}}),
            Path("demo.yaml"),
            ok,
        )
        self.assertEqual(ok, [])
        bad: list[str] = []
        spec.check_recipe(
            recipe({
                "id": "gate",
                "kind": "human.gate",
                "label": "将代写: deliver.aligned",
                "react": {"candidates": ["stage-gate"]},
            }),
            Path("demo.yaml"),
            bad,
        )
        self.assertTrue(any("cannot declare react" in item for item in bad))
        plain: list[str] = []
        spec.check_recipe(recipe({"id": "look", "kind": "route.s4"}), Path("demo.yaml"), plain)
        self.assertEqual(plain, [])

    def test_snapshot_keeps_react_off_a_step_that_does_not_declare_it(self):
        kept = workflow.step_snapshot({"id": "look", "kind": "route.s4", "status": "PASS"})
        self.assertNotIn("react", kept)
        self.assertNotIn("status", kept)
        joint = workflow.step_snapshot({
            "id": "look",
            "kind": "route.s4",
            "react": {"candidates": ["stage-gate"]},
        })
        self.assertEqual(joint["react"]["candidates"], ["stage-gate"])
        text = workflow._react_line(joint, "demo")
        self.assertIn("REACT candidates=stage-gate", text)
        log = workflow.sink_dir("react") / "demo--look.yaml"
        self.assertIn("REACT_LOG %s" % log, text)
        self.assertIn(
            "REACT_OPEN python3 scripts/react_loop.py open --feature demo --step look --candidate stage-gate",
            text,
        )
        self.assertIn("REACT_ACT ", text)
        self.assertIn("REACT_OBSERVE ", text)
        self.assertIn("REACT_FINISH ", text)
        self.assertIn("REACT_SHOW ", text)

    def test_two_tool_failures_heat_evolve_review(self):
        with tempfile.TemporaryDirectory() as raw:
            inbox = Path(raw) / "inbox"
            inbox.mkdir()
            note = (
                "schema_version: 1\nfeature: demo\nstatus: pending\ntags:\n"
                "- react-tool-fail\nnote: tool-fail step look action stage-gate observation gate red\n"
            )
            (inbox / "a.yaml").write_text(note, encoding="utf-8")
            (inbox / "b.yaml").write_text(note, encoding="utf-8")
            env = os.environ.copy()
            env["IDEV_INBOX_DIR"] = str(inbox)
            env["IDEV_PROPOSALS_DIR"] = str(Path(raw) / "proposals")
            env["IDEV_REVIEWS_DIR"] = str(Path(raw) / "reviews")
            proc = subprocess.run(
                ["bash", str(HERE / "evolve-review.sh"), "--dry-run", "--window", "1"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("hot_tags=react-tool-fail", proc.stdout)
            self.assertIn("signal=1", proc.stdout)
            self.assertEqual(list((Path(raw) / "proposals").glob("*.md")), [])

    def test_tool_fail_does_not_inherit_the_exhaust_exit(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            loop("open", "--feature", "demo", "--step", "look", "--candidate", "stage-gate",
                 "--on-exhaust", "stop", folder=folder)
            loop("act", "--feature", "demo", "--step", "look",
                 "--thought", "check", "--action", "stage-gate", folder=folder)
            failed = loop(
                "observe", "--feature", "demo", "--step", "look",
                "--text", "red", "--fail", folder=folder,
            )
            self.assertEqual(failed.returncode, 3)
            self.assertTrue(failed.stdout.startswith("EXIT human"))
            text = (folder / "demo--look.yaml").read_text(encoding="utf-8")
            self.assertIn("status: failed", text)

    def test_skip_keeps_the_loop_open_and_writes_no_inbox(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            loop("open", "--feature", "demo", "--step", "look", "--candidate", "stage-gate",
                 "--on-fail", "skip", folder=folder)
            loop("act", "--feature", "demo", "--step", "look",
                 "--thought", "check", "--action", "stage-gate", folder=folder)
            skipped = loop(
                "observe", "--feature", "demo", "--step", "look",
                "--text", "red", "--fail", folder=folder,
            )
            self.assertEqual(skipped.returncode, 0, skipped.stderr)
            self.assertIn("SKIP stage-gate", skipped.stdout)
            text = (folder / "demo--look.yaml").read_text(encoding="utf-8")
            self.assertIn("status: open", text)
            self.assertIn("ok: false", text)
            self.assertFalse((folder / "inbox").exists())
            again = loop(
                "act", "--feature", "demo", "--step", "look",
                "--thought", "once more", "--action", "stage-gate", folder=folder,
            )
            self.assertEqual(again.returncode, 0, again.stderr)


if __name__ == "__main__":
    unittest.main()
