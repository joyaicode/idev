#!/usr/bin/env python3
"""record <gate> AUTO runs the gate's own check; a saved file proves nothing.

AUTO used to read whatever file --evidence named and pass on a `0 FAIL` line,
so a hand-written file stood in for a person. These cases drive the real CLI
on the example ticket that passes every stage.

    python3 scripts/test_auto_gate.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDEV = HERE.parent
sys.path.insert(0, str(HERE / "lib"))

import safeyaml  # noqa: E402
import testenv  # noqa: E402
import workflow_spec as spec  # noqa: E402

testenv.pin()

FEATURE = "auto-demo"
LOG = "verify/plan-check.log"


def assemble(repo: Path) -> Path:
    """The example ticket, put together the way test/golden/record.sh does."""
    ticket = repo / ".idev" / "task" / FEATURE
    (ticket / "verify").mkdir(parents=True)
    (repo / ".git").mkdir()
    base = IDEV / "deliver" / "references"
    baseline = (base / "baseline.example.yaml").read_text(encoding="utf-8")
    (ticket / "baseline.yaml").write_text(baseline.replace("sealed: false", "sealed: true"), encoding="utf-8")
    for src, dst in (
        ("req.example.yaml", "req.yaml"),
        ("arch.example.yaml", "arch.yaml"),
        ("deliver.example.yaml", "deliver.yaml"),
        ("review.example.md", "review.md"),
        ("deliver-eval.example.md", "deliver-eval.md"),
        ("design.example.md", "design.md"),
    ):
        shutil.copy(base / src, ticket / dst)
    shutil.copy(IDEV / "verify" / "references" / "plan.example.yaml", ticket / "verify" / "plan.yaml")
    (ticket / "grill.md").write_text(
        "convention: grilling\nfrontier: empty\nshared_understanding: true\n"
        "arch_frontier: empty\narch_shared_understanding: true\n\n"
        "❓ **Q1** - **scope**: settled in the example baseline\n➡️ keep the sealed baseline\n\n"
        "## arch\n\n❓ **Q1** - **rollback**: how does the design back out\n➡️ the approval.enabled switch\n",
        encoding="utf-8",
    )
    spec_dir = repo / ".idev" / "docs" / "spec"
    spec_dir.mkdir(parents=True)
    (spec_dir / f"{FEATURE}.md").write_text("restates the sealed baseline\n", encoding="utf-8")
    return ticket


def cli(repo: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    """The Python lane on a machine with no Go build: what the golden files record."""
    env = {**os.environ, "IDEV_ENGINE": "python", "IDEV_BIN": "off", "PYTHONUNBUFFERED": "1"}
    env.pop("IDEV_PRODUCT_REPO", None)
    return subprocess.run(
        [sys.executable, str(HERE / script), "--repo", str(repo), *args],
        capture_output=True, text=True, env=env, cwd=repo,
    )


def said(done: subprocess.CompletedProcess) -> str:
    return done.stdout + done.stderr


class AutoGate(unittest.TestCase):
    """dev-logic: plan, then gate-plan with auto_tiers [P1, P2], on a P1 ticket."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()
        self.ticket = assemble(self.repo)
        self.run_path = self.ticket / "workflow" / "run.yaml"
        for args in (
            ("start", "dev-logic", "--feature", FEATURE),
            ("record", "plan", "PASS", "--evidence", "verify/plan.yaml", "--feature", FEATURE),
        ):
            done = cli(self.repo, "workflow.py", *args)
            self.assertEqual(done.returncode, 0, said(done))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def auto(self, *extra: str) -> subprocess.CompletedProcess:
        return cli(self.repo, "workflow.py", "record", "gate-plan", "AUTO", "--feature", FEATURE, *extra)

    def gate(self) -> dict:
        run = safeyaml.mapping(self.run_path) or {}
        return next(s for s in run["steps"] if s["id"] == "gate-plan")

    def edit_plan(self, change) -> None:
        path = self.ticket / "verify" / "plan.yaml"
        data = safeyaml.mapping(path)
        change(data)
        path.write_text(safeyaml.dump(data), encoding="utf-8")

    def test_the_hint_says_auto_runs_the_check(self) -> None:
        out = said(cli(self.repo, "workflow.py", "next", "--feature", FEATURE))
        self.assertIn("record AUTO runs check-feature verify-plan", out)

    def test_a_clean_plan_passes_on_the_check_it_ran(self) -> None:
        done = self.auto()
        self.assertEqual(done.returncode, 0, said(done))
        log = self.ticket / LOG
        self.assertIn("0 FAIL", log.read_text(encoding="utf-8").splitlines())
        gate = self.gate()
        self.assertEqual(gate["status"], "AUTO")
        self.assertEqual(gate["evidence"], LOG)
        self.assertNotIn("signoff", gate)
        self.assertEqual(gate["auto"]["stage"], "verify-plan")
        self.assertEqual(gate["auto"]["exit"], 0)
        self.assertEqual(gate["auto"]["sha256"], hashlib.sha256(log.read_bytes()).hexdigest())
        checked = subprocess.run(
            [sys.executable, str(HERE / "workflow-check.py"), "--run", str(self.run_path)],
            capture_output=True, text=True,
        )
        self.assertEqual(checked.returncode, 0, said(checked))

    def test_a_saved_clean_file_is_not_trusted(self) -> None:
        (self.ticket / "design.md").unlink()
        (self.ticket / LOG).write_text("---\n0 FAIL\n", encoding="utf-8")
        done = self.auto("--evidence", LOG)
        self.assertEqual(done.returncode, 2, said(done))
        self.assertIn("missing design.md", said(done))
        self.assertNotIn("status", self.gate())
        self.assertIn("missing design.md", (self.ticket / LOG).read_text(encoding="utf-8"))

    def test_a_signal_in_the_check_stops_it(self) -> None:
        self.edit_plan(lambda d: d["cases"][1].pop("runner"))
        done = self.auto()
        self.assertEqual(done.returncode, 2, said(done))
        self.assertIn("question for a person", said(done))
        self.assertIn("compat-enabled-unchanged", said(done))
        self.assertNotIn("status", self.gate())

    def test_an_unanswered_signal_on_the_plan_step_stops_it(self) -> None:
        records = Path(cli(self.repo, "delegation.py", "dir", "--feature", FEATURE).stdout.strip())
        records.mkdir(parents=True, exist_ok=True)
        (records / "plan-2.yaml").write_text(safeyaml.dump({
            "step": "plan", "attempt": 2, "kind": "verify.plan", "agent": "idev-verifier",
            "signals": ["[承重] 回放库开跑前是空的"],
            "report": {"raw": "STATUS: PASS\nASSUMED: [承重] 回放库开跑前是空的\n"},
        }), encoding="utf-8")
        done = self.auto()
        self.assertEqual(done.returncode, 2, said(done))
        self.assertIn("回放库开跑前是空的", said(done))
        decided = cli(
            self.repo, "workflow.py", "decide", "plan", "--signal", "[承重] 回放库开跑前是空的",
            "--question", "回放库开跑前是空的吗", "--answer", "是", "--quote", "1", "--feature", FEATURE,
        )
        self.assertEqual(decided.returncode, 0, said(decided))
        done = self.auto()
        self.assertEqual(done.returncode, 0, said(done))

    def test_evidence_can_only_name_the_log_it_writes(self) -> None:
        done = self.auto("--evidence", "review.md")
        self.assertEqual(done.returncode, 2, said(done))
        self.assertIn(LOG, said(done))

    def test_auto_is_not_a_signoff(self) -> None:
        done = self.auto("--by", "wangwei794")
        self.assertEqual(done.returncode, 2, said(done))
        self.assertIn("not a signoff", said(done))


