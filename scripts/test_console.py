#!/usr/bin/env python3
"""Console board, thread, and page: agents, durations, skills, hypotheses."""
from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

import console
import safeyaml


TRACE = """schema_version: 2
at: "2026-10-24T19:00:00+08:00"
feature: feat
intent: "看自测为什么红"
invoke:
  trigger: "看自测"
  matched: "S8"
  how: explicit
  skills:
    - name: idev
      why: "用户要看自测"
route:
  module: verify
  scenario: S8
  stage: test
  risk_tier: P1
  why: "自测还是红的"
calls:
  - kind: skill
    name: idev
    from: user
    to: skill:idev
    thinking: "先看技能入口"
    duration_s: 12
  - kind: module
    name: verify/SKILL.md
    from: conductor
    to: module:verify
thinking:
  summary: "自测是红的，先看 verify。"
opened:
  - verify/SKILL.md
"""


def _ticket(root: Path) -> Path:
    task = root / ".idev" / "task" / "feat"
    (task / "workflow" / "delegations").mkdir(parents=True)
    (task / "deliver.yaml").write_text("stage: test\n", encoding="utf-8")
    (task / "workflow" / "run.yaml").write_text(safeyaml.dump({
        "workflow_id": "lite-change",
        "status": "active",
        "steps": [
            {"id": "classify", "kind": "ops.classify", "status": "pending"},
            {"id": "gate", "kind": "human.gate", "status": "PASS"},
        ],
    }), encoding="utf-8")
    (task / "workflow" / "delegations" / "classify-1.yaml").write_text(safeyaml.dump({
        "feature": "feat",
        "step": "classify",
        "kind": "ops.classify",
        "agent": "idev-ops",
        "attempt": 1,
        "duration_s": 185,
        "report": {"status": "PASS", "evidence": "notes.md"},
    }), encoding="utf-8")
    (task / "workflow" / "delegations" / "edit-1.yaml").write_text(safeyaml.dump({
        "feature": "feat",
        "step": "edit",
        "kind": "deliver.code_pass",
        "agent": "idev-coder",
        "attempt": 1,
        "report": {"status": "PASS", "evidence": "diff.txt"},
    }), encoding="utf-8")
    (task / "hypotheses.yaml").write_text(safeyaml.dump({
        "schema_version": 1,
        "feature": "feat",
        "items": [{
            "id": "H1",
            "claim": "连接池把超时当成成功",
            "status": "open",
            "at": "2026-10-24T19:00:00+08:00",
        }],
    }), encoding="utf-8")
    return task


