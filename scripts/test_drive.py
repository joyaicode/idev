#!/usr/bin/env python3
"""drive runs conductor commands and stops at the first agent."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
KERNEL = HERE.parent
sys.path.insert(0, str(HERE / "lib"))
import drive_run  # noqa: E402
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402

def _drive(show, record):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = drive_run.drive(Path("/tmp"), Path("/tmp"), {
            "feature": "demo",
            "workflow_id": "lite-change",
            "load": lambda: {},
            "show_next": show,
            "record": record,
        })
    return code, buf.getvalue()


GIT = {
    "GIT_AUTHOR_NAME": "idev",
    "GIT_AUTHOR_EMAIL": "idev@example.com",
    "GIT_COMMITTER_NAME": "idev",
    "GIT_COMMITTER_EMAIL": "idev@example.com",
}


class Drive(unittest.TestCase):
    def test_tool_command_appends_only_a_declared_feature(self) -> None:
        spec = drive_run.command_for(
            "tool.step", {"with": {"tool": "stage-gate"}}, Path("/tmp/repo"), "demo", "lite-change",
        )
        argv, cwd = spec
        self.assertEqual(argv[:2], ["python3", "scripts/stage-gate.py"])
        self.assertEqual(argv[-2:], ["--feature", "demo"])
        self.assertEqual(cwd, kind_agents.kernel_root())

    def test_a_write_shard_leases_only_its_paths(self) -> None:
        import workflow
        self.assertEqual(workflow.write_lease_paths(Path("/none"), "a", ["a/one.go"]), ["a/one.go"])

    def test_wake_names_an_agent_not_the_conductor(self) -> None:
        self.assertTrue(drive_run.wake("NEXT code-pass\nDELEGATE idev-coder\n"))
        self.assertFalse(drive_run.wake("DELEGATE none; the conductor does this step\n"))

    def test_a_wave_is_prepared_and_a_question_is_not(self) -> None:
        seen: list[str] = []

        def once(text: str) -> int:
            return drive_run.drive(Path("/tmp"), Path("/tmp"), {
                "feature": "demo",
                "workflow_id": "lite-change",
                "load": lambda: {},
                "show_next": lambda: (0, text),
                "record": lambda *_args: (0, ""),
                "handoff": lambda body: seen.append(body) or (0, "handed\n"),
            })

        wave = (
            "DIGEST x\nPARALLEL g\n"
            "NEXT a  kind=verify.plan  status=pending\nDELEGATE idev-verifier\n"
        )
        self.assertEqual(once(wave), 0)
        self.assertEqual(len(seen), 1)
        self.assertEqual(once("NEXT s kind=human.gate status=pending\nASK slot s\n"), 0)
        self.assertEqual(len(seen), 1)
        self.assertEqual(once("NEXT code-pass kind=deliver.code_pass status=pending\nDELEGATE idev-coder\n"), 0)
        self.assertEqual(len(seen), 2)

    def test_a_ceremonial_gate_is_recorded_and_the_next_step_shows(self) -> None:
        texts = iter([
            (0, "NEXT g kind=human.gate status=pending\nGATE pass. Will write: x\nGATE do not ask for a confirmation\n"),
            (0, "NEXT code kind=deliver.code_pass status=pending\nDELEGATE idev-coder\n"),
        ])
        recorded = []

        def show():
            return next(texts)

        def record(step, status, evidence):
            recorded.append((step, status, evidence))
            return 0, "recorded\n"

        code, out = _drive(show, record)
        self.assertEqual(code, 0)
        self.assertEqual(recorded, [("g", "PASS", "")])
        self.assertIn("DELEGATE idev-coder", out)

    def test_a_decision_gate_stops_without_a_record(self) -> None:
        recorded = []

        def show():
            return 0, "NEXT g kind=human.gate status=pending\nDECISION a person chooses\n"

        def record(step, status, evidence):
            recorded.append(step)
            return 0, ""

        code, out = _drive(show, record)
        self.assertEqual(code, 0)
        self.assertEqual(recorded, [])
        self.assertIn("DECISION", out)

    def test_cap_stops_after_eight_commands(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        calls = []

        def show():
            return 0, "NEXT s  kind=shell.confirmed  status=pending\nDELEGATE none\n"

        def record(step, status, evidence):
            calls.append((step, status))
            return 0, "ok\n"

        code = drive_run.drive(root, root, {
            "feature": "demo",
            "workflow_id": "lite-change",
            "load": lambda: {"steps": [{"id": "s", "with": {"cmd": "true"}}]},
            "show_next": show,
            "record": record,
        })
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 8)

    def test_drive_records_the_probes_and_stops_at_the_coder(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name) / "one"
        repo.mkdir()
        env = dict(os.environ, IDEV_BIN="off", IDEV_ENGINE="python", IDEV_RUN_WRITER="python",
                   IDEV_DATA=str(Path(tmp.name) / "data"),
                   PATH="/usr/bin" + os.pathsep + os.environ.get("PATH", ""), **GIT)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
        task = repo / ".idev" / "task" / "demo"
        task.mkdir(parents=True)
        (task / "deliver.yaml").write_text("stage: code\nrisk_tier: P1\n", encoding="utf-8")
        (task / "baseline.yaml").write_text("sealed: true\ngoal: keep\nnon_goal: drop\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True, env=env)
        start = subprocess.run(
            [sys.executable, str(KERNEL / "scripts" / "workflow.py"), "start", "lite-change", "--feature", "demo"],
            cwd=repo, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(start.returncode, 0, start.stdout + start.stderr)
        done = subprocess.run(
            [sys.executable, str(KERNEL / "scripts" / "workflow.py"), "drive", "--feature", "demo"],
            cwd=repo, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("DELEGATE idev-coder", done.stdout)
        self.assertIn("END BRIEF", done.stdout)
        self.assertIn("SERIAL code", done.stdout)
        run = safeyaml.mapping(task / "workflow" / "run.yaml")
        status = {step["id"]: step.get("status") for step in run["steps"]}
        self.assertEqual(status["preflight"], "PASS")
        self.assertEqual(status["scope-guard"], "PASS")
        self.assertNotEqual(status.get("code-pass"), "PASS")

    def test_drive_briefs_each_fanout_shard(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name) / "one"
        repo.mkdir()
        env = dict(os.environ, IDEV_BIN="off", IDEV_ENGINE="python", IDEV_RUN_WRITER="python",
                   IDEV_DATA=str(Path(tmp.name) / "data"),
                   PATH="/usr/bin" + os.pathsep + os.environ.get("PATH", ""), **GIT)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
        task = repo / ".idev" / "task" / "demo"
        task.mkdir(parents=True)
        (task / "deliver.yaml").write_text("stage: code\nrisk_tier: P1\n", encoding="utf-8")
        (task / "baseline.yaml").write_text("sealed: true\ngoal: keep\nnon_goal: drop\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True, env=env)
        (task / "arch.yaml").write_text(safeyaml.dump({
            "impact_candidates": [
                {"path": "a/one.go", "include": True},
                {"path": "b/two.go", "include": True},
            ],
        }), encoding="utf-8")
        start = subprocess.run(
            [sys.executable, str(KERNEL / "scripts" / "workflow.py"), "start", "lite-change", "--feature", "demo"],
            cwd=repo, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(start.returncode, 0, start.stdout + start.stderr)
        done = subprocess.run(
            [sys.executable, str(KERNEL / "scripts" / "workflow.py"), "drive", "--feature", "demo"],
            cwd=repo, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("FANOUT code", done.stdout)
        self.assertIn("分片: a", done.stdout)
        self.assertIn("分片: b", done.stdout)
        self.assertIn("只写: a/one.go", done.stdout)
        self.assertIn("只写: b/two.go", done.stdout)
        self.assertIn("land code-pass --shard a", done.stdout)
        self.assertEqual(done.stdout.count("END BRIEF"), 2)
        run = safeyaml.mapping(task / "workflow" / "run.yaml")
        code_pass = next(step for step in run["steps"] if step["id"] == "code-pass")
        self.assertEqual((code_pass.get("delegated") or {}).get("agent"), "idev-coder")
        self.assertNotEqual(code_pass.get("status"), "PASS")
        report = (
            "STATUS: PASS\nEVIDENCE: a/one.go\n"
            "FACTS: codegraph a/one.go and git diff\n"
            "DOC_DRIFT: none\nASSUMED: none\n"
            "SCOPE: a/one.go\nREAD: a/one.go\nCHANGED: a/one.go\n"
            "REVERT: git checkout -- a/one.go\n"
            "CHANGE_KIND: local\nCANON_TRIGGER: none\nTABLE_HIT: none\n"
        )
        land = subprocess.run(
            [sys.executable, str(KERNEL / "scripts" / "workflow.py"),
             "land", "code-pass", "--shard", "a", "--feature", "demo", "--report", "-"],
            cwd=repo, env=env, input=report, capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(land.returncode, 2, land.stdout + land.stderr)
        self.assertNotIn("record the step once", land.stdout)
        (repo / "a").mkdir()
        (repo / "b").mkdir()
        (repo / "a" / "one.go").write_text("package a\n", encoding="utf-8")
        (repo / "b" / "two.go").write_text("package b\n", encoding="utf-8")
        other = report.replace("a/one.go", "b/two.go")
        land_b = subprocess.run(
            [sys.executable, str(KERNEL / "scripts" / "workflow.py"),
             "land", "code-pass", "--shard", "b", "--feature", "demo", "--report", "-"],
            cwd=repo, env=env, input=other, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(land_b.returncode, 0, land_b.stdout + land_b.stderr)
        self.assertIn("record the step once", land_b.stdout)
        run = safeyaml.mapping(task / "workflow" / "run.yaml")
        code_pass = next(step for step in run["steps"] if step["id"] == "code-pass")
        self.assertNotEqual(code_pass.get("status"), "PASS")
        folder = task / "workflow" / "delegations" / str(run["run_id"])
        written = list(folder.glob("code-pass-a-*.yaml"))
        self.assertTrue(written, land.stdout + land.stderr)
        self.assertIn("shard: a", written[0].read_text(encoding="utf-8"))

    def test_handoff_merges_finished_report_shards(self) -> None:
        import fanout
        import workflow
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        task = root / ".idev" / "task" / "feat"
        task.mkdir(parents=True)
        (task / "deliver.yaml").write_text("stage: code\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        for name in ("mod-a", "mod-b"):
            directory = root / name
            directory.mkdir()
            (directory / "A.java").write_text("class A {}\n", encoding="utf-8")
        first = fanout.assess("feat", "report", root)
        self.assertEqual(first["decision"], "FANOUT")
        for shard in first["shards"]:
            path = task / shard["writes"][0]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("### UNPROVEN\n\nnot opened\n", encoding="utf-8")
        text = (
            "NEXT report  kind=review.report  status=pending\n"
            "DELEGATE idev-reviewer\n"
            "FANOUT_ASSESS report python3 scripts/fanout.py assess "
            "--feature feat --activity report\n"
        )
        code, out = workflow._handoff(
            argparse.Namespace(repo=str(root), feature="feat", run="", step=""),
            text,
        )
        self.assertEqual(code, 0, out)
        self.assertIn("MERGE report", out)
        self.assertNotIn("END BRIEF", out)
        self.assertTrue((task / "review.md").is_file())

    def test_handoff_leaves_prep_for_the_conductor(self) -> None:
        import workflow
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        task = root / ".idev" / "task" / "feat"
        task.mkdir(parents=True)
        (task / "deliver.yaml").write_text("stage: code\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        for name in ("mod-a", "mod-b"):
            directory = root / name
            directory.mkdir()
            (directory / "A.java").write_text("class A {}\n", encoding="utf-8")
        text = (
            "NEXT report  kind=review.report  status=pending\n"
            "DELEGATE idev-reviewer\n"
            "FANOUT_ASSESS report python3 scripts/fanout.py assess "
            "--feature feat --activity report\n"
        )
        code, out = workflow._handoff(
            argparse.Namespace(repo=str(root), feature="feat", run="", step=""),
            text,
        )
        self.assertEqual(code, 0, out)
        self.assertIn("PREP ", out)
        self.assertNotIn("END BRIEF", out)

    def test_a_compile_line_is_not_a_kernel_script(self) -> None:
        import prep_run
        self.assertIsNone(prep_run.kernel_argv("mod mvn -pl mod -am -Pex test-compile"))
        argv = prep_run.kernel_argv(f"bash {KERNEL}/scripts/coding-scan.sh {KERNEL}")
        self.assertEqual(argv[0], "bash")
        self.assertTrue(argv[1].endswith("coding-scan.sh"))

    def test_drive_runs_the_scan_then_briefs_report_shards(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name) / "one"
        repo.mkdir()
        env = dict(os.environ, IDEV_BIN="off", IDEV_ENGINE="python", IDEV_RUN_WRITER="python",
                   IDEV_DATA=str(Path(tmp.name) / "data"),
                   PATH="/usr/bin" + os.pathsep + os.environ.get("PATH", ""), **GIT)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
        task = repo / ".idev" / "task" / "demo"
        (task / "workflow").mkdir(parents=True)
        (repo / ".idev" / "workflows").mkdir()
        (repo / ".idev" / "marker.yaml").write_text(
            "schema_version: 1\nmarker: idev\nid: demo\nevolve: false\n", encoding="utf-8",
        )
        (task / "deliver.yaml").write_text("stage: code\nrisk_tier: P1\n", encoding="utf-8")
        for name in ("mod-a", "mod-b"):
            directory = repo / name
            directory.mkdir()
            (directory / "A.java").write_text("class A {}\n", encoding="utf-8")
        (repo / ".idev" / "workflows" / "scan.yaml").write_text(
            "schema_version: 1\nid: scan\nsummary: x\n"
            "params:\n  - {name: feature, required: true, from: user}\n"
            "steps:\n  - {id: report, kind: review.report}\n",
            encoding="utf-8",
        )
        start = subprocess.run(
            [sys.executable, str(KERNEL / "scripts" / "workflow.py"), "start", "scan", "--feature", "demo"],
            cwd=repo, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(start.returncode, 0, start.stdout + start.stderr)
        done = subprocess.run(
            [sys.executable, str(KERNEL / "scripts" / "workflow.py"), "drive", "--feature", "demo"],
            cwd=repo, env=env, capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("PREP exit=", done.stdout)
        self.assertIn("分片: mod-a", done.stdout)
        self.assertIn("分片: mod-b", done.stdout)
        self.assertIn("扫描:", done.stdout)
        self.assertEqual(done.stdout.count("END BRIEF"), 2)
        log = task / "workflow" / "prep-report.log"
        self.assertTrue(log.is_file(), done.stdout)
        self.assertIn("idev coding-scan", log.read_text(encoding="utf-8"))
        run = safeyaml.mapping(task / "workflow" / "run.yaml")
        report = next(step for step in run["steps"] if step["id"] == "report")
        self.assertNotEqual(report.get("status"), "PASS")

    def test_drive_briefs_an_open_wave(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name) / "one"
        repo.mkdir()
        env = dict(os.environ, IDEV_BIN="off", IDEV_ENGINE="python", IDEV_RUN_WRITER="python",
                   IDEV_DATA=str(Path(tmp.name) / "data"),
                   PATH="/usr/bin" + os.pathsep + os.environ.get("PATH", ""), **GIT)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
        task = repo / ".idev" / "task" / "demo"
        (task / "workflow").mkdir(parents=True)
        (repo / ".idev" / "workflows").mkdir()
        (repo / ".idev" / "marker.yaml").write_text(
            "schema_version: 1\nmarker: idev\nid: demo\nevolve: false\n", encoding="utf-8",
        )
        (task / "deliver.yaml").write_text("stage: code\nrisk_tier: P1\n", encoding="utf-8")
        (repo / ".idev" / "workflows" / "wave.yaml").write_text(
            "schema_version: 1\nid: wave\nsummary: x\n"
            "params:\n  - {name: feature, required: true, from: user}\n"
            "steps:\n"
            "  - {id: plan, kind: verify.plan, group: check, writes: [verify/plan.yaml],"
            " with: {mode: selftest}}\n"
            "  - {id: review, kind: review.report, group: check, writes: [review.md]}\n",
            encoding="utf-8",
        )
        start = subprocess.run(
            [sys.executable, str(KERNEL / "scripts" / "workflow.py"), "start", "wave", "--feature", "demo"],
            cwd=repo, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(start.returncode, 0, start.stdout + start.stderr)
        done = subprocess.run(
            [sys.executable, str(KERNEL / "scripts" / "workflow.py"), "drive", "--feature", "demo"],
            cwd=repo, env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("PARALLEL check", done.stdout)
        self.assertIn("本步: plan", done.stdout)
        self.assertIn("本步: review", done.stdout)
        self.assertEqual(done.stdout.count("END BRIEF"), 2)
        run = safeyaml.mapping(task / "workflow" / "run.yaml")
        status = {step["id"]: step.get("status") for step in run["steps"]}
        self.assertNotEqual(status.get("plan"), "PASS")
        self.assertNotEqual(status.get("review"), "PASS")
        agents = {step["id"]: (step.get("delegated") or {}).get("agent") for step in run["steps"]}
        self.assertEqual(agents["plan"], "idev-verifier")
        self.assertEqual(agents["review"], "idev-reviewer")


if __name__ == "__main__":
    unittest.main()
