#!/usr/bin/env python3
"""A trace says what the round delegated and recorded from the records, and
its signoff check reads what the round did, not which words it used.

    python3 scripts/test_trace_derive.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
KERNEL = HERE.parent
TRACE = HERE / "trace.py"
TRACES = KERNEL / "test" / "fixtures" / "traces"
SEVEN = TRACES / "20261028-007.yaml"
# 016 confirmed with nothing to write and said so; 027 read aligned=true back from deliver.yaml.
CLEAN = (TRACES / "20261025-016.yaml", TRACES / "20261028-027.yaml")


def ago(hours: float) -> str:
    return (dt.datetime.now().astimezone() - dt.timedelta(hours=hours)).isoformat(timespec="seconds")


BASE = """schema_version: 2
at: "{at}"
feature: demo
intent: "人确认需求"
invoke:
  trigger: "确认"
  matched: "需求通过"
  how: continuation
route:
  module: deliver
  scenario: S2
  convention_class: docs
  stage: req
  risk_tier: P1
  why: "确认需求"
thinking:
  summary: "人说确认"
calls:
  - kind: skill
    name: idev
    from: user
    to: skill:idev
    result: continuation
decisions:
{decisions}"""

CONFIRM = "  - kind: call\n    chose: chat-confirm-signoff\n    why: \"确认原话写入需求通过\"\n"
REFUSE = "  - kind: refuse\n    chose: arch.accepted\n    why: \"禁止代写架构通过\"\n"
ROUTE = "  - kind: route\n    chose: deliver\n    why: \"写入 sealed 之前先看 baseline\"\n"


def run(*args: str, cwd: Path | None = None, stdin: str | None = None, env: dict | None = None):
    return subprocess.run([sys.executable, *args], cwd=cwd, input=stdin, capture_output=True,
                          text=True, timeout=60, env=env)


class SignoffReadsStructure(unittest.TestCase):
    def check(self, text: str) -> subprocess.CompletedProcess:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as fh:
            fh.write(text)
        try:
            return run(str(TRACE), "check", fh.name)
        finally:
            os.unlink(fh.name)

    def test_a_confirmed_write_needs_a_signoff_whatever_else_the_trace_says(self) -> None:
        for decisions in (CONFIRM, CONFIRM + REFUSE):
            done = self.check(BASE.format(at=ago(0), decisions=decisions))
            self.assertNotEqual(done.returncode, 0, decisions)
            self.assertIn("signoff block required", done.stdout)

    def test_a_trace_that_only_refuses_or_mentions_a_mark_needs_none(self) -> None:
        done = self.check(BASE.format(at=ago(0), decisions=REFUSE + ROUTE))
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_a_confirmation_that_wrote_nothing_passes_when_the_signoff_says_so(self) -> None:
        said = 'signoff:\n  status: none\n  marks: []\n  by: alice\n  evidence: "quote「确认」；无停问点，未写签字字段"\n'
        done = self.check(BASE.format(at=ago(0), decisions=CONFIRM) + said)
        self.assertEqual(done.returncode, 0, done.stdout)
        claimed = said.replace("marks: []", "marks: [accepted]")
        done = self.check(BASE.format(at=ago(0), decisions=CONFIRM) + claimed)
        self.assertIn("signoff.status must be recorded|pending", done.stdout)

    def test_a_repo_call_needs_a_signoff_only_when_it_wrote_a_mark(self) -> None:
        call = "  - kind: repo\n    name: .idev/task/demo/deliver.yaml\n    result: \"%s\"\ndecisions:\n"
        for result, needs in (("stage=done aligned=true reopen_baseline=false", False), ("写入 aligned: true", True)):
            done = self.check(BASE.format(at=ago(0), decisions=ROUTE).replace("decisions:\n", call % result, 1))
            self.assertEqual(done.returncode != 0, needs, result + "\n" + done.stdout)

    def test_real_traces_raise_only_the_one_that_wrote_sealed(self) -> None:
        done = run(str(TRACE), "check", str(SEVEN))
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertIn("signoff block required", done.stdout)
        for clean in CLEAN:
            done = run(str(TRACE), "check", str(clean))
            self.assertEqual(done.returncode, 0, clean.name + "\n" + done.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            traces = Path(tmp) / "traces"
            traces.mkdir()
            for real in (SEVEN, *CLEAN):
                (traces / real.name).write_text(real.read_text(encoding="utf-8"), encoding="utf-8")
            audit = run(str(HERE / "audit_traces_lib.py"), str(traces), "5")
            self.assertEqual(audit.returncode, 0, audit.stderr)
            self.assertIn("HARD_COUNT=1", audit.stdout)
            self.assertEqual(re.findall(r"(?m)^- (\S+) .*seal-write-without-signoff", audit.stdout), [SEVEN.name])


class DerivedRound(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        (self.repo / ".git").mkdir(parents=True)
        self.ticket = self.repo / ".idev" / "task" / "demo"
        self.records = self.ticket / "workflow" / "delegations"
        (self.records / "R1").mkdir(parents=True)
        self.traces = self.repo / ".idev" / "traces"
        self.traces.mkdir(parents=True)
        (self.traces / "20200101-001.yaml").write_text(
            BASE.format(at=ago(3), decisions=ROUTE), encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if k not in ("IDEV_TRACE_DIR", "IDEV_PRODUCT_REPO", "IDEV_RUN_ID")}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def record(self, name: str, agent: str, step: str, at: str, **extra) -> dict:
        body = {"schema_version": 1, "feature": "demo", "step": step, "kind": extra.pop("kind", "review.report"),
                "agent": agent, "attempt": 1, "at": at, "report": {"status": "PASS", "raw": "STATUS: PASS\n"}, **extra}
        (self.records / "R1" / name).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return body

    def append(self, text: str) -> str:
        done = run(str(TRACE), "append", "-", cwd=self.repo, stdin=text, env=self.env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        stored = re.search(r"^wrote (.+)$", done.stdout, re.M)
        self.assertIsNotNone(stored, done.stdout)
        return Path(stored.group(1)).read_text(encoding="utf-8")

    @staticmethod
    def entries(text: str, heading: str) -> list[str]:
        body = re.search(rf"(?m)^{heading}:[^\n]*\n((?:[ \t].*\n)*)", text)
        if body is None:
            return ["<no block>"]
        return re.findall(r"(?m)^  - (.*)$", body.group(1))

    def test_append_lists_every_delegation_of_the_round_once(self) -> None:
        report = self.record("report-1.yaml", "idev-reviewer", "report", ago(2))
        (self.records / "report-1.yaml").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        self.record("fix-1.yaml", "idev-coder", "fix", ago(1), kind="review.fix")
        self.record("fix-1.verify.yaml", "idev-reviewer", "fix", ago(0.9), kind="review.fix", role="verifier")
        self.record("old-1.yaml", "idev-ops", "old", ago(5), kind="ops.classify")

        conductor = BASE.format(at=ago(0), decisions=ROUTE) + "delegations:\n  - agent: idev-ops\n    step: made-up\n"
        first = self.append(conductor)
        self.assertEqual(len(self.entries(first, "delegations")), 3, first)
        self.assertNotIn("made-up", first)
        self.assertNotIn("old", "".join(self.entries(first, "delegations")))
        self.assertIn("role: verifier", first)
        shown = sorted(self.traces.glob("2*.yaml"))[-1]
        path = run(str(TRACE), "path", str(shown), cwd=self.repo, env=self.env)
        self.assertRegex(path.stdout, r"(?m)^delegated: .*idev-reviewer fix#1 verify")

        second = self.append(BASE.format(at=ago(0), decisions=ROUTE))
        self.assertEqual(self.entries(second, "delegations"), [], second)

    def test_a_record_lands_in_one_trace_when_the_conductor_dated_it_early(self) -> None:
        self.record("fix-1.yaml", "idev-coder", "fix", ago(0.5), kind="review.fix")
        first = self.append(BASE.format(at=ago(1), decisions=ROUTE))
        self.assertEqual(len(self.entries(first, "delegations")), 1, first)
        second = self.append(BASE.format(at=ago(0.2), decisions=ROUTE))
        self.assertEqual(self.entries(second, "delegations"), [], second)

    def test_a_gate_the_round_recorded_fills_the_signoff(self) -> None:
        run_yaml = self.ticket / "workflow" / "run.yaml"
        run_yaml.write_text(
            "run_id: R1\nfeature: demo\nsteps:\n"
            f"- id: plan\n  kind: verify.plan\n  status: PASS\n  at: '{ago(1)}'\n"
            "  delegated: {agent: idev-verifier}\n"
            "- id: gate-plan\n  kind: human.gate\n  with: {gate_type: accepted_plan}\n"
            f"  signoff: {{by: alice, quote: 确认, assurance: chat}}\n  status: PASS\n  at: '{ago(0.5)}'\n",
            encoding="utf-8")
        stored = self.append(BASE.format(at=ago(0), decisions=CONFIRM))
        self.assertEqual(len(self.entries(stored, "recorded")), 2, stored)
        signoff = re.search(r"(?m)^signoff:\n((?:[ \t].*\n)*)", stored)
        self.assertIsNotNone(signoff, stored)
        self.assertIn("by: alice", signoff.group(1))
        self.assertIn("accepted", signoff.group(1))
        self.assertIn("gate-plan", signoff.group(1))


if __name__ == "__main__":
    unittest.main(verbosity=1)
