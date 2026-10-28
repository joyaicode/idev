#!/usr/bin/env python3
"""The conductor's cold start stays within budget; other pages show how often rounds open them.

    python3 scripts/test_cold_start.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
KERNEL = HERE.parent
SCRIPT = HERE / "cold-start-size.py"
COLD = ("SKILL.md", "references/agent-brief.md")


def size(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True)


def kernel(root: Path, skill: int, brief: int, **pages: int) -> None:
    (root / "references").mkdir()
    (root / "SKILL.md").write_text("x" * skill, encoding="utf-8")
    (root / "references" / "agent-brief.md").write_text("y" * brief, encoding="utf-8")
    for name, n in pages.items():
        (root / "references" / f"{name}.md").write_text("z" * n, encoding="utf-8")


class ColdStartBudget(unittest.TestCase):
    def test_the_pages_are_the_ones_agent_brief_names(self) -> None:
        brief = (KERNEL / "references" / "agent-brief.md").read_text(encoding="utf-8")
        section = brief.split("## 冷启动", 1)[1].split("\n## ", 1)[0]
        moved = "agent-brief.md changed the cold start; update COLD in scripts/cold-start-size.py"
        self.assertTrue(section.startswith("（只读两页）"), moved)
        self.assertIn("**本页**", section, moved)
        self.assertIn("**`SKILL.md`", section, moved)

    def test_the_kernel_counts_only_the_two_pages_agent_brief_names(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            proc = size("--kernel", str(KERNEL), "--traces", empty)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        total = sum(len((KERNEL / p).read_text(encoding="utf-8")) for p in COLD)
        self.assertIn(f"PASS cold start {total} <= 24000", proc.stdout)

    def test_a_cold_start_over_budget_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kernel(Path(tmp), 23000, 1001)
            proc = size("--kernel", tmp, "--traces", tmp)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("FAIL cold start 24001 > 24000", proc.stdout)
        with tempfile.TemporaryDirectory() as empty:
            proc = size("--kernel", str(KERNEL), "--traces", empty, "--budget", "1000")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_the_budget_is_inclusive_and_on_demand_pages_stay_out_of_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kernel(Path(tmp), 23000, 1000, **{"chat-confirm-signoff": 9000})
            proc = size("--kernel", tmp, "--traces", tmp)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS cold start 24000 <= 24000", proc.stdout)
        self.assertRegex(proc.stdout, r"9000\s+references/chat-confirm-signoff\.md")


class OpenRates(unittest.TestCase):
    def test_rates_read_the_opened_field_of_traces_that_have_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            traces = Path(tmp)
            (traces / "20261028-001.yaml").write_text(
                "schema_version: 2\nopened:\n  - references/chat-confirm-signoff.md\n"
                "  - references/chat-confirm-signoff.md\n"
                "  - ~/.cursor/skills/idev/references/invoke.md\n"
                f"  - {KERNEL}/references/glossary.md\n", encoding="utf-8")
            (traces / "20261028-002.yaml").write_text(
                "schema_version: 2\nopened: [SKILL.md, /repo/joypaas/.idev/pack/conventions/SKILL.md]\n",
                encoding="utf-8")
            (traces / "20261028-003.yaml").write_text(
                "schema_version: 2\nopened: []\n"
                "notes: 没打开 references/skill-details.md，也没读 references/chat-confirm-signoff.md\n",
                encoding="utf-8")
            (traces / "20261019-001.yaml").write_text(
                "schema_version: 1\nnotes: references/invoke.md\n", encoding="utf-8")
            proc = size("--kernel", str(KERNEL), "--traces", tmp)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = proc.stdout
        self.assertIn("3 traces with opened", out)
        self.assertRegex(out, r"references/chat-confirm-signoff\.md\s+opened 1/3\b")
        self.assertRegex(out, r"references/invoke\.md\s+opened 1/3\b")
        self.assertRegex(out, r"references/glossary\.md\s+opened 1/3\b")
        self.assertRegex(out, r"(?m)^\s*\d+\s+SKILL\.md\s+opened 1/3\b")
        self.assertRegex(out, r"conventions/SKILL\.md\s+opened 0/3\b")
        self.assertRegex(out, r"references/skill-details\.md\s+opened 0/3\b")


if __name__ == "__main__":
    unittest.main()
