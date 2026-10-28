#!/usr/bin/env python3
"""Red/green fixtures for idev client hooks and the quote check they feed.

    python3 scripts/test_hooks.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
IDEV = HERE.parent
HOOKS = IDEV / "hooks"
sys.path.insert(0, str(HERE / "lib"))

import testenv  # noqa: E402

testenv.pin()

_spec = importlib.util.spec_from_file_location("idev_hooks_lib", HOOKS / "lib.py")
HOOKS_LIB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(HOOKS_LIB)


def pinned_idev() -> Path | None:
    exe = testenv.go_binary()
    return Path(exe) if exe else None


def run_hook(script: str, payload: dict, env: dict | None = None, client: str = "cursor") -> subprocess.CompletedProcess:
    merged = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(HOOKS / script), "--client", client],
        input=json.dumps(payload),
        capture_output=True, text=True, env=merged, cwd=IDEV,
    )


class PromptLog(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.env = {"IDEV_DATA": str(self.data)}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_appends_sha256_and_text(self) -> None:
        done = run_hook("prompt_log.py", {"prompt": "确认，按提案执行"}, self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        rows = (self.data / "prompts.log").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(rows), 1)
        row = json.loads(rows[0])
        self.assertEqual(row["text"], "确认，按提案执行")
        self.assertEqual(row["sha256"], __import__("hashlib").sha256("确认，按提案执行".encode()).hexdigest())
        self.assertEqual(json.loads(done.stdout)["permission"], "allow")


class PreTool(unittest.TestCase):
    def test_allows_ordinary_write(self) -> None:
        done = run_hook("pre_tool.py", {
            "tool_name": "Write",
            "tool_input": {"path": "src/app.py", "contents": "print(1)\n"},
        })
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["permission"], "allow")

    def test_allows_delivery_field_write(self) -> None:
        done = run_hook("pre_tool.py", {
            "tool_name": "Write",
            "tool_input": {
                "path": "docs/task/demo/baseline.yaml",
                "contents": "sealed: true\n",
            },
        })
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(json.loads(done.stdout)["permission"], "allow")

    def test_denies_reopen_written_by_hand(self) -> None:
        done = run_hook("pre_tool.py", {
            "tool_name": "Write",
            "tool_input": {
                "path": "docs/task/demo/baseline.yaml",
                "contents": "reopen_baseline: true\n",
            },
        })
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertEqual(json.loads(done.stdout)["permission"], "deny")
        self.assertIn("reopen", done.stdout)

    def test_allows_delivery_fields_in_ticket_and_run_yaml(self) -> None:
        for path, key, field in (
            ("/repo/.idev/task/demo/deliver.yaml", "contents", "aligned: true\n"),
            ("docs/task/demo/workflow/run.yaml", "new_string", "  by: wangwei794\n"),
            (".idev/workflow-runs/r1/run.yaml", "content", "signoff:\n  quote: ok\n"),
            ("/kernel/state/workflow-runs/r1/run.yml", "new_string", "accepted: true\n"),
            ("C:\\repo\\docs\\task\\demo\\baseline.yaml", "contents", "sealed: true\n"),
        ):
            for path_key in ("path", "file_path"):
                done = run_hook("pre_tool.py", {"tool_name": "Edit", "tool_input": {path_key: path, key: field}})
                self.assertEqual(done.returncode, 0, f"{path} {path_key}: {done.stdout}")
                self.assertEqual(json.loads(done.stdout)["permission"], "allow")

    def test_allows_source_and_docs_that_only_quote_signoff_words(self) -> None:
        # Cursor sends the whole file with an edit, so every old line is in the content.
        go = "func (a app) gate(args []string) {\n\tby := fs.String(\"by\", \"\", \"human handle\")\n}\n"
        self.assertRegex(go, HOOKS_LIB.SIGNOFF_FIELD_RE)
        for path, content in (
            ("/work/idev/cmd/idev/app.go", go),
            ("scripts/lib/staffing.py", "def assign(\n    by: str,\n) -> None:\n    pass\n"),
            ("test/lease-channel.sh", "cat >run.yaml <<'EOF'\n  by: tester\nEOF\n"),
            ("references/chat-confirm-signoff.md", "```yaml\nsealed: true\n```\n"),
            ("docs/task/demo/grill.md", "accepted: the person said yes\n"),
        ):
            self.assertRegex(content, HOOKS_LIB.SIGNOFF_FIELD_RE, path)
            done = run_hook("pre_tool.py", {
                "tool_name": "StrReplace",
                "tool_input": {"path": path, "content": content, "new_string": "x"},
            })
            self.assertEqual(done.returncode, 0, f"{path}: {done.stdout}")
            self.assertEqual(json.loads(done.stdout)["permission"], "allow", path)

    def test_a_write_without_a_path_is_still_checked(self) -> None:
        done = run_hook("pre_tool.py", {"tool_name": "Write", "tool_input": {"contents": "reopen_baseline: true\n"}})
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertIn("reopen", done.stdout)

    def test_denies_idev_engine_python(self) -> None:
        done = run_hook("pre_tool.py", {
            "tool_name": "Shell",
            "tool_input": {"command": "IDEV_ENGINE=python python3 scripts/workflow.py next"},
        })
        self.assertEqual(done.returncode, 2)
        self.assertIn("IDEV_ENGINE=python", done.stdout)

    def test_denies_switching_the_binary_off(self) -> None:
        for command in (
            "IDEV_BIN=off python3 scripts/check-feature.py --feature demo --stage req",
            "export IDEV_BIN='none' && python3 scripts/workflow.py next",
            "env FOO=1 IDEV_BIN=0 python3 scripts/workflow.py next",
        ):
            done = run_hook("pre_tool.py", {"tool_name": "Shell", "tool_input": {"command": command}})
            self.assertEqual(done.returncode, 2, command)
            self.assertIn("IDEV_BIN", done.stdout)
        done = run_hook("pre_tool.py", {
            "tool_name": "Shell",
            "tool_input": {"command": "IDEV_BIN=/tmp/idev python3 scripts/workflow.py next"},
        })
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_denies_git_push(self) -> None:
        done = run_hook("pre_tool.py", {
            "command": "git push origin HEAD",
        })
        self.assertEqual(done.returncode, 2)
        self.assertIn("git push", done.stdout)


class InstallHooks(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def install(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(IDEV / "scripts" / "install-idev-hooks.sh"), "--repo", str(self.repo), *extra],
            capture_output=True, text=True,
        )

    def test_install_is_idempotent_and_uninstall_cleans(self) -> None:
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        cursor = json.loads((self.repo / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("beforeSubmitPrompt", cursor["hooks"])
        self.assertIn("preToolUse", cursor["hooks"])
        second = self.install()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        cursor2 = json.loads((self.repo / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
        # one idev entry per event, not duplicated
        self.assertEqual(len(cursor2["hooks"]["beforeSubmitPrompt"]), 1)
        claude = json.loads((self.repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(len(claude["hooks"]["UserPromptSubmit"]), 1)
        removed = self.install("--uninstall")
        self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
        cursor3 = json.loads((self.repo / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
        for event, entries in (cursor3.get("hooks") or {}).items():
            for e in entries:
                self.assertNotIn(f"{IDEV}/hooks/", str(e.get("command", "")), event)

    def test_the_subagent_stop_hook_only_runs_for_idev_agents(self) -> None:
        done = self.install()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        entry = json.loads((self.repo / ".cursor" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["subagentStop"][0]
        for agent in ("idev-coder", "idev-reviewer", "idev-verifier", "idev-deliver", "idev-ops"):
            self.assertRegex(agent, entry["matcher"])
        for other in ("explore", "generalPurpose", "idev-coder-old"):
            self.assertNotRegex(other, entry["matcher"])

    def test_an_entry_from_another_checkout_is_replaced_and_user_hooks_survive(self) -> None:
        cursor_dir = self.repo / ".cursor"
        cursor_dir.mkdir()
        elsewhere = "python3 /opt/kernel-v2/hooks/pre_tool.py --client cursor"
        (cursor_dir / "hooks.json").write_text(json.dumps({"version": 1, "hooks": {
            "preToolUse": [{"command": elsewhere}, {"command": "bash ~/bin/lint-hook.sh"}],
        }}), encoding="utf-8")
        done = self.install()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        commands = [e["command"] for e in json.loads(
            (cursor_dir / "hooks.json").read_text(encoding="utf-8"))["hooks"]["preToolUse"]]
        self.assertNotIn(elsewhere, commands)
        self.assertIn("bash ~/bin/lint-hook.sh", commands)
        self.assertEqual(len([c for c in commands if "/hooks/pre_tool.py" in c]), 1, commands)


class QuoteCheck(unittest.TestCase):
    """A recorded sentence is a note. The prompt log does not gate it."""

    def setUp(self) -> None:
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        sys.path.insert(0, str(HERE / "lib"))
        sys.path.insert(0, str(HERE))
        import workflow  # noqa: E402
        import workflow_spec as spec  # noqa: E402
        self.w = workflow
        self.spec = spec
        spec._PEOPLE_CACHE.clear()
        key = (os.environ.get("IDEV_ROOT", ""), str(Path.cwd()))
        spec._PEOPLE_CACHE[key] = ({"wangwei794"}, "")

    def tearDown(self) -> None:
        self.spec._PEOPLE_CACHE.clear()
        self.tmp.cleanup()

    def test_a_quote_is_stored_when_the_log_check_is_on(self) -> None:
        (self.data / "prompts.log").write_text(
            json.dumps({"text": "hello", "sha256": "x", "at": "t"}) + "\n",
            encoding="utf-8",
        )
        env_was = os.environ.get("IDEV_DATA"), os.environ.get("IDEV_PROMPT_LOG_CHECK")
        os.environ["IDEV_DATA"] = str(self.data)
        os.environ["IDEV_PROMPT_LOG_CHECK"] = "1"
        try:
            got = self.w.chat_signoff("wangwei794", "确认不了")
            self.assertEqual(got["quote"], "确认不了")
        finally:
            for key, val in zip(("IDEV_DATA", "IDEV_PROMPT_LOG_CHECK"), env_was):
                if val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = val

    def test_check_off_does_not_read_the_log(self) -> None:
        # Foreign cwd → auto-check stays off even with a leftover log.
        (self.data / "prompts.log").write_text(
            json.dumps({"text": "unrelated", "sha256": "x", "at": "t", "cwd": "/other/repo"}) + "\n",
            encoding="utf-8",
        )
        os.environ["IDEV_DATA"] = str(self.data)
        os.environ.pop("IDEV_PROMPT_LOG_CHECK", None)
        try:
            got = self.w.chat_signoff("wangwei794", "确认")
            self.assertEqual(got["by"], "wangwei794")
        finally:
            os.environ.pop("IDEV_DATA", None)

    def test_auto_check_when_cwd_has_logged_prompts(self) -> None:
        cwd = str(Path.cwd().resolve())
        (self.data / "prompts.log").write_text(
            json.dumps({"text": "hello only", "sha256": "x", "at": "t", "cwd": cwd}) + "\n",
            encoding="utf-8",
        )
        os.environ["IDEV_DATA"] = str(self.data)
        os.environ.pop("IDEV_PROMPT_LOG_CHECK", None)
        try:
            got = self.w.chat_signoff("wangwei794", "同意吗")
            self.assertEqual(got["quote"], "同意吗")
        finally:
            os.environ.pop("IDEV_DATA", None)


class GoRunYamlWriter(unittest.TestCase):
    """Phase 1 §6: idev owns run.yaml bytes when the binary is present (or forced)."""

    def test_default_writer_follows_binary(self) -> None:
        sys.path.insert(0, str(HERE))
        sys.path.insert(0, str(HERE / "lib"))
        import workflow  # noqa: E402
        idev = pinned_idev()
        was = os.environ.pop("IDEV_RUN_WRITER", None), os.environ.get("IDEV_BIN")
        try:
            os.environ.pop("IDEV_RUN_WRITER", None)
            if idev:
                os.environ["IDEV_BIN"] = str(idev)
                self.assertTrue(workflow.run_writer_go())
            os.environ["IDEV_RUN_WRITER"] = "python"
            self.assertFalse(workflow.run_writer_go())
            os.environ["IDEV_RUN_WRITER"] = "go"
            if idev:
                self.assertTrue(workflow.run_writer_go())
        finally:
            for key, val in zip(("IDEV_RUN_WRITER", "IDEV_BIN"), was):
                if val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = val

    def test_idev_run_record_stamps_a_step(self) -> None:
        idev = pinned_idev()
        if idev is None:
            self.skipTest("no idev binary for this run: the Go toolchain is missing")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.yaml"
            path.write_text("steps:\n  - {id: plan}\n", encoding="utf-8")
            done = subprocess.run(
                [str(idev), "run", "record", "--file", str(path),
                 "--step", "plan", "--status", "PASS", "--evidence", "verify/plan.yaml"],
                capture_output=True, text=True,
            )
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            body = path.read_text(encoding="utf-8")
            self.assertIn("status: PASS", body)
            self.assertIn("evidence: verify/plan.yaml", body)

    def test_workflow_record_via_go_writer(self) -> None:
        idev = pinned_idev()
        if idev is None:
            self.skipTest("no idev binary for this run: the Go toolchain is missing")
        sys.path.insert(0, str(HERE))
        sys.path.insert(0, str(HERE / "lib"))
        import workflow  # noqa: E402
        import safeyaml  # noqa: E402
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.yaml"
            path.write_text(
                "schema_version: 1\nrun_id: 01TESTGOWRITE00000000000000\n"
                "workflow_id: x\nfeature: demo\nstatus: running\n"
                "steps:\n  - {id: plan, kind: verify.plan}\n",
                encoding="utf-8",
            )
            expect = __import__("hashlib").sha256(path.read_bytes()).hexdigest()

            def bump(data: dict) -> dict:
                data["steps"][0]["status"] = "PASS"
                data["steps"][0]["evidence"] = "verify/plan.yaml"
                return data

            env_was = os.environ.get("IDEV_RUN_WRITER"), os.environ.get("IDEV_BIN")
            os.environ["IDEV_RUN_WRITER"] = "go"
            os.environ["IDEV_BIN"] = str(idev)
            try:
                workflow.save_run(path, bump)
            finally:
                for key, val in zip(("IDEV_RUN_WRITER", "IDEV_BIN"), env_was):
                    if val is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = val
            body = path.read_text(encoding="utf-8")
            self.assertIn("status: PASS", body)
            self.assertNotEqual(
                __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
                expect,
            )
            # stale expect is refused
            stale = subprocess.run(
                [str(idev), "run", "write", "--file", str(path), "--expect-sha256", "00"],
                input=b"status: broken\n", capture_output=True,
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn(b"stale", stale.stderr.lower() + stale.stdout.lower())


class SubagentStopAndTrace(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IDEV_DATA": self.tmp.name}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_subagent_stop_appends(self) -> None:
        done = run_hook("subagent_stop.py", {
            "status": "completed",
            "modified_files": ["src/a.py"],
            "duration_ms": 12,
            "tool_call_count": 3,
            "summary": "CHANGED: src/a.py",
        }, self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        rows = Path(self.tmp.name, "subagent-stops.jsonl").read_text(encoding="utf-8").strip().splitlines()
        row = json.loads(rows[0])
        self.assertEqual(row["modified_files"], ["src/a.py"])
        self.assertEqual(row["duration_ms"], 12)
        self.assertEqual(row["tool_call_count"], 3)

    def test_subagent_stop_defaults_timing_to_zero(self) -> None:
        done = run_hook("subagent_stop.py", {
            "status": "completed",
            "modified_files": ["x.py"],
            "summary": "ok",
        }, self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        row = json.loads(Path(self.tmp.name, "subagent-stops.jsonl").read_text(encoding="utf-8").strip())
        self.assertEqual(row["duration_ms"], 0)
        self.assertEqual(row["tool_call_count"], 0)

    def test_timing_coverage_is_100_percent(self) -> None:
        run_hook("subagent_stop.py", {"summary": "a", "duration_ms": 1, "tool_call_count": 1}, self.env)
        run_hook("subagent_stop.py", {"summary": "b"}, self.env)  # defaults to 0
        cov = subprocess.run(
            [sys.executable, str(HOOKS / "timing_coverage.py")],
            capture_output=True, text=True, env={**os.environ, **self.env},
        )
        self.assertEqual(cov.returncode, 0, cov.stdout + cov.stderr)
        self.assertEqual(json.loads(cov.stdout)["coverage"], 1.0)

    def test_stop_writes_audit_passable_yaml(self) -> None:
        done = run_hook("stop_trace.py", {
            "status": "completed",
            "tool_call_count": 4,
            "duration_ms": 2500,
            "modified_files": ["hooks/stop_trace.py"],
            "feature": "demo-feat",
        }, self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        skel = Path(out["skeleton"])
        self.assertTrue(skel.is_file())
        body = skel.read_text(encoding="utf-8")
        self.assertIn("scenario: S8", body)
        self.assertIn("extensions: []", body)
        self.assertRegex(body, r"(?m)^calls:\s*$")
        self.assertIn("thinking:", body)
        self.assertIn("CONDUCTOR: replace with one thinking line", body)
        # fill_thinking replaces the placeholder
        filled = subprocess.run(
            [sys.executable, str(HOOKS / "fill_thinking.py"),
             "--skeleton", str(skel), "--summary", "phase1 stop skeleton"],
            capture_output=True, text=True,
        )
        self.assertEqual(filled.returncode, 0, filled.stderr)
        self.assertIn("phase1 stop skeleton", skel.read_text(encoding="utf-8"))
        self.assertNotIn("CONDUCTOR: replace", skel.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
