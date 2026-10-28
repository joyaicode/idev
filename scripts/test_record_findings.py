#!/usr/bin/env python3
"""record PASS against the delegation's machine checks, and the verifier's record.

A PASS whose delegation fails a check the agent owns is refused unless the
conductor writes why it passes anyway; the reason goes into the audit chain.
The verifier's report sits beside the writer's attempt instead of taking the
next attempt number. Go lane: a binary built from this tree and a store of
the test's own.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))

import safeyaml  # noqa: E402
import testenv  # noqa: E402

testenv.pin()

WORKFLOW = HERE / "workflow.py"
DELEGATION = HERE / "delegation.py"
VERIFIED = ("--verified-by", "idev-reviewer", "--verify-evidence", "review.md")

COMPLETE = (
    "STATUS: PASS\nEVIDENCE: r.md\nFACTS: codegraph src/app.py:main and git diff\n"
    "DOC_DRIFT: none\nASSUMED: none\nSCOPE: src/app.py:main\nREAD: src/app.py:main\n"
    "CHANGED: src/app.py\nREVERT: git checkout -- src/app.py\n"
    "CHANGE_KIND: local\nCANON_TRIGGER: none\nTABLE_HIT: none\n"
)
NO_EVIDENCE = COMPLETE.replace("EVIDENCE: r.md\n", "")
REVIEW = "STATUS: PASS\nEVIDENCE: review.md\nFACTS: read src/app.py:main and git diff\nDOC_DRIFT: none\nASSUMED: none\n"


class RecordAgainstChecks(unittest.TestCase):
    def setUp(self) -> None:
        binary = testenv.go_binary()
        if binary is None:
            self.skipTest("no idev binary for this run: the Go toolchain is missing")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve() / "one"
        ticket = self.repo / ".idev" / "task" / "demo"
        (ticket / "workflow").mkdir(parents=True)
        (self.repo / ".idev" / "workflows").mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        (self.repo / ".idev" / "marker.yaml").write_text(
            "schema_version: 1\nmarker: idev\nid: demo\nevolve: false\n", encoding="utf-8")
        (ticket / "deliver.yaml").write_text("stage: code\nrisk_tier: P1\n", encoding="utf-8")
        (ticket / "arch.yaml").write_text(
            "impact_candidates:\n  - {path: src/app.py, hop: 0, include: true}\n", encoding="utf-8")
        (self.repo / ".idev" / "workflows" / "demo-code.yaml").write_text(
            "schema_version: 1\nid: demo-code\nsummary: x\n"
            "params:\n  - {name: feature, required: true, from: user}\n"
            "steps:\n  - {id: c, kind: deliver.code_pass}\n  - {id: r, kind: verify.run}\n",
            encoding="utf-8")
        (self.repo / "review.md").write_text("reviewed\n", encoding="utf-8")
        self.env = dict(os.environ, IDEV_BIN=binary, IDEV_DATA=str(Path(tmp.name) / "data"))
        self.env.pop("IDEV_ENGINE", None)
        self.env.pop("IDEV_RUN_WRITER", None)
        self.workflow("start", "demo-code", "--feature", "demo")
        self.workflow("delegate", "c", "--feature", "demo")

    def run_script(self, script: Path, *args: str, stdin: str | None = None) -> tuple[int, str]:
        done = subprocess.run([sys.executable, str(script), *args], cwd=self.repo, env=self.env,
                              input=stdin, capture_output=True, text=True, timeout=120)
        return done.returncode, done.stdout + done.stderr

    def workflow(self, *args: str, ok: bool = True) -> str:
        code, out = self.run_script(WORKFLOW, *args)
        self.assertEqual(code == 0, ok, out)
        return out

    def write(self, agent: str, raw: str, role: str = "", attempt: int = 1, prior: str = "",
              clean: bool = True) -> str:
        brief = {"ticket_home": ".idev/task/demo", "repo": str(self.repo), "stage": "code",
                 "must_read": [".idev/task/demo/arch.yaml"], "idev_root": str(HERE.parent)}
        if prior:
            brief["prior_failure"] = prior
        record = {"step": "c", "attempt": attempt, "kind": "deliver.code_pass", "agent": agent,
                  "brief": brief, "report": {"raw": raw}}
        if role:
            record["role"] = role
        code, out = self.run_script(DELEGATION, "write", "--feature", "demo", stdin=json.dumps(record))
        self.assertIn("OK ", out)
        self.assertEqual(code == 0, clean, out)
        return out

    def records(self) -> Path:
        code, out = self.run_script(DELEGATION, "dir", "--feature", "demo")
        self.assertEqual(code, 0, out)
        return Path(out.strip().splitlines()[-1])

    def step(self) -> dict:
        run = safeyaml.mapping(self.repo / ".idev/task/demo/workflow/run.yaml")
        return next(s for s in run["steps"] if s["id"] == "c")

    def audit(self, action: str) -> list[dict]:
        done = subprocess.run([self.env["IDEV_BIN"], "audit", "export"], env=self.env,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        events = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
        return [e for e in events if e.get("action") == action]

    def verified(self) -> None:
        self.workflow("delegate", "c", "--verify", "--feature", "demo")
        self.write("idev-reviewer", REVIEW, role="verifier")

    def pass_c(self, *extra: str, ok: bool = True) -> str:
        return self.workflow("record", "c", "PASS", "--feature", "demo", "--evidence", "r.md",
                             *VERIFIED, *extra, ok=ok)

    def test_a_pass_the_checks_reject_is_refused_and_names_them(self) -> None:
        self.write("idev-coder", NO_EVIDENCE, clean=False)
        self.verified()
        out = self.pass_c(ok=False)
        self.assertIn("fails machine checks: evidence-present", out)
        self.assertIn("--accept-with-findings", out)
        self.assertNotEqual(self.step().get("status"), "PASS")

    def test_accepting_the_findings_records_the_reason(self) -> None:
        self.write("idev-coder", NO_EVIDENCE, clean=False)
        self.verified()
        reason = "the diff itself is the evidence; r.md was attached by hand"
        self.pass_c("--accept-with-findings", reason)
        step = self.step()
        self.assertEqual(step.get("status"), "PASS")
        self.assertEqual(step["accepted_findings"]["checks"], ["evidence-present"])
        self.assertEqual(step["accepted_findings"]["reason"], reason)
        accepted = self.audit("delegation.accepted")
        self.assertEqual(len(accepted), 1, accepted)
        detail = accepted[0]["detail"]
        self.assertEqual(detail["accepted_with_findings"], ["evidence-present"])
        self.assertEqual(detail["reason"], reason)

    def test_a_reason_with_nothing_to_accept_is_refused(self) -> None:
        self.write("idev-coder", COMPLETE)
        self.verified()
        out = self.pass_c("--accept-with-findings", "just in case", ok=False)
        self.assertIn("fails no machine check", out)
        self.pass_c()
        self.assertNotIn("accepted_findings", self.step())

    def test_the_verifier_records_beside_the_writer_attempt(self) -> None:
        self.write("idev-coder", COMPLETE)
        writer = safeyaml.mapping(self.records() / "c-1.yaml")
        self.assertRegex(str(writer.get("checker")), r"^[0-9a-f]{12}$")
        self.assertIn("workflow.py delegate c --verify", self.workflow("next", "--feature", "demo"))
        self.workflow("delegate", "c", "--verify", "--feature", "demo")
        self.write("idev-reviewer", REVIEW, role="verifier")
        verification = safeyaml.mapping(self.records() / "c-1.verify.yaml")
        self.assertEqual(verification["role"], "verifier")
        self.assertEqual(verification["attempt"], 1)
        self.assertEqual(verification["verifies"]["delegation_id"], writer["delegation_id"])
        recorded = self.audit("verification.recorded")
        self.assertEqual([e["detail"]["writer"] for e in recorded], ["idev-coder"])

        record = {"step": "c", "kind": "deliver.code_pass", "agent": "idev-reviewer", "role": "verifier",
                  "report": {"raw": REVIEW}}
        code, out = self.run_script(DELEGATION, "write", "--feature", "demo", stdin=json.dumps(record))
        self.assertNotEqual(code, 0, out)
        self.assertIn("already records the verification", out)

        self.pass_c()
        self.assertEqual(self.step().get("status"), "PASS")

    def test_a_verification_does_not_take_the_next_attempt(self) -> None:
        self.write("idev-coder", COMPLETE)
        self.workflow("delegate", "c", "--verify", "--feature", "demo")
        self.write("idev-reviewer", REVIEW, role="verifier")
        self.write("idev-coder", COMPLETE, attempt=2, prior="the reviewer found a missing test")
        retry = safeyaml.mapping(self.records() / "c-2.yaml")
        self.assertEqual(retry["attempt"], 2)
        self.assertFalse((self.records() / "c-3.yaml").exists())

    def test_the_verifier_needs_a_writer_record_first(self) -> None:
        record = {"step": "c", "kind": "deliver.code_pass", "agent": "idev-reviewer", "role": "verifier",
                  "report": {"raw": REVIEW}}
        code, out = self.run_script(DELEGATION, "write", "--feature", "demo", stdin=json.dumps(record))
        self.assertNotEqual(code, 0, out)
        self.assertIn("no writer record for c", out)


if __name__ == "__main__":
    unittest.main()