class GoWriterRecords(unittest.TestCase):
    """IDEV_RUN_WRITER=go: workflow computes, idev run write owns the bytes."""

    def test_a_plan_pass_goes_through_go(self) -> None:
        idev = testenv.go_binary()
        if idev is None:
            self.skipTest("no idev binary for this run: the Go toolchain is missing")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name).resolve()
        assemble(repo)
        env = {
            **os.environ,
            "IDEV_RUN_WRITER": "go",
            "IDEV_BIN": str(idev),
            "IDEV_DATA": str(repo / ".idev-data"),
            "PYTHONUNBUFFERED": "1",
        }
        env.pop("IDEV_ENGINE", None)
        env.pop("IDEV_PRODUCT_REPO", None)
        for args in (
            ("start", "dev-logic", "--feature", FEATURE),
            ("delegate", "plan", "--feature", FEATURE),
            ("record", "plan", "PASS", "--evidence", "verify/plan.yaml", "--feature", FEATURE),
        ):
            done = subprocess.run(
                [sys.executable, str(HERE / "workflow.py"), "--repo", str(repo), *args],
                capture_output=True, text=True, env=env, cwd=repo,
            )
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        run = safeyaml.mapping(repo / ".idev" / "task" / FEATURE / "workflow" / "run.yaml")
        plan = next(s for s in run["steps"] if s["id"] == "plan")
        self.assertEqual(plan["status"], "PASS")
        self.assertEqual(plan["evidence"], "verify/plan.yaml")


