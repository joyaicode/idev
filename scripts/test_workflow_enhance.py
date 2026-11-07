#!/usr/bin/env python3
"""Slots, forward branches, recipe digest, tool names, and audit counts."""
from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import workflow_compose  # noqa: E402
import workflow_spec as spec  # noqa: E402
import read_ledger  # noqa: E402

_wf = importlib.util.spec_from_file_location("workflow", HERE / "workflow.py")
workflow = importlib.util.module_from_spec(_wf)
_wf.loader.exec_module(workflow)


def recipe(name: str, steps: list, params: list | None = None) -> dict:
    data = {"schema_version": 1, "id": name, "summary": "x", "steps": steps}
    if params is not None:
        data["params"] = params
    return data


def param(name: str) -> dict:
    return {"name": name, "required": False, "from": "user"}


class Enhance(unittest.TestCase):
    def test_a_missing_slot_asks_before_any_delegate(self):
        step = {"id": "look", "kind": "route.s4", "slots": ["scope"]}
        lines = workflow._step_lines({"params": {"feature": "demo"}}, step)
        self.assertEqual(lines[-1], "ASK slot scope")
        self.assertFalse(any(line.startswith("DELEGATE") for line in lines))
        blank = workflow._step_lines({"params": {"scope": "  "}}, step)
        self.assertEqual(blank[-1], "ASK slot scope")
        filled = workflow._step_lines({"params": {"scope": "api"}, "feature": "-"}, step)
        self.assertTrue(any(line.startswith("DELEGATE") for line in filled))
        self.assertFalse(any(line.startswith("ASK") for line in filled))

    def test_a_gate_stops_only_when_someone_must_choose(self):
        run = {"feature": "-", "params": {}}
        decision = "\n".join(workflow._step_lines(run, {
            "id": "g", "kind": "human.gate", "label": "push",
            "with": {"decision": True, "will_write": ["git push"]},
        }))
        self.assertIn("DECISION a person chooses", decision)
        self.assertNotIn("GATE pass", decision)
        review = "\n".join(workflow._step_lines(run, {
            "id": "g", "kind": "human.gate", "label": "实现审核",
            "with": {"will_write": ["semantic_gate.code"]},
        }))
        self.assertIn("GATE pass", review)
        self.assertNotIn("DECISION", review)
        errors: list[str] = []
        spec.check_recipe(recipe("bad", [
            {"id": "g", "kind": "human.gate", "label": "x", "with": {"decision": False, "will_write": ["a"]}},
        ]), Path("bad.yaml"), errors)
        self.assertTrue(any("with.decision must be true" in item for item in errors))
        both: list[str] = []
        spec.check_recipe(recipe("both", [
            {"id": "g", "kind": "human.gate", "label": "x", "with": {
                "decision": True, "auto_tiers": ["P1"], "will_write": ["verify/plan.yaml accepted"],
            }},
        ]), Path("both.yaml"), both)
        self.assertTrue(any("cannot declare auto_tiers" in item for item in both))

    def test_a_branch_skips_forward_and_a_failed_branch_does_not_block(self):
        errors: list[str] = []
        spec.check_recipe(
            recipe("demo", [
                {"id": "a", "kind": "route.s4", "branch": {"fail": "a"}},
                {"id": "c", "kind": "route.s4"},
            ]),
            Path("demo.yaml"),
            errors,
        )
        self.assertTrue(any("later step" in item for item in errors))
        grouped: list[str] = []
        spec.check_recipe(
            recipe("demo", [
                {"id": "a", "kind": "route.s4", "group": "wave", "writes": ["a.md"], "branch": {"pass": "c"}},
                {"id": "c", "kind": "route.s4"},
            ]),
            Path("demo.yaml"),
            grouped,
        )
        self.assertTrue(any("cannot branch" in item for item in grouped))
        run = {"status": "running", "steps": [
            {"id": "a", "kind": "route.s4", "status": "FAIL", "branch": {"fail": "c"}},
            {"id": "b", "kind": "route.s4", "status": "pending"},
            {"id": "c", "kind": "route.s4", "status": "pending"},
        ]}
        self.assertEqual(workflow._take_branch(run, run["steps"][0], "FAIL"), "c")
        self.assertEqual(run["steps"][1]["status"], "SKIPPED")
        self.assertEqual(run["steps"][1]["note"], "branch a -> c")
        self.assertEqual(run["steps"][0]["branch_to"], "c")
        self.assertEqual(workflow.current_step(run)["id"], "c")
        passed = {"steps": [
            {"id": "a", "kind": "route.s4", "status": "PASS", "branch": {"pass": "c"}},
            {"id": "b", "kind": "route.s4", "status": "pending"},
            {"id": "c", "kind": "route.s4", "status": "pending"},
        ]}
        self.assertEqual(workflow._take_branch(passed, passed["steps"][0], "PASS"), "c")
        self.assertNotIn("branch_to", passed["steps"][0])
        self.assertEqual(passed["steps"][1]["status"], "SKIPPED")
        self.assertEqual(workflow.current_step(passed)["id"], "c")

    def test_an_unknown_slot_is_refused_when_the_recipe_declares_params(self):
        errors: list[str] = []
        spec.check_recipe(
            recipe("demo", [{"id": "a", "kind": "route.s4", "slots": ["other"]}], [param("scope")]),
            Path("demo.yaml"),
            errors,
        )
        self.assertTrue(any("not a recipe param" in item for item in errors))

    def test_start_stores_the_recipe_digest(self):
        raw = b"schema: demo\n"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "demo.yaml"
            path.write_bytes(raw)
            self.assertEqual(workflow.recipe_digest(path), hashlib.sha256(raw).hexdigest()[:16])

    def test_a_tool_prints_its_declared_names(self):
        inputs, outputs = workflow_compose.tool_contract("stage-gate")
        self.assertEqual(inputs, ["feature"])
        self.assertEqual(outputs, [])
        lines = workflow._tool_lines({"kind": "tool.step", "tool": "stage-gate"})
        self.assertIn("TOOL python3 scripts/stage-gate.py", lines)
        self.assertIn("LIMIT 不写签字，不改票。", lines)
        self.assertEqual(lines[0], "TOOL python3 scripts/stage-gate.py")
        self.assertIn("IN feature", lines)
        missing: list[str] = []
        spec.check_catalog({
            "schema_version": 1,
            "tools": [{"id": "x", "summary": "s", "command": "c"}],
        }, Path("tools.yaml"), missing)
        self.assertTrue(any("limit is required" in item for item in missing))
        errors: list[str] = []
        spec.check_catalog({
            "schema_version": 1,
            "tools": [{"id": "x", "summary": "s", "command": "c", "inputs": "feature"}],
        }, Path("tools.yaml"), errors)
        self.assertTrue(any("inputs" in item for item in errors))

    def test_a_tool_input_is_asked_like_a_slot(self):
        step = {"id": "gate", "kind": "tool.step", "tool": "stage-gate"}
        lines = workflow._step_lines({"params": {}}, step)
        self.assertEqual(lines[-1], "ASK slot feature")
        self.assertFalse(any(line.startswith("TOOL") for line in lines))
        filled = workflow._step_lines({"params": {"feature": "demo"}, "feature": "-"}, step)
        self.assertTrue(any(line.startswith("TOOL") for line in filled))
        self.assertIn("IN feature", filled)

    def test_a_branch_cannot_land_inside_a_group_or_on_a_settled_step(self):
        errors: list[str] = []
        spec.check_recipe(recipe("demo", [
            {"id": "a", "kind": "route.s4", "branch": {"pass": "c"}},
            {"id": "b", "kind": "route.s4", "group": "wave", "writes": ["b.md"]},
            {"id": "c", "kind": "route.s4", "group": "wave", "writes": ["c.md"]},
        ]), Path("demo.yaml"), errors)
        self.assertTrue(any("first step of group" in item for item in errors))
        run = {"steps": [
            {"id": "a", "status": "PASS", "branch": {"pass": "c"}},
            {"id": "b", "status": "pending"},
            {"id": "c", "status": "PASS"},
        ]}
        with self.assertRaises(workflow.Blocked):
            workflow._take_branch(run, run["steps"][0], "PASS")
        self.assertEqual(run["steps"][1]["status"], "pending")

    def test_param_fills_an_open_slot_and_digest_only_compares(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            recipe_path = folder / "demo.yaml"
            recipe_path.write_text("id: demo\n", encoding="utf-8")
            digest = workflow.recipe_digest(recipe_path)
            run = {
                "status": "running",
                "recipe": str(recipe_path),
                "recipe_digest": digest,
                "params": {},
                "steps": [{"id": "look", "kind": "route.s4", "slots": ["scope"], "status": "pending"}],
            }
            lines = workflow.next_line(run)
            self.assertEqual(lines[0], "DIGEST match %s" % digest)
            self.assertEqual(lines[-1], "PROGRESS closed=0/1 open=look")
            recipe_path.write_text("id: demo\nchanged: true\n", encoding="utf-8")
            self.assertTrue(workflow.digest_line(run).startswith("DIGEST drift "))
            body = (
                "schema_version: 1\nworkflow_id: demo\nfeature: demo\nstatus: running\n"
                "recipe: %s\nrecipe_digest: %s\nparams: {}\nsteps:\n"
                "  - id: look\n    kind: route.s4\n    slots: [scope]\n    status: pending\n"
                % (recipe_path, digest)
            )
            run_path = folder / "run.yaml"
            run_path.write_text(body, encoding="utf-8")
            self.assertEqual(workflow.main(["param", "scope=api", "--run", str(run_path)]), 0)
            text = run_path.read_text(encoding="utf-8")
            self.assertIn("scope: api", text)
            self.assertEqual(workflow.main(["param", "other=no", "--run", str(run_path)]), 2)
            self.assertNotIn("other:", run_path.read_text(encoding="utf-8"))

    def test_progress_counts_closed_steps_and_names_open_ids(self):
        skipped = {
            "status": "running",
            "steps": [
                {"id": "skip", "kind": "route.s4", "status": "SKIPPED"},
                {"id": "left", "kind": "route.s4", "status": "pending"},
            ],
        }
        self.assertEqual(workflow.next_line(skipped)[-1], "PROGRESS closed=1/2 open=left")
        branched = {
            "status": "running",
            "steps": [
                {"id": "bad", "kind": "route.s4", "status": "FAIL", "branch_to": "left"},
                {"id": "left", "kind": "route.s4", "status": "pending"},
            ],
        }
        self.assertEqual(workflow.next_line(branched)[-1], "PROGRESS closed=1/2 open=left")
        parallel = {
            "status": "running",
            "steps": [
                {"id": "a", "kind": "route.s4", "status": "pending", "group": "g"},
                {"id": "b", "kind": "route.s4", "status": "pending", "group": "g"},
            ],
        }
        self.assertEqual(workflow.next_line(parallel)[-1], "PROGRESS closed=0/2 open=a,b")
        done = {
            "status": "done",
            "steps": [
                {"id": "a", "status": "PASS"},
                {"id": "b", "status": "PASS"},
            ],
        }
        self.assertEqual(workflow.next_line(done)[-1], "PROGRESS closed=2/2")

    def test_brief_prints_progress_before_end(self):
        import io
        from contextlib import redirect_stdout
        run = {
            "status": "running",
            "feature": "demo",
            "steps": [{"id": "look", "kind": "route.s4", "status": "pending"}],
        }
        brief = {
            "ticket_home": "/tmp/t",
            "repo": "/tmp/r",
            "stage": "s",
            "risk_tier": "P1",
            "label": "",
            "with": {},
            "must_read": "/tmp/m",
            "idev_root": "/tmp/i",
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            workflow.print_brief(run, run["steps"][0], "idev-ops", 1, brief)
        text = buf.getvalue()
        self.assertIn("请求头: agent=idev-ops sha256=", text)
        self.assertIn("tools=Read, Grep, Glob, Bash, Write", text)
        self.assertIn("PROGRESS closed=0/1 open=look\nEND BRIEF", text)
        brief["prior_failure"] = "上次 STATUS=FAIL"
        brief["context_blocks"] = [{"span": "src/a.go:1:1", "sha256": "abc", "text": "1|package a"}]
        brief["context_stale"] = [{"span": "src/b.go:1:1", "reason": "文件已变"}]
        buf = io.StringIO()
        with redirect_stdout(buf):
            workflow.print_brief(run, run["steps"][0], "idev-ops", 2, brief)
        text = buf.getvalue()
        self.assertIn("重放: 本步换了新的上下文", text)
        self.assertIn("上下文: src/a.go:1:1 sha256=abc\n1|package a", text)
        self.assertIn("上下文失效: src/b.go:1:1 文件已变，这一段不算上下文", text)

    def test_print_uses_the_frozen_header_and_names_a_change(self):
        import io
        from contextlib import redirect_stdout
        run = {
            "status": "running",
            "feature": "demo",
            "steps": [{"id": "look", "kind": "route.s4", "status": "pending"}],
        }
        brief = {
            "ticket_home": "/tmp/t",
            "repo": "/tmp/r",
            "stage": "s",
            "risk_tier": "P1",
            "label": "",
            "with": {},
            "must_read": "/tmp/m",
            "idev_root": "/tmp/i",
            "request_header": {"agent": "idev-ops", "sha256": "frozen", "tools": "Read"},
            "header_changed": {"from": "oldsha", "to": "frozen"},
            "progress": "PROGRESS closed=9/9 open=kept",
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            workflow.print_brief(run, run["steps"][0], "idev-ops", 2, brief)
        text = buf.getvalue()
        self.assertIn("请求头: agent=idev-ops sha256=frozen tools=Read", text)
        self.assertIn("请求头变更: oldsha → frozen。执行者定义和上一回不是同一份。", text)
        self.assertIn("PROGRESS closed=9/9 open=kept\nEND BRIEF", text)

    def test_compose_stores_the_header_and_notices_a_change(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            run_path = repo / "workflow" / "run.yaml"
            run_path.parent.mkdir()
            run_path.write_text("status: running\n", encoding="utf-8")
            run = {"feature": "demo", "steps": [{"id": "look", "kind": "route.s4", "status": "pending"}]}
            previous = {
                "agent": "idev-ops",
                "brief": {"request_header": {"agent": "idev-ops", "sha256": "oldsha", "tools": "Read"}},
            }
            brief = workflow.compose_brief(
                run_path, run, run["steps"][0], repo, previous, agent="idev-ops",
            )
            live = workflow.step_packet.header("idev-ops")
            self.assertEqual(brief["request_header"]["sha256"], live["sha256"])
            self.assertEqual(brief["request_header"]["tools"], live["tools"])
            self.assertEqual(brief["header_changed"], {"from": "oldsha", "to": live["sha256"]})
            self.assertEqual(brief["progress"], "PROGRESS closed=0/1 open=look")
            other = workflow.compose_brief(
                run_path, run, run["steps"][0], repo,
                {"agent": "idev-coder", "brief": {"request_header": {"sha256": "oldsha"}}},
                agent="idev-ops",
            )
            self.assertNotIn("header_changed", other)

    def test_retry_brief_replays_a_span_and_skips_the_page_excerpt(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            source = repo / "src" / "a.go"
            source.parent.mkdir()
            source.write_text("package a\nfunc F() {}\n", encoding="utf-8")
            run_path = repo / "workflow" / "run.yaml"
            run_path.parent.mkdir()
            run_path.write_text("status: running\n", encoding="utf-8")
            read_ledger.note(
                repo, "look", "src/a.go:1:2",
                hashlib.sha256(source.read_bytes()).hexdigest(),
            )
            run = {"feature": "demo", "steps": [{"id": "look", "kind": "route.s4", "status": "pending"}]}
            brief = workflow.compose_brief(
                run_path, run, run["steps"][0], repo, prior_failure="上次 STATUS=FAIL",
            )
            self.assertEqual(brief["context_blocks"][0]["span"], "src/a.go:1:2")
            self.assertIn("func F", brief["context_blocks"][0]["text"])
            self.assertNotIn("context_refused", brief)

    def test_loop_status_is_shown_and_does_not_replace_the_step(self):
        step = {"id": "look", "kind": "route.s4", "react": {"candidates": ["stage-gate"]}}
        self.assertEqual(workflow._loop_line({"feature": "enhance-probe-absent"}, step), "LOOP absent")
        path = workflow.sink_dir("react") / "enhance-probe-open--look.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("status: open\nmax_hops: 4\nhops:\n- {n: 1}\n- {n: 2}\n", encoding="utf-8")
        try:
            self.assertEqual(workflow._loop_line({"feature": "enhance-probe-open"}, step), "LOOP open hops=2/4")
            lines = workflow._step_lines({"feature": "enhance-probe-open", "params": {}}, step)
            self.assertIn("LOOP open hops=2/4", lines)
            self.assertTrue(any(line.startswith("DELEGATE") for line in lines))
        finally:
            if path.is_file():
                path.unlink()

    def test_audit_counts_tool_hops_and_open_failures_outside_hard(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            traces = root / "traces"
            inbox = root / "inbox"
            traces.mkdir()
            inbox.mkdir()
            (traces / "a.yaml").write_text(
                "feature: demo\ncalls:\n  - kind: tool\n    from: react:look\n    to: tool:stage-gate\n",
                encoding="utf-8",
            )
            (inbox / "open.yaml").write_text(
                "status: pending\ntags:\n  - react-tool-fail\n",
                encoding="utf-8",
            )
            (inbox / "closed.yaml").write_text(
                "status: consumed\ntags:\n  - react-exhausted\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [sys.executable, str(HERE / "audit_traces_lib.py"), str(traces), "5"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("| 写了工具跳 | 1 |", proc.stdout)
            self.assertIn("未消费关节失败=1", proc.stdout)
            self.assertIn("HARD_COUNT=0", proc.stdout)


if __name__ == "__main__":
    unittest.main()
