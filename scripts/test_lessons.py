#!/usr/bin/env python3
"""A decision prefix is a shape on the lesson. It does not run an agent."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lessons.py"

PREFIX = """\
goal: 核对下一步
env: 临时仓
agent: 测试
tools: lessons.py
before: ev/before.md
first_error:
  step: 写入
  kind: message
  category: 流程与规范缺失
  evidence: schema 只有六问
  cause: 写成了建议
  consequence: 召回对不上下一步
accept:
  - 有决策步就写 prefix
forbid:
  - 把召回当答案
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class LessonPrefix(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.home = self.repo / ".idev" / "task" / "demo"
        self.home.mkdir(parents=True)
        write(self.repo / "ev" / "before.md", "首错之前的上下文\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_lessons(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), "--feature", "demo", *args],
            capture_output=True,
            text=True,
        )

    def add(self, *extra: str, event: str = "verified") -> subprocess.CompletedProcess[str]:
        return self.run_lessons(
            "add",
            "--event",
            event,
            "--scope",
            "idev 经验台账",
            "--symptom",
            "失败只写成六问",
            "--evidence",
            "check 当时只验六问",
            "--action",
            "有决策步就写 prefix",
            "--outcome",
            "召回印出可接受和禁止",
            "--not-when",
            "没有决策步不造 prefix",
            *extra,
        )

    def test_fact_without_prefix_stays_clean(self):
        added = self.add()
        self.assertEqual(added.returncode, 0, added.stderr)
        checked = self.run_lessons("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertNotIn("没有 prefix", checked.stderr)

    def test_correction_without_prefix_warns(self):
        added = self.add(event="user-correction")
        self.assertEqual(added.returncode, 0, added.stderr)
        checked = self.run_lessons("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("没有 prefix", checked.stderr)
        self.assertIn("纯事实不用造前缀", checked.stderr)

    def test_incomplete_prefix_is_refused(self):
        text = PREFIX.replace("accept:\n  - 有决策步就写 prefix\n", "")
        write(self.repo / "ev" / "prefix.yaml", text)
        added = self.add("--prefix", "ev/prefix.yaml", event="failed-action")
        self.assertEqual(added.returncode, 2, added.stdout)
        self.assertIn("prefix.accept 至少一条", added.stderr)
        self.assertFalse((self.home / "lessons.yaml").exists())

    def test_before_outside_repo_is_refused(self):
        text = PREFIX.replace("before: ev/before.md", "before: ../before.md")
        write(self.repo / "ev" / "prefix.yaml", text)
        added = self.add("--prefix", "ev/prefix.yaml")
        self.assertEqual(added.returncode, 2, added.stderr)
        self.assertIn("相对路径", added.stderr)

    def test_prefix_is_recalled_as_a_boundary(self):
        write(self.repo / "ev" / "prefix.yaml", PREFIX)
        added = self.add("--prefix", "ev/prefix.yaml", event="user-correction")
        self.assertEqual(added.returncode, 0, added.stderr)
        recalled = self.run_lessons("recall", "--scope", "经验", "--no-count")
        self.assertEqual(recalled.returncode, 0, recalled.stderr)
        self.assertIn("可接受: 有决策步就写 prefix", recalled.stdout)
        self.assertIn("禁止: 把召回当答案", recalled.stdout)
        self.assertIn("不是答案", recalled.stdout)
        checked = self.run_lessons("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertNotIn("没有 prefix", checked.stderr)
        promoted = self.run_lessons("promote", "--id", "L1", "--by", "agent", "--repro", "ev/before.md")
        self.assertEqual(promoted.returncode, 2, promoted.stderr)

    def test_hand_edit_cannot_drop_a_forbidden_action(self):
        write(self.repo / "ev" / "prefix.yaml", PREFIX)
        self.assertEqual(self.add("--prefix", "ev/prefix.yaml").returncode, 0)
        path = self.home / "lessons.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        del data["lessons"][0]["prefix"]["forbid"]
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        checked = self.run_lessons("check")
        self.assertEqual(checked.returncode, 1, checked.stdout)
        self.assertIn("prefix.forbid 至少一条", checked.stderr)

    def test_schema_mentions_prefix(self):
        shown = self.run_lessons("schema")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("prefix", shown.stdout)
        self.assertIn("不执行 Agent", shown.stdout)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