class OnlyAGateWithACheckMayAuto(unittest.TestCase):
    def test_a_step_confirm_gate_without_auto_stage_may_not(self) -> None:
        errors: list = []
        spec._check_gate(
            {"id": "g", "kind": "human.gate", "label": "将代写: x", "with": {"auto_tiers": ["P1"]}},
            "steps[0]", errors,
        )
        self.assertTrue(any("auto_tiers" in e for e in errors), errors)

    def test_the_plan_gate_may(self) -> None:
        errors: list = []
        spec._check_gate(
            {"id": "g", "kind": "human.gate",
             "with": {"will_write": ["verify/plan.yaml accepted"], "auto_tiers": ["P1"]}},
            "steps[0]", errors,
        )
        self.assertEqual(errors, [])

    def test_a_step_confirm_gate_with_auto_stage_may(self) -> None:
        errors: list = []
        spec._check_gate(
            {"id": "g", "kind": "human.gate", "label": "将代写: x",
             "with": {"auto_tiers": ["P1", "P2"], "auto_stage": "code"}},
            "steps[0]", errors,
        )
        self.assertEqual(errors, [])

    def test_auto_stage_must_name_a_real_stage(self) -> None:
        errors: list = []
        spec._check_gate(
            {"id": "g", "kind": "human.gate", "label": "将代写: x",
             "with": {"auto_tiers": ["P1"], "auto_stage": "deploy"}},
            "steps[0]", errors,
        )
        self.assertTrue(any("auto_stage" in e for e in errors), errors)

    def test_auto_stage_current_is_the_deliver_next_gate(self) -> None:
        errors: list = []
        spec._check_gate(
            {"id": "g", "kind": "human.gate", "label": "将代写: x",
             "with": {"auto_tiers": ["P1", "P2"], "auto_stage": "current"}},
            "steps[0]", errors,
        )
        self.assertEqual(errors, [])

    def test_the_plan_gate_does_not_redeclare_auto_stage(self) -> None:
        errors: list = []
        spec._check_gate(
            {"id": "g", "kind": "human.gate",
             "with": {"will_write": ["verify/plan.yaml accepted"],
                      "auto_tiers": ["P1"], "auto_stage": "verify-plan"}},
            "steps[0]", errors,
        )
        self.assertTrue(any("already has its check" in e for e in errors), errors)


