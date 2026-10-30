#!/usr/bin/env python3
"""sediment.py keeps one success as a note and does not run a script."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sediment.py"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Sediment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.home = self.repo / ".idev" / "task" / "sed"
        self.home.mkdir(parents=True)
        write(self.repo / "ev" / "once.log", "first result\n")
        write(self.repo / "ev" / "twice.log", "second result\n")
        write(self.repo / "ev" / "repro.log", "replayed\n")
        write(self.repo / "do.sh", "#!/bin/sh\ntouch \"$0.ran\"\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_sed(self, *args: str, feature: str = "sed") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), "--feature", feature, *args],
            capture_output=True,
            text=True,
        )

    def add(self, *extra: str) -> subprocess.CompletedProcess[str]:
        trust = ["--trust", "reviewed"]
        if "--trust" in extra:
            trust = []
        return self.run_sed(
            "add",
            "--form",
            "program",
            *trust,
            "--scope",
            "库存回写",
            "--claim",
            "积压在生产侧时先看位点再看消费者",
            "--not-when",
            "位点连续推进时不适用",
            *extra,
        )

    def test_source_does_not_call_other_ledgers_or_run_code(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("import lessons", text)
        self.assertNotIn("realign", text)
        self.assertNotIn("subprocess", text)

    def test_one_result_stays_a_candidate(self):
        added = self.add("--evidence", "ev/once.log", "--script", "do.sh")
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertIn("candidate", added.stdout)
        transformed = self.run_sed(
            "transform", "--id", "S1", "--by", "wangwei794", "--repro", "ev/repro.log"
        )
        self.assertEqual(transformed.returncode, 2, transformed.stderr)
        self.assertIn("一次成功还不是能力", transformed.stderr)
        self.assertFalse((self.repo / "do.sh.ran").exists())

    def test_two_results_keep_without_running_the_script(self):
        added = self.add(
            "--evidence", "ev/once.log", "--evidence", "ev/twice.log", "--script", "do.sh"
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        transformed = self.run_sed(
            "transform", "--id", "S1", "--by", "wangwei794", "--repro", "ev/repro.log"
        )
        self.assertEqual(transformed.returncode, 0, transformed.stderr)
        self.assertIn("kept", transformed.stdout)
        self.assertIn("没有执行脚本", transformed.stdout)
        self.assertFalse((self.repo / "do.sh.ran").exists())
        recalled = self.run_sed("recall", "--scope", "库存")
        self.assertEqual(recalled.returncode, 0, recalled.stderr)
        self.assertIn("不执行", recalled.stdout)
        self.assertIn("不是答案", recalled.stdout)

    def test_script_path_does_not_count_as_a_result(self):
        added = self.add("--evidence", "do.sh", "--evidence", "ev/once.log", "--script", "do.sh")
        self.assertEqual(added.returncode, 0, added.stderr)
        transformed = self.run_sed(
            "transform", "--id", "S1", "--by", "wangwei794", "--repro", "ev/repro.log"
        )
        self.assertEqual(transformed.returncode, 2)
        self.assertIn("脚本本身不算一次结果", transformed.stderr)

    def test_copied_log_is_still_one_success(self):
        write(self.repo / "ev" / "copy.log", "first result\n")
        added = self.add(
            "--evidence", "ev/once.log", "--evidence", "ev/copy.log", "--script", "do.sh"
        )
        self.assertEqual(added.returncode, 2)
        self.assertIn("内容相同", added.stderr)

    def test_fact_and_external_text_stay_out(self):
        fact = self.run_sed(
            "add",
            "--form",
            "fact",
            "--trust",
            "reviewed",
            "--scope",
            "库存回写",
            "--claim",
            "积压在生产侧",
            "--not-when",
            "位点连续推进时不适用",
            "--evidence",
            "ev/once.log",
        )
        self.assertEqual(fact.returncode, 2)
        self.assertIn("事实不进这本账", fact.stderr)
        self.assertIn("lessons.py", fact.stderr)
        judgment = self.run_sed(
            "add",
            "--form",
            "instruction",
            "--trust",
            "reviewed",
            "--scope",
            "库存回写",
            "--claim",
            "先看位点再下结论",
            "--not-when",
            "位点连续推进时不适用",
            "--evidence",
            "ev/once.log",
        )
        self.assertEqual(judgment.returncode, 2)
        self.assertIn("要看语境的判断不进这本账", judgment.stderr)
        refused = self.add("--trust", "external", "--evidence", "ev/once.log", "--script", "do.sh")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("外部内容不能写成程序", refused.stderr)
        self.assertFalse((self.home / "sediment.yaml").exists())

    def test_model_cannot_confirm(self):
        self.add("--evidence", "ev/once.log", "--evidence", "ev/twice.log", "--script", "do.sh")
        transformed = self.run_sed(
            "transform", "--id", "S1", "--by", "agent", "--repro", "ev/repro.log"
        )
        self.assertEqual(transformed.returncode, 2)
        self.assertIn("不是人", transformed.stderr)

    def test_prompt_file_is_not_a_program(self):
        write(self.repo / "SKILL.md", "# rules\n")
        refused = self.add("--evidence", "ev/once.log", "--script", "SKILL.md")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("不能当程序", refused.stderr)

    def test_path_outside_the_repo_is_refused(self):
        outside = Path(self.tmp.name).parent / f"sediment-outside-{os.getpid()}.log"
        outside.write_text("secret\n", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        refused = self.add("--evidence", str(outside), "--script", "do.sh")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("不在仓库里", refused.stderr)
        link = self.repo / "link.log"
        link.symlink_to(outside)
        linked = self.add("--evidence", "link.log", "--script", "do.sh")
        self.assertEqual(linked.returncode, 2)
        self.assertIn("不在仓库里", linked.stderr)

    def test_gc_names_a_duplicate_and_does_not_write(self):
        first = self.run_sed(
            "add",
            "--form",
            "program",
            "--trust",
            "reviewed",
            "--scope",
            "库存回写",
            "--claim",
            "积压在生产侧时先看位点",
            "--not-when",
            "位点连续推进时不适用",
            "--evidence",
            "ev/once.log",
            "--script",
            "do.sh",
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_sed(
            "add",
            "--form",
            "program",
            "--trust",
            "reviewed",
            "--scope",
            "库存回写",
            "--claim",
            "积压在生产侧时先看位点",
            "--not-when",
            "位点连续推进时不适用",
            "--evidence",
            "ev/twice.log",
            "--script",
            "do.sh",
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        ledger = self.home / "sediment.yaml"
        before = ledger.read_bytes()
        found = self.run_sed("gc")
        self.assertEqual(found.returncode, 1)
        self.assertIn("GC duplicate S2 与 S1 同文", found.stdout)
        self.assertEqual(ledger.read_bytes(), before)

    def test_hand_edited_kept_is_caught(self):
        write(
            self.home / "sediment.yaml",
            textwrap.dedent(
                """\
                schema_version: 1
                entries:
                  - id: S1
                    status: kept
                    form: program
                    trust: reviewed
                    scope: 库存回写
                    claim: 先看证据
                    not_when: 没有第二份记录时不适用
                    evidence: [ev/once.log]
                    script: do.sh
                    confirmed_by: ""
                    repro: ""
                    uses: 0
                """
            ),
        )
        checked = self.run_sed("check")
        self.assertEqual(checked.returncode, 1)
        self.assertIn("一次成功还不是能力", checked.stderr)
        self.assertIn("不是人", checked.stderr)
        self.assertIn("没有钉住字节", checked.stderr)

    def test_broken_ledger_is_not_overwritten(self):
        ledger = self.home / "sediment.yaml"
        ledger.write_text("[]\n", encoding="utf-8")
        before = ledger.read_bytes()
        added = self.add("--evidence", "ev/once.log", "--script", "do.sh")
        self.assertEqual(added.returncode, 2)
        self.assertIn("台账读不了", added.stderr)
        self.assertEqual(ledger.read_bytes(), before)

    def test_missing_ticket_is_refused(self):
        missing = self.run_sed("check", feature="nope")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("no ticket home", missing.stderr)

    def test_repro_cannot_reuse_the_draft(self):
        self.add("--evidence", "ev/once.log", "--evidence", "ev/twice.log", "--script", "do.sh")
        same_path = self.run_sed(
            "transform", "--id", "S1", "--by", "wangwei794", "--repro", "ev/once.log"
        )
        self.assertEqual(same_path.returncode, 2, same_path.stderr)
        self.assertIn("起草时已经用过", same_path.stderr)
        write(self.repo / "ev" / "same.log", "first result\n")
        same_bytes = self.run_sed(
            "transform", "--id", "S1", "--by", "wangwei794", "--repro", "ev/same.log"
        )
        self.assertEqual(same_bytes.returncode, 2, same_bytes.stderr)
        self.assertIn("内容相同", same_bytes.stderr)
        script = self.run_sed(
            "transform", "--id", "S1", "--by", "wangwei794", "--repro", "do.sh"
        )
        self.assertEqual(script.returncode, 2, script.stderr)
        self.assertIn("不能是脚本本身", script.stderr)
        recalled = self.run_sed("recall", "--scope", "库存")
        self.assertIn("[候选]", recalled.stdout)
        self.assertNotIn("[留下]", recalled.stdout)

    def test_hand_edited_repro_from_the_draft_is_caught(self):
        write(
            self.home / "sediment.yaml",
            textwrap.dedent(
                """\
                schema_version: 1
                entries:
                  - id: S1
                    status: kept
                    form: program
                    trust: reviewed
                    scope: 库存回写
                    claim: 先看证据
                    not_when: 没有第二份记录时不适用
                    evidence: [ev/once.log, ev/twice.log]
                    script: do.sh
                    confirmed_by: wangwei794
                    repro: ev/once.log
                    uses: 0
                """
            ),
        )
        checked = self.run_sed("check")
        self.assertEqual(checked.returncode, 1, checked.stderr)
        self.assertIn("起草时已经用过", checked.stderr)

    def test_same_path_twice_is_refused(self):
        refused = self.add(
            "--evidence", "ev/once.log", "--evidence", "ev/once.log", "--script", "do.sh"
        )
        self.assertEqual(refused.returncode, 2)
        self.assertIn("同一个文件", refused.stderr)

    def test_changed_script_is_not_the_kept_capability(self):
        added = self.add(
            "--evidence", "ev/once.log", "--evidence", "ev/twice.log", "--script", "do.sh"
        )
        self.assertEqual(added.returncode, 0, added.stderr)
        kept = self.run_sed(
            "transform", "--id", "S1", "--by", "wangwei794", "--repro", "ev/repro.log"
        )
        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.assertIn("字节已钉住", kept.stdout)
        self.assertIn("bound:", (self.home / "sediment.yaml").read_text(encoding="utf-8"))
        self.assertFalse((self.repo / "do.sh.ran").exists())
        (self.repo / "do.sh").write_text("#!/bin/sh\necho changed\n", encoding="utf-8")
        ledger = self.home / "sediment.yaml"
        before = ledger.read_bytes()
        found = self.run_sed("gc")
        self.assertEqual(found.returncode, 1)
        self.assertIn("GC drift", found.stdout)
        self.assertIn("脚本已不是留下时的那一份", found.stdout)
        self.assertEqual(ledger.read_bytes(), before)
        checked = self.run_sed("check")
        self.assertEqual(checked.returncode, 1)
        self.assertIn("脚本已不是留下时的那一份", checked.stderr)
        recalled = self.run_sed("recall", "--scope", "库存", "--no-count")
        self.assertIn("不要把这条当成现行能力", recalled.stdout)
        again = self.run_sed(
            "transform", "--id", "S1", "--by", "wangwei794", "--repro", "ev/repro.log"
        )
        self.assertEqual(again.returncode, 2)
        self.assertIn("一次修改还不是演化", again.stderr)
        self.assertFalse((self.repo / "do.sh.ran").exists())
        write(self.repo / "ev" / "third.log", "third result\n")
        evolved = self.run_sed(
            "transform",
            "--id",
            "S1",
            "--by",
            "wangwei794",
            "--repro",
            "ev/repro.log",
            "--evidence",
            "ev/third.log",
        )
        self.assertEqual(evolved.returncode, 0, evolved.stderr)
        self.assertFalse((self.repo / "do.sh.ran").exists())
        passed = self.run_sed("check")
        self.assertEqual(passed.returncode, 0, passed.stderr)


if __name__ == "__main__":
    unittest.main()
