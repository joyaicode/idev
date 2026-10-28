#!/usr/bin/env python3
"""A delegation record carries its own subagent's time and tool calls, not a neighbour's.

    python3 scripts/test_telemetry.py
"""
from __future__ import annotations

import json
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

REVIEW = (
    "STATUS: PASS\nEVIDENCE: review.md\nFACTS: codegraph 查到 src/app.py:main 的调用方\n"
    "DOC_DRIFT: 无\nASSUMED: 无\n"
)
BRIEF = {
    "ticket_home": ".idev/task/feat", "repo": ".", "stage": "code",
    "must_read": "conventions/coding.md", "idev_root": str(KERNEL),
}


class Telemetry(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.repo = base / "repo"
        (self.repo / ".git").mkdir(parents=True)
        workflow = self.repo / ".idev" / "task" / "feat" / "workflow"
        workflow.mkdir(parents=True)
        (workflow / "run.yaml").write_text("run_id: R1\nstatus: running\nsteps: []\n", encoding="utf-8")
        self.elsewhere = base / "other"
        self.elsewhere.mkdir()
        self.data = base / "data"
        self.env = dict(os.environ, IDEV_DATA=str(self.data), IDEV_BIN="off")
        self.env.pop("IDEV_ENGINE", None)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def stop(self, agent: str, duration_ms: int, tools: int, root: Path | None = None) -> dict:
        payload = {
            "subagent_type": agent, "status": "completed", "task": "review the diff",
            "description": "review", "summary": "STATUS: PASS", "duration_ms": duration_ms,
            "message_count": 9, "tool_call_count": tools, "loop_count": 0, "modified_files": [],
            "agent_transcript_path": None, "conversation_id": "conv-1", "generation_id": "gen-1",
            "model": "m", "hook_event_name": "subagentStop", "workspace_roots": [str(root or self.repo)],
        }
        done = subprocess.run(
            [sys.executable, str(KERNEL / "hooks" / "subagent_stop.py"), "--client", "cursor"],
            input=json.dumps(payload), capture_output=True, text=True, env=self.env, timeout=30,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        return self.rows()[-1]

    def rows(self) -> list[dict]:
        path = self.data / "subagent-stops.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def write(self, attempt: int = 1, **extra) -> tuple[dict, str]:
        brief = dict(BRIEF, prior_failure="the first report missed a file") if attempt > 1 else BRIEF
        record = {"step": "report", "kind": "review.report", "agent": "idev-reviewer", "attempt": attempt,
                  "brief": brief, "report": {"status": "PASS", "raw": REVIEW}, **extra}
        done = subprocess.run(
            [sys.executable, str(HERE / "delegation.py"), "--repo", str(self.repo), "write", "--feature", "feat"],
            input=json.dumps(record, ensure_ascii=False), capture_output=True, text=True, env=self.env, timeout=60,
        )
        self.assertIn(done.returncode, (0, 1), done.stdout + done.stderr)
        found = sorted(self.repo.glob(f".idev/task/feat/workflow/delegations/**/report-{attempt}.yaml"))
        self.assertEqual(len(found), 1, done.stdout + done.stderr)
        return safeyaml.mapping(found[0]), done.stdout

    def test_the_hook_keeps_what_cursor_sends(self) -> None:
        row = self.stop("idev-reviewer", 61000, 12)
        self.assertEqual((row["duration_ms"], row["tool_call_count"], row["message_count"]), (61000, 12, 9))
        self.assertEqual(row["workspace_roots"], [str(self.repo)])
        self.assertEqual((row["conversation_id"], row["generation_id"], row["loop_count"]), ("conv-1", "gen-1", 0))
        self.assertRegex(row["id"], r"^[0-9a-f]{32}$")

    def test_a_record_takes_its_own_agents_stop(self) -> None:
        mine = self.stop("idev-reviewer", 61000, 12)
        self.stop("idev-coder", 5000, 3)
        record, _ = self.write()
        self.assertEqual((record["duration_ms"], record["tool_call_count"]), (61000, 12))
        self.assertEqual(record["stop_id"], mine["id"])

    def test_a_stop_is_used_once(self) -> None:
        self.stop("idev-reviewer", 61000, 12)
        self.write()
        record, out = self.write(attempt=2)
        self.assertNotIn("tool_call_count", record)
        self.assertIn("HINT no subagentStop row of idev-reviewer for this delegation", out)

    def test_without_the_hook_the_record_says_how_to_get_telemetry(self) -> None:
        record, out = self.write()
        self.assertNotIn("duration_ms", record)
        self.assertIn("install-idev-hooks.sh", out)

    def test_another_workspace_or_an_earlier_stop_is_not_this_delegation(self) -> None:
        self.stop("idev-reviewer", 61000, 12, root=self.elsewhere)
        record, _ = self.write()
        self.assertNotIn("duration_ms", record)
        self.stop("idev-reviewer", 7000, 4)
        record, _ = self.write(attempt=2, started_at="2099-01-01T00:00:00+08:00")
        self.assertNotIn("duration_ms", record)

    def test_eval_reports_how_many_records_carry_telemetry(self) -> None:
        self.stop("idev-reviewer", 61000, 12)
        self.write()
        self.write(attempt=2)
        done = subprocess.run(
            [sys.executable, str(HERE / "delegation.py"), "--repo", str(self.repo), "eval", "--feature", "feat"],
            capture_output=True, text=True, env=self.env, timeout=60,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("- telemetry: 1/2", done.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
