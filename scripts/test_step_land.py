#!/usr/bin/env python3
"""step and land: the conductor's commands for one delegated step.

`step` hands the step to its agent and prints the brief the machine filled.
`land` takes the agent's report and does the rest: the delegation record,
then either the verify lease and the verifier's brief, or the step's record.
A step its kind has verified independently takes three commands (step, land
the writer, land the verifier); any other delegated step takes two. Go lane:
a binary built from this tree and a store of the test's own.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
KERNEL = HERE.parent
sys.path.insert(0, str(HERE / "lib"))

import safeyaml  # noqa: E402
import testenv  # noqa: E402

testenv.pin()

WORKFLOW = HERE / "workflow.py"
COMPLETE = (
    "STATUS: PASS\nEVIDENCE: r.md\nFACTS: codegraph src/app.py:main and git diff\n"
    "DOC_DRIFT: none\nASSUMED: none\nSCOPE: src/app.py:main\nREAD: src/app.py:main\n"
    "CHANGED: src/app.py\nREVERT: git checkout -- src/app.py\n"
    "CHANGE_KIND: local\nCANON_TRIGGER: none\nTABLE_HIT: none\n"
)
NO_EVIDENCE = COMPLETE.replace("EVIDENCE: r.md\n", "")
REVIEW = "STATUS: PASS\nEVIDENCE: review.md\nFACTS: read src/app.py:main and git diff\nDOC_DRIFT: none\nASSUMED: none\n"
RAN = "STATUS: PASS\nEVIDENCE: verify/run.md\nFACTS: codegraph src/app.py:main and the pytest output\nDOC_DRIFT: none\nASSUMED: none\n"


class StepAndLand(unittest.TestCase):
    def setUp(self) -> None:
        binary = testenv.go_binary()
        if binary is None:
            self.skipTest("no idev binary for this run: the Go toolchain is missing")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve() / "one"
        self.ticket = self.repo / ".idev" / "task" / "demo"
        (self.ticket / "workflow").mkdir(parents=True)
        (self.ticket / "verify").mkdir()
        (self.repo / ".idev" / "workflows").mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        (self.repo / ".idev" / "marker.yaml").write_text(
            "schema_version: 1\nmarker: idev\nid: demo\nevolve: false\n", encoding="utf-8")
        (self.ticket / "deliver.yaml").write_text("stage: code\nrisk_tier: P1\n", encoding="utf-8")
        (self.ticket / "arch.yaml").write_text(
            "impact_candidates:\n  - {path: src/app.py, hop: 0, include: true}\n", encoding="utf-8")
        (self.repo / ".idev" / "workflows" / "demo-code.yaml").write_text(
            "schema_version: 1\nid: demo-code\nsummary: x\n"
            "params:\n  - {name: feature, required: true, from: user}\n"
            "steps:\n  - {id: c, kind: deliver.code_pass}\n  - {id: r, kind: verify.run}\n",
            encoding="utf-8")
        (self.repo / "review.md").write_text("reviewed\n", encoding="utf-8")
        (self.ticket / "verify" / "run.md").write_text("ran\n", encoding="utf-8")
        self.env = dict(os.environ, IDEV_BIN=binary, IDEV_DATA=str(Path(tmp.name) / "data"))
        self.env.pop("IDEV_ENGINE", None)
        self.env.pop("IDEV_RUN_WRITER", None)
        self.run_workflow("start", "demo-code", "--feature", "demo")
        self.commands: list[str] = []

    def run_workflow(self, *args: str, stdin: str | None = None) -> tuple[int, str]:
        done = subprocess.run([sys.executable, str(WORKFLOW), *args], cwd=self.repo, env=self.env,
                              input=stdin, capture_output=True, text=True, timeout=120)
        return done.returncode, done.stdout + done.stderr

    def conductor(self, verb: str, step: str, stdin: str | None = None, ok: bool = True, *extra: str) -> str:
        args = [verb, step, "--feature", "demo"] + (["--report", "-"] if verb == "land" else []) + list(extra)
        code, out = self.run_workflow(*args, stdin=stdin)
        self.commands.append(verb)
        self.assertEqual(code == 0, ok, out)
        return out

    def step(self, sid: str = "c") -> dict:
        run = safeyaml.mapping(self.ticket / "workflow" / "run.yaml")
        return next(s for s in run["steps"] if s["id"] == sid)

    def records(self) -> Path:
        run = safeyaml.mapping(self.ticket / "workflow" / "run.yaml")
        return self.ticket / "workflow" / "delegations" / str(run["run_id"])

    def test_a_reviewed_step_takes_three_commands(self) -> None:
        out = self.conductor("step", "c")
        self.assertIn("DELEGATE c -> idev-coder", out)
        self.assertIn("LEASE ", out)
        self.assertIn("票目录: .idev/task/demo", out)
        self.assertIn("必读: " + str(KERNEL / "deliver" / "SKILL.md"), out)
        self.assertIn("IDEV_ROOT: " + str(KERNEL), out)
        self.assertIn("workflow.py land c", out)

        out = self.conductor("land", "c", COMPLETE)
        self.assertIn("DELEGATE c -> idev-reviewer", out)
        self.assertIn("BRIEF c -> idev-reviewer verify attempt 1", out)
        self.assertRegex(out, r"复核对象: \.idev/task/demo/workflow/delegations/[^/]+/c-1\.yaml")
        self.assertEqual(self.step()["verify_lease"]["agent"], "idev-reviewer")
        self.assertNotIn("status", self.step())

        out = self.conductor("land", "c", REVIEW)
        step = self.step()
        self.assertEqual(step["status"], "PASS")
        self.assertEqual(step["evidence"], "r.md")
        self.assertEqual(step["verification"]["by"], "idev-reviewer")
        self.assertEqual(step["verification"]["evidence"], "review.md")
        writer = safeyaml.mapping(self.records() / "c-1.yaml")
        self.assertEqual(writer["checks"]["brief-complete"], "PASS")
        self.assertIn("duration_s", writer)
        self.assertTrue((self.records() / "c-1.verify.yaml").is_file())
        self.assertIn("NEXT r", out)
        self.assertEqual(self.commands, ["step", "land", "land"])
        self.assertEqual(list((self.ticket / "workflow" / "briefs").iterdir()), [])

    def test_a_step_with_no_reviewer_takes_two(self) -> None:
        self.conductor("step", "c")
        self.conductor("land", "c", COMPLETE)
        self.conductor("land", "c", REVIEW)
        (self.ticket / "workflow" / "agent-feedback.yaml").write_text(
            "status: none\nby: alice\nnote: nothing to add\n", encoding="utf-8")
        self.commands.clear()
        out = self.conductor("step", "r")
        self.assertIn("DELEGATE r -> idev-verifier", out)
        out = self.conductor("land", "r", RAN)
        self.assertEqual(self.step("r")["status"], "PASS")
        self.assertEqual(self.step("r")["evidence"], "verify/run.md")
        self.assertIn("RUN DONE", out)
        self.assertEqual(self.commands, ["step", "land"])

    def test_a_writer_failing_its_checks_is_sent_back_before_review(self) -> None:
        self.conductor("step", "c")
        out = self.conductor("land", "c", NO_EVIDENCE, ok=False)
        self.assertIn("evidence-present", out)
        self.assertIn("workflow.py step c", out)
        self.assertNotIn("verify_lease", self.step())
        out = self.conductor("step", "c")
        self.assertIn("attempt: 2", out)
        self.assertIn("prior_failure:", out)
        self.assertIn("evidence-present", out)
        self.conductor("land", "c", COMPLETE)
        retry = safeyaml.mapping(self.records() / "c-2.yaml")
        self.assertIn("evidence-present", retry["brief"]["prior_failure"])
        self.assertIn("不重判上次产物", retry["brief"]["prior_failure"])
        self.assertEqual(self.step()["verify_lease"]["agent"], "idev-reviewer")

    def test_a_new_report_on_a_used_brief_needs_the_retry_brief(self) -> None:
        self.conductor("step", "c")
        self.conductor("land", "c", NO_EVIDENCE, ok=False)
        out = self.conductor("land", "c", COMPLETE, ok=False)
        self.assertIn("workflow.py step c prints the retry brief", out)
        self.assertFalse((self.records() / "c-2.yaml").exists())

    def test_landing_the_writer_report_twice_keeps_one_record(self) -> None:
        self.conductor("step", "c")
        self.conductor("land", "c", COMPLETE)
        out = self.conductor("land", "c", COMPLETE)
        self.assertFalse((self.records() / "c-2.yaml").exists())
        self.assertFalse((self.records() / "c-1.verify.yaml").exists())
        self.assertIn("BRIEF c -> idev-reviewer verify attempt 1", out)

    def test_next_points_at_step_and_land(self) -> None:
        code, out = self.run_workflow("next", "--feature", "demo")
        self.assertEqual(code, 0, out)
        self.assertIn("STEP workflow.py step c --feature demo", out)

    def test_findings_accepted_at_the_writer_reach_the_record(self) -> None:
        self.conductor("step", "c")
        reason = "r.md was attached by hand; the diff is the evidence"
        self.conductor("land", "c", NO_EVIDENCE, True, "--accept-with-findings", reason)
        self.conductor("land", "c", REVIEW)
        step = self.step()
        self.assertEqual(step["status"], "PASS")
        self.assertEqual(step["accepted_findings"]["checks"], ["evidence-present"])
        self.assertEqual(step["accepted_findings"]["reason"], reason)

    def test_land_needs_the_brief_step_printed(self) -> None:
        out = self.conductor("land", "c", COMPLETE, ok=False)
        self.assertIn("workflow.py step c", out)
        self.assertFalse(self.records().exists() and any(self.records().iterdir()))


if __name__ == "__main__":
    unittest.main()
