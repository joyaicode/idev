#!/usr/bin/env python3
"""One person wears every role; several people are asked one batch each.

    python3 scripts/test_staffing.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import staffing  # noqa: E402

ROLES = staffing.ROLES


def people(repo: Path, names: list[str]) -> None:
    path = repo / ".idev" / "people.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "schema_version: 1\npeople:\n" + "".join(f"  - {name}\n" for name in names)
    path.write_text(body, encoding="utf-8")


def kernel_with(tmp: Path, names: list[str]) -> Path:
    kernel = tmp / "kernel"
    people(kernel, names)
    # people() writes .idev/people.yaml; the kernel list lives at config/.
    (kernel / ".idev" / "people.yaml").unlink()
    config = kernel / "config"
    config.mkdir(parents=True)
    body = "schema_version: 1\npeople:\n" + "".join(f"  - {name}\n" for name in names)
    (config / "people.yaml").write_text(body, encoding="utf-8")
    return kernel


class Resolve(unittest.TestCase):
    def test_one_product_person_holds_every_role(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            repo.mkdir()
            people(repo, ["alice"])
            staff = staffing.resolve(repo, kernel_with(root, ["operator", "bob"]), git_name="operator")
        self.assertEqual(staff.mode, "solo")
        self.assertEqual(staff.source, "product-people")
        self.assertEqual(staff.chat, "alice")
        self.assertEqual(staff.ask, "none")
        self.assertEqual(staff.people, ["alice"])
        self.assertTrue(all(staff.roles[role] == ["alice"] for role in ROLES))
        self.assertNotIn("operator", staff.people)
        self.assertEqual(staffing.refusal(staff, "alice", "accepted_arch", "arch"), "")

    def test_kernel_list_is_the_fallback(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            repo.mkdir()
            staff = staffing.resolve(repo, kernel_with(root, ["wangwei794"]), git_name="")
        self.assertEqual(staff.mode, "solo")
        self.assertEqual(staff.source, "kernel-people")
        self.assertEqual(staff.chat, "wangwei794")
        self.assertIn("hold=product,design,arch,dev,test,delivery,ops=wangwei794", staffing.format_line(staff))
        self.assertIn("wait=-", staffing.format_line(staff))

    def test_two_people_without_a_map_ask_once(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            repo.mkdir()
            people(repo, ["alice", "bob"])
            staff = staffing.resolve(repo, kernel_with(root, ["operator"]), git_name="alice")
        self.assertEqual(staff.mode, "unassigned")
        self.assertEqual(staff.ask, "assign")
        self.assertEqual(staff.chat, "alice")
        self.assertIn("只问一次", staffing.note_line(staff))
        self.assertIn("staffing is unassigned", staffing.refusal(staff, "alice", "accepted_req", "req"))
        self.assertIn("staffing is unassigned", staffing.refusal(staff, "bob", "accepted_arch", "arch"))

    def test_split_map_asks_only_the_chat_users_roles(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            repo.mkdir()
            roles = {role: ["bob"] for role in ROLES}
            roles["product"] = ["alice"]
            roles["design"] = ["alice"]
            staffing.write_map(repo, roles)
            staff = staffing.resolve(repo, kernel_with(root, ["operator"]), chat="alice", git_name="")
        self.assertEqual(staff.mode, "collaborative")
        self.assertEqual(staff.ask, "none")
        line = staffing.format_line(staff)
        self.assertIn("hold=product,design=alice", line)
        self.assertIn("arch,dev,test,delivery,ops=bob", line)
        self.assertEqual(staffing.refusal(staff, "alice", "accepted_req", ""), "")
        self.assertIn("不在这个岗位上", staffing.refusal(staff, "alice", "accepted_arch", "arch"))
        self.assertEqual(staffing.refusal(staff, "bob", "step_confirm", "code"), "")
        self.assertIn("不在这个岗位上", staffing.refusal(staff, "alice", "step_confirm", "test"))

    def test_write_solo_collapses_to_one_person(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            path = staffing.write_map(repo, {role: ["alice"] for role in ROLES})
            self.assertTrue(path.is_file())
            staff = staffing.resolve(repo, Path(raw) / "no-kernel", git_name="bob")
        self.assertEqual(staff.mode, "solo")
        self.assertEqual(staff.source, "staffing.yaml")
        self.assertEqual(staff.chat, "alice")

    def test_incomplete_map_stays_unassigned(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            (repo / ".idev").mkdir()
            (repo / ".idev" / "staffing.yaml").write_text(
                "schema_version: 1\nroles:\n  product: [alice]\n",
                encoding="utf-8",
            )
            staff = staffing.resolve(repo, Path(raw) / "no-kernel", git_name="")
        self.assertEqual(staff.mode, "unassigned")
        self.assertEqual(staff.source, "staffing-incomplete")
        self.assertEqual(staff.ask, "assign")

    def test_agent_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            with self.assertRaises(ValueError):
                staffing.write_map(repo, {role: ["idev-coder"] for role in ROLES})

    def test_empty_name_list_does_not_borrow_git(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            repo.mkdir()
            people(repo, [])
            staff = staffing.resolve(repo, kernel_with(root, ["operator"]), git_name="operator")
        self.assertEqual(staff.mode, "unassigned")
        self.assertEqual(staff.ask, "name")
        self.assertNotEqual(staff.chat, "operator")


class RecordGate(unittest.TestCase):
    def test_the_wrong_role_cannot_sign_and_the_holder_can(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            ticket = repo / ".idev" / "task" / "staff-demo"
            (ticket / "verify").mkdir(parents=True)
            (repo / ".git").mkdir()
            (ticket / "deliver.yaml").write_text(
                textwrap.dedent(
                    """\
                    schema_version: 2
                    feature: staff-demo
                    stage: code
                    risk_tier: P1
                    """
                ),
                encoding="utf-8",
            )
            (ticket / "verify" / "plan.yaml").write_text("cases: []\n", encoding="utf-8")
            people(repo, ["alice", "bob"])
            roles = {role: ["bob"] for role in ROLES}
            roles["product"] = ["alice"]
            roles["design"] = ["alice"]
            staffing.write_map(repo, roles)

            def run(*args: str) -> subprocess.CompletedProcess:
                env = {**os.environ, "IDEV_PROMPT_LOG_CHECK": "0"}
                env.pop("IDEV_PRODUCT_REPO", None)
                env.pop("IDEV_ENGINE", None)
                return subprocess.run(
                    [sys.executable, str(HERE / "workflow.py"), "--repo", str(repo), *args],
                    capture_output=True, text=True, env=env, cwd=repo,
                )

            started = run("start", "dev-logic", "--feature", "staff-demo")
            self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
            run_path = ticket / "workflow" / "run.yaml"
            data = yaml.safe_load(run_path.read_text(encoding="utf-8"))
            for step in data["steps"]:
                if step["id"] == "plan":
                    step["status"] = "PASS"
                    step["at"] = "2026-10-28T00:00:00+08:00"
            run_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            denied = run(
                "record", "gate-plan", "PASS", "--by", "alice", "--quote", "确认", "--feature", "staff-demo"
            )
            self.assertEqual(denied.returncode, 2, denied.stdout + denied.stderr)
            self.assertIn("不在这个岗位上", denied.stderr)
            allowed = run(
                "record", "gate-plan", "PASS", "--by", "bob", "--quote", "确认", "--feature", "staff-demo"
            )
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)


if __name__ == "__main__":
    unittest.main()
