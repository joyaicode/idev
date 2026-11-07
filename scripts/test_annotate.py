#!/usr/bin/env python3
"""标注循环: the plan document as shared mutable state between a person and an agent.

A person reviewing a plan has ten things to change. Describing them in
chat loses some, distorts others, and leaves nothing for the next round
to check against. Writing them into the document itself keeps all three.

The tests below mostly guard the third criterion — an annotation that is
in the ledger and in neither state in the file. The first two are work
not done; that one is a person's objection being quietly eaten by a
rewrite, which is worse than having no mechanism at all, because the
person believes they raised it.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))

import safeyaml  # noqa: E402

SCRIPT = HERE / "annotate.py"
CHECK_FEATURE = HERE / "check-feature.py"


class Annotate(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve() / "one"
        self.ticket = self.repo / ".idev" / "task" / "demo"
        self.ticket.mkdir(parents=True)
        self.arch = self.ticket / "arch.yaml"
        self.design = self.ticket / "design.md"
        self.arch.write_text("approach: 加一层缓存\nnon_approach: 不改 DAO\n", encoding="utf-8")
        self.design.write_text("# 设计\n正文\n", encoding="utf-8")

    def run_tool(self, *args: str) -> tuple[int, str]:
        done = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo),
                               *args, "--feature", "demo"],
                              capture_output=True, text=True, timeout=60)
        return done.returncode, done.stdout + done.stderr

    def annotate_yaml(self, text: str = "这里不该加缓存") -> None:
        self.arch.write_text(f"approach: 加一层缓存\n# @me: {text}\nnon_approach: 不改 DAO\n",
                             encoding="utf-8")

    def annotate_md(self, text: str = "visibility 要放在 list 上") -> None:
        self.design.write_text(f"# 设计\n<!-- @me: {text} -->\n正文\n", encoding="utf-8")

    def settle_yaml(self, how: str = "删掉缓存那一节") -> tuple[int, str]:
        return self.run_tool("settle", "--at", ".idev/task/demo/arch.yaml:2", "--how", how)

    def mark_done(self, path: Path) -> None:
        path.write_text(path.read_text(encoding="utf-8").replace("@me:", "@done:"), encoding="utf-8")

    def notes(self) -> list[dict]:
        data = safeyaml.mapping(self.ticket / "annotations.yaml")
        return list(data["notes"])

    # --- scan ---------------------------------------------------------

    def test_a_clean_ticket_scans_green(self) -> None:
        code, out = self.run_tool("scan")
        self.assertEqual(code, 0, out)

    def test_both_comment_syntaxes_are_found(self) -> None:
        self.annotate_yaml()
        self.annotate_md()
        code, out = self.run_tool("scan")
        self.assertEqual(code, 1)
        self.assertIn("这里不该加缓存", out)
        self.assertIn("visibility 要放在 list 上", out)

    def test_scan_prints_the_settle_command(self) -> None:
        self.annotate_yaml()
        _, out = self.run_tool("scan")
        self.assertIn("--at .idev/task/demo/arch.yaml:2", out)

    # --- settle -------------------------------------------------------

    def test_settle_records_the_text_not_a_summary_of_it(self) -> None:
        self.annotate_yaml()
        code, out = self.settle_yaml()
        self.assertEqual(code, 0, out)
        note = self.notes()[0]
        self.assertEqual(note["text"], "这里不该加缓存")
        self.assertEqual(note["how"], "删掉缓存那一节")

    def test_settle_refuses_an_empty_how(self) -> None:
        """A settle with no account of what was done is the same as no settle."""
        self.annotate_yaml()
        code, out = self.run_tool("settle", "--at", ".idev/task/demo/arch.yaml:2", "--how", "   ")
        self.assertEqual(code, 2)
        self.assertIn("没写怎么处置的", out)

    def test_settle_refuses_a_line_with_no_annotation(self) -> None:
        self.annotate_yaml()
        code, out = self.run_tool("settle", "--at", ".idev/task/demo/arch.yaml:1", "--how", "x")
        self.assertEqual(code, 2)
        self.assertIn("上没有标注", out)

    def test_settling_twice_is_not_two_notes(self) -> None:
        self.annotate_yaml()
        self.settle_yaml()
        self.settle_yaml("又说了一遍")
        self.assertEqual(len(self.notes()), 1)

    # --- the three criteria -------------------------------------------

    def test_an_open_annotation_fails(self) -> None:
        self.annotate_yaml()
        code, out = self.run_tool("check")
        self.assertEqual(code, 1)
        self.assertIn("标注未处置", out)
        self.assertIn("不要写 sealed / accepted", out)

    def test_done_without_a_record_fails(self) -> None:
        """Marking it handled without saying how is a claim, not a record."""
        self.annotate_yaml()
        self.mark_done(self.arch)
        code, out = self.run_tool("check")
        self.assertEqual(code, 1)
        self.assertIn("标注处置无留痕", out)

    def test_an_erased_annotation_fails(self) -> None:
        self.annotate_yaml()
        self.settle_yaml()
        self.arch.write_text("approach: 直读\nnon_approach: 不改 DAO\n", encoding="utf-8")
        code, out = self.run_tool("check")
        self.assertEqual(code, 1)
        self.assertIn("标注被抹掉", out)

    def test_rewording_the_annotation_counts_as_erasing_it(self) -> None:
        """The text is the identity. Edit it and the ledger is about something else."""
        self.annotate_yaml()
        self.settle_yaml()
        self.arch.write_text("approach: 直读\n# @done: 这里可以加缓存\n", encoding="utf-8")
        _, out = self.run_tool("check")
        self.assertIn("标注被抹掉", out)
        self.assertIn("标注处置无留痕", out)

    def test_settled_and_marked_is_green(self) -> None:
        self.annotate_yaml()
        self.settle_yaml()
        self.mark_done(self.arch)
        code, out = self.run_tool("check")
        self.assertEqual(code, 0, out)
        self.assertIn("不说明方案对齐了", out)

    def test_whitespace_does_not_change_the_identity(self) -> None:
        self.annotate_yaml()
        self.settle_yaml()
        self.arch.write_text("approach: 直读\n#  @done:  这里不该加缓存  \n", encoding="utf-8")
        code, out = self.run_tool("check")
        self.assertEqual(code, 0, out)

    # --- the gate -----------------------------------------------------

    def test_check_feature_refuses_the_stage_while_an_annotation_is_open(self) -> None:
        self.annotate_yaml()
        done = subprocess.run(
            [sys.executable, str(CHECK_FEATURE), "--repo", str(self.repo),
             "--feature", "demo", "--stage", "arch"],
            capture_output=True, text=True, timeout=120,
        )
        self.assertIn("标注未处置", done.stdout + done.stderr)
        self.assertEqual(done.returncode, 1)

    def test_check_feature_is_quiet_when_there_is_nothing_to_settle(self) -> None:
        done = subprocess.run(
            [sys.executable, str(CHECK_FEATURE), "--repo", str(self.repo),
             "--feature", "demo", "--stage", "arch"],
            capture_output=True, text=True, timeout=120,
        )
        out = done.stdout + done.stderr
        self.assertIn("annotations settled and recorded", out)
        self.assertNotIn("标注", out)


if __name__ == "__main__":
    unittest.main()