class Board(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.traces = self.root / "traces"
        self.traces.mkdir()
        self.folder = self.root / "console"
        self.folder.mkdir()
        _ticket(self.root)
        (self.traces / "20261024-001.yaml").write_text(TRACE, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_board_shows_agent_duration_skill_and_hypothesis(self) -> None:
        console.live_add(self.folder, feature="feat", step="classify", agent="idev-ops", kind="ops.classify")
        data = console.board(trace_dir=self.traces, repo=self.root, console_dir=self.folder)
        self.assertEqual(data["traces"][0]["skills"][0]["name"], "idev")
        skill = next(item for item in data["traces"][0]["calls"] if item["kind"] == "skill")
        module = next(item for item in data["traces"][0]["calls"] if item["kind"] == "module")
        self.assertEqual(skill["duration_s"], 12)
        self.assertIsNone(module["duration_s"])
        pack = data["features"]["feat"]
        ops = next(row for row in pack["delegations"] if row["agent"] == "idev-ops")
        coder = next(row for row in pack["delegations"] if row["agent"] == "idev-coder")
        self.assertEqual(ops["duration_s"], 185)
        self.assertEqual(ops["evidence"], "notes.md")
        self.assertIsNone(coder["duration_s"])
        self.assertEqual(pack["ops_duration_s"], 185)
        self.assertEqual(pack["hypotheses"][0]["claim"], "连接池把超时当成成功")
        steps = {step["id"]: step for step in pack["run"]["steps"]}
        self.assertTrue(steps["classify"]["running"])
        self.assertFalse(steps["gate"]["running"])
        self.assertEqual(data["live"][0]["agent"], "idev-ops")
        self.assertIsNotNone(data["live"][0]["elapsed_s"])
        self.assertGreaterEqual(data["live"][0]["elapsed_s"], 0)
        running = data["current"]["running"][0]
        self.assertEqual(running["agent"], "idev-ops")
        self.assertEqual(running["step"], "classify")
        self.assertEqual(running["stage"], "test")
        self.assertEqual(running["stage_label"], "测试")
        self.assertEqual(running["intent"], "看自测为什么红")
        self.assertEqual(data["current"]["focus"]["feature"], "feat")
        meters = data["meters"]
        self.assertEqual(meters["traces"], 1)
        self.assertEqual(meters["live"], 1)
        self.assertEqual(next(row["n"] for row in meters["scenarios"] if row["id"] == "S8"), 1)
        self.assertEqual(next(row["n"] for row in meters["scenarios"] if row["id"] == "S1"), 0)
        observed = {row["id"]: row["n"] for row in meters["observation"]}
        self.assertEqual(observed, {"skill": 1, "delegate": 0, "model": 0, "hop": 1})
        ops = next(row for row in meters["agents"] if row["agent"] == "idev-ops")
        coder = next(row for row in meters["agents"] if row["agent"] == "idev-coder")
        self.assertEqual(ops["duration_s"], 185)
        self.assertEqual(ops["untimed"], 0)
        self.assertIsNone(coder["duration_s"])
        self.assertEqual(coder["untimed"], 1)
        self.assertEqual(next(row["n"] for row in meters["outcomes"] if row["id"] == "PASS"), 2)
        self.assertEqual(meters["retries"], 0)
        self.assertEqual(meters["delegations"], 2)
        self.assertEqual(meters["skills"], [{"name": "idev", "n": 1}])
        self.assertEqual(next(row["n"] for row in meters["hypotheses"] if row["id"] == "open"), 1)

    def test_current_ticket_keeps_its_stage_when_nothing_is_running(self) -> None:
        data = console.board(trace_dir=self.traces, repo=self.root, console_dir=self.folder)
        self.assertEqual(data["current"]["running"], [])
        focus = data["current"]["focus"]
        self.assertEqual(focus["feature"], "feat")
        self.assertEqual(focus["stage"], "test")
        self.assertEqual(focus["stage_label"], "测试")
        self.assertEqual(focus["intent"], "看自测为什么红")
        self.assertEqual(focus["step"], "classify")

    def test_running_workflow_outranks_a_newer_trace(self) -> None:
        review = self.root / ".idev" / "task" / "review"
        (review / "workflow").mkdir(parents=True)
        (review / "workflow" / "run.yaml").write_text(safeyaml.dump({
            "workflow_id": "code-review",
            "feature": "review",
            "status": "running",
            "steps": [
                {"id": "report", "kind": "review.report", "status": "PASS"},
                {
                    "id": "plan",
                    "kind": "verify.plan",
                    "label": "为已签收项起草 selftest plan",
                    "delegated": {"agent": "idev-verifier", "at": "2026-10-24T19:55:53+08:00"},
                    "with": {"mode": "selftest"},
                    "lease": {
                        "id": "lease-1",
                        "token": "secret-token",
                        "fencing": 8,
                        "paths": ["docs/task/review/verify/plan.yaml"],
                    },
                },
            ],
        }), encoding="utf-8")
        newer = TRACE.replace('feature: feat', 'feature: other').replace("看自测为什么红", "另一张票")
        (self.traces / "20261024-002.yaml").write_text(newer, encoding="utf-8")
        data = console.board(trace_dir=self.traces, repo=self.root, console_dir=self.folder)
        running = data["current"]["running"][0]
        self.assertEqual(running["feature"], "review")
        self.assertEqual(running["agent"], "idev-verifier")
        self.assertEqual(running["step"], "plan")
        self.assertEqual(running["label"], "为已签收项起草 selftest plan")
        self.assertEqual(running["mode"], "selftest")
        self.assertEqual(running["fencing"], 8)
        self.assertEqual(running["paths"], ["docs/task/review/verify/plan.yaml"])
        self.assertNotIn("secret-token", json.dumps(running))
        logs = review / "workflow" / "logs"
        logs.mkdir()
        fresh = logs / "i1.log"
        fresh.write_text("still red\nEXIT:0\n", encoding="utf-8")
        stale = logs / "old.log"
        stale.write_text("EXIT:1\n", encoding="utf-8")
        os_utime = __import__("os").utime
        os_utime(stale, (1_700_000_000, 1_700_000_000))
        secret = logs / "scan.log"
        secret.write_text("token=secret-token\n", encoding="utf-8")
        data = console.board(trace_dir=self.traces, repo=self.root, console_dir=self.folder)
        running = data["current"]["running"][0]
        names = [item["name"] for item in running["activity"]]
        self.assertIn("i1.log", names)
        self.assertNotIn("old.log", names)
        self.assertEqual(next(item["tail"] for item in running["activity"] if item["name"] == "i1.log"), "EXIT:0")
        self.assertEqual(next(item["tail"] for item in running["activity"] if item["name"] == "scan.log"), "(已略过)")
        self.assertNotIn("secret-token", json.dumps(running))
        self.assertIsNotNone(running["elapsed_s"])
        self.assertGreater(running["elapsed_s"], 0)
        self.assertEqual(data["current"]["focus"]["feature"], "review")
        self.assertEqual(data["traces"][0]["feature"], "other")

    def test_live_clear_removes_one_shard(self) -> None:
        console.live_add(self.folder, feature="feat", step="run", agent="idev-verifier", shard="a")
        console.live_add(self.folder, feature="feat", step="run", agent="idev-verifier", shard="b")
        console.live_clear(self.folder, feature="feat", step="run", shard="a")
        left = console.read_live(self.folder)
        self.assertEqual([row["shard"] for row in left], ["b"])

    def test_thread_post_pending_reply_clears_unread(self) -> None:
        console.post(self.folder, "看一下自测为什么红")
        self.assertEqual(len(console.unread(self.folder)), 1)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(console.main(["pending", "--console-dir", str(self.folder)]), 0)
        self.assertIn("看一下自测为什么红", buf.getvalue())
        self.assertIn("pending: 1", buf.getvalue())
        console.reply(self.folder, "下一轮看 verify.run")
        self.assertEqual(console.unread(self.folder), [])
        roles = [item["role"] for item in console.read_thread(self.folder)]
        self.assertEqual(roles, ["user", "conductor"])
        self.assertEqual(console.read_thread(self.folder)[0]["status"], "read")

    def test_page_names_the_panels(self) -> None:
        for word in ("各轮", "时间线", "详情", "任务与对话", "技能调起", "系统架构", "当前任务", "阶段", "正在工作", "写入范围", "刚写下", "sealed", "计量", "定向调整", "改关口", "补观测", "质疑基线", "不是分数"):
            self.assertIn(word, console.PAGE)


class Http(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        traces = self.root / "traces"
        traces.mkdir()
        (traces / "20261024-001.yaml").write_text(TRACE, encoding="utf-8")
        _ticket(self.root)
        self.folder = self.root / "console"
        self.httpd = console.make_server(traces, self.root, self.folder, 0)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def test_page_and_post(self) -> None:
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")
        page = urllib.request.urlopen(self.base + "/", timeout=2).read().decode("utf-8")
        self.assertIn("时间线", page)
        body = json.dumps({"text": "从页面下达任务"}).encode("utf-8")
        req = urllib.request.Request(
            self.base + "/api/thread",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        sent = json.loads(urllib.request.urlopen(req, timeout=2).read().decode("utf-8"))
        self.assertTrue(sent["ok"])
        board = json.loads(urllib.request.urlopen(self.base + "/api/board", timeout=2).read().decode("utf-8"))
        self.assertEqual(board["thread"][0]["text"], "从页面下达任务")
        self.assertEqual(board["thread"][0]["status"], "unread")
        self.assertEqual(board["features"]["feat"]["hypotheses"][0]["claim"], "连接池把超时当成成功")


if __name__ == "__main__":
    unittest.main()