class StageConfirmAutoGate(unittest.TestCase):
    """A step_confirm gate with auto_stage passes on the stage's own check.

    The deliver-next shape: `auto_stage: current` resolves at record time to
    whatever deliver stage the ticket is on. Same refusal family as the plan
    gate: FAIL / SIGNAL / unanswered earlier signals / tier outside.
    """

    STAGE_LOG = "workflow/gate-code-check.log"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()
        self.ticket = assemble(self.repo)
        # The example ticket sits at req-review; move it to the code stage so
        # `current` resolves to code and check-feature code has all its inputs
        # (the example ticket ships semantic_gate priors in deliver.yaml).
        deliver = self.ticket / "deliver.yaml"
        data = safeyaml.mapping(deliver)
        data["stage"] = "code"
        deliver.write_text(safeyaml.dump(data), encoding="utf-8")
        self.run_path = self.ticket / "workflow" / "run.yaml"
        (self.repo / ".idev" / "workflows").mkdir(parents=True, exist_ok=True)
        # A marked product repo carries its own recipe; without the marker the
        # resolver falls back to the kernel's workflows and cannot see this one.
        (self.repo / ".idev" / "marker.yaml").write_text(
            "schema_version: 1\nmarker: idev\nid: demo\nevolve: false\n", encoding="utf-8",
        )
        (self.repo / ".idev" / "workflows" / "stage-confirm.yaml").write_text(
            "schema_version: 1\nid: stage-confirm\nsummary: x\nparams:\n"
            "  - {name: feature, required: true, from: user}\n"
            "steps:\n"
            "  - id: gate\n    kind: human.gate\n    label: 阶段关\n    with:\n"
            "      will_write: [\"当前 stage 的签收字段\"]\n"
            "      auto_tiers: [P1, P2]\n      auto_stage: current\n",
            encoding="utf-8",
        )
        done = cli(self.repo, "workflow.py", "start", "stage-confirm", "--feature", FEATURE)
        self.assertEqual(done.returncode, 0, said(done))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def auto(self) -> subprocess.CompletedProcess:
        return cli(self.repo, "workflow.py", "record", "gate", "AUTO", "--feature", FEATURE)

    def gate(self) -> dict:
        run = safeyaml.mapping(self.run_path) or {}
        return next(s for s in run["steps"] if s["id"] == "gate")

    def test_the_hint_names_the_resolved_stage(self) -> None:
        out = said(cli(self.repo, "workflow.py", "next", "--feature", FEATURE))
        self.assertIn("record AUTO runs check-feature", out)

    def test_a_clean_stage_passes_and_logs_its_own_check(self) -> None:
        done = self.auto()
        self.assertEqual(done.returncode, 0, said(done))
        gate = self.gate()
        self.assertEqual(gate["status"], "AUTO")
        # `current` resolved to the ticket's stage, and the log path follows it
        self.assertEqual(gate["auto"]["stage"], "code")
        self.assertEqual(gate["evidence"], self.STAGE_LOG)
        log = self.ticket / self.STAGE_LOG
        self.assertTrue(log.is_file())

    def test_ask_does_not_open_a_channel_for_an_auto_gate(self) -> None:
        # The Python lane has no gate channel at all, so any ask is refused;
        # the auto-gate refusal line is the Go lane's contract. What this
        # lane shares is the shape: no channel opens, and record AUTO is the
        # only way this gate closes.
        done = cli(self.repo, "workflow.py", "ask", "gate", "--feature", FEATURE)
        self.assertNotEqual(done.returncode, 0)

    def test_tier_outside_auto_tiers_still_needs_a_person(self) -> None:
        deliver = self.ticket / "deliver.yaml"
        data = safeyaml.mapping(deliver)
        data["risk_tier"] = "P0"
        deliver.write_text(safeyaml.dump(data), encoding="utf-8")
        done = self.auto()
        self.assertEqual(done.returncode, 2, said(done))
        self.assertIn("needs a person", said(done))


if __name__ == "__main__":
    unittest.main(verbosity=1)
