#!/usr/bin/env python3
"""skill-up stays a rule suite: no score gate, and it runs only after a kernel change."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
HOOKS = ROOT / "hooks"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


mod = load("skill_up_eval_mod", SCRIPTS / "skill-up-eval.py")
hook = load("skill_up_eval_hook", HOOKS / "skill_up_eval.py")


def git(root: Path, args: list[str]) -> None:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = "t@example.com"
    env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_COMMITTER_EMAIL"] = "t@example.com"
    subprocess.check_call(["git", "-C", str(root), *args], env=env)


def init_repo(root: Path) -> None:
    git(root, ["init"])
    (root / "SKILL.md").write_text("name: idev\n", encoding="utf-8")
    git(root, ["add", "SKILL.md"])
    git(root, ["commit", "-m", "init"])


class SkillUpEval(unittest.TestCase):
    def temp_root(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_real_suite_has_no_score_gate(self) -> None:
        self.assertEqual(mod.check_suite(ROOT), 0)

    def test_suite_rejects_model_judge(self) -> None:
        root = self.temp_root()
        self.write_bad_suite(root)
        self.assertEqual(mod.check_suite(root), 1)
        self.assertEqual(mod.score_gate("type: rule_based\n"), "")

    def write_bad_suite(self, root: Path) -> None:
        case = root / "evals" / "cases"
        case.mkdir(parents=True)
        (root / "evals" / "eval.yaml").write_text(
            "schema_version: v1alpha1\ncases:\n  files:\n    - evals/cases/a.yaml\n"
            "judge:\n  type: agent_judge\n",
            encoding="utf-8",
        )
        (case / "a.yaml").write_text("expect:\n  must_contain:\n    - x\n", encoding="utf-8")

    def test_notes_and_state_do_not_count(self) -> None:
        self.assertFalse(mod.surface("scripts/docs/notes/x.md"))
        self.assertFalse(mod.surface("state/skill-up/stamp"))
        self.assertTrue(mod.surface("SKILL.md"))
        self.assertTrue(mod.surface("evals/eval.yaml"))

    def test_unchanged_tree_skips(self) -> None:
        root = self.temp_root()
        init_repo(root)
        mod.write_stamp(root, mod.fingerprint(root), "pass")
        self.assertEqual(mod.plan(root, False), "skip-unchanged")

    def test_edit_plans_a_run_when_cli_and_engine_exist(self) -> None:
        root = self.temp_root()
        init_repo(root)
        (root / "SKILL.md").write_text("name: idev\nchanged\n", encoding="utf-8")
        self.assertEqual(self.planned(root), "run")

    def planned(self, root: Path) -> str:
        with mock.patch.object(mod, "skill_up_bin", return_value="/bin/skill-up"), \
             mock.patch.object(mod, "pick_engine", return_value="claude_code"):
            return mod.plan(root, False)

    def test_missing_cli_skips(self) -> None:
        root = self.temp_root()
        init_repo(root)
        with mock.patch.object(mod, "skill_up_bin", return_value=""):
            self.assertEqual(mod.plan(root, True), "skip-cli")

    def test_lock_is_exclusive_until_released(self) -> None:
        root = self.temp_root()
        self.assertTrue(mod.take_lock(root, "abc"))
        self.assertFalse(mod.take_lock(root, "abc"))
        mod.release_lock(root)
        self.assertTrue(mod.take_lock(root, "def"))


class SkillUpHook(unittest.TestCase):
    def test_disabled_does_not_spawn(self) -> None:
        with mock.patch.dict(os.environ, {"SKILL_UP_EVAL": "0"}), \
             mock.patch.object(hook, "spawn") as spawn:
            self.assertEqual(hook.main(["--client", "cursor"]), 0)
        spawn.assert_not_called()

    def test_enabled_spawns_without_waiting(self) -> None:
        root = self.temp_root()
        with mock.patch.object(hook.subprocess, "Popen") as popen:
            hook.spawn(root)
        args, kwargs = popen.call_args
        self.assertIn("skill-up-eval.py", args[0][1])
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)

    def temp_root(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_install_registers_one_stop_hook(self) -> None:
        repo = self.temp_root()
        done = self.install(repo)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.install(repo)
        commands = self.stop_commands(repo)
        self.assertEqual(sum("skill_up_eval.py" in c for c in commands), 1)

    def test_claude_stop_runs_the_same_hook(self) -> None:
        repo = self.temp_root()
        done = self.install(repo)
        self.assertEqual(done.returncode, 0, done.stderr)
        raw = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
        commands = [h["command"] for block in raw["hooks"]["Stop"] for h in block["hooks"]]
        self.assertEqual(sum("skill_up_eval.py" in c for c in commands), 1)

    def install(self, repo: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(SCRIPTS / "install-idev-hooks.sh"), "--repo", str(repo)],
            capture_output=True, text=True,
        )

    def stop_commands(self, repo: Path) -> list[str]:
        raw = json.loads((repo / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
        return [item["command"] for item in raw["hooks"]["stop"]]


if __name__ == "__main__":
    unittest.main()
