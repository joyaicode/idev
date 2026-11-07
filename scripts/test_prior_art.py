#!/usr/bin/env python3
"""既往: the confirmed prior art a delegation brief carries into a cold context.

An executor is a fresh context every time, so what the ticket already paid
to learn has to arrive with the brief. Both ledgers already have a gate —
a lesson is authoritative only after a reproduction and a named person, a
program is kept only after two different results and a named person — and
this line carries only rows that cleared it. The tests below are mostly
about what stays *out*: a candidate injected into a brief is how one local
mistake becomes a systematic one.
"""
from __future__ import annotations

import io
import contextlib
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
sys.path.insert(0, str(HERE))

import lessons  # noqa: E402
import prior_art  # noqa: E402
import sediment  # noqa: E402
import workflow  # noqa: E402


def lesson(lid: str, status: str, scope: str, uses: int = 0) -> str:
    return (
        f"  - id: {lid}\n"
        f"    status: {status}\n"
        f"    scope: {scope}\n"
        f"    symptom: 回写卡住\n"
        f"    evidence: ev/{lid}.log\n"
        f"    action: 先看位点\n"
        f"    outcome: 好了\n"
        f"    not_when: 位点在推进时\n"
        f"    uses: {uses}\n"
    )


def program(sid: str, status: str, scope: str) -> str:
    return (
        f"  - id: {sid}\n"
        f"    status: {status}\n"
        f"    form: program\n"
        f"    trust: reviewed\n"
        f"    scope: {scope}\n"
        f"    claim: 先跑这个\n"
        f"    not_when: 没有位点时\n"
        f"    script: scripts/check.sh\n"
    )


class PriorArt(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.lessons = self.root / "lessons.yaml"
        self.sediment = self.root / "sediment.yaml"

    def write_lessons(self, *rows: str) -> None:
        self.lessons.write_text("schema_version: 1\nlessons:\n" + "".join(rows), encoding="utf-8")

    def write_sediment(self, *rows: str) -> None:
        self.sediment.write_text("schema_version: 1\nentries:\n" + "".join(rows), encoding="utf-8")

    # --- what gets in -------------------------------------------------

    def test_authoritative_lesson_in_scope_is_recalled(self) -> None:
        self.write_lessons(lesson("L1", "authoritative", "库存回写"))
        found = lessons.prior_art([self.lessons], ["库存回写"])
        self.assertEqual([x["id"] for x in found], ["L1"])

    def test_kept_program_in_scope_is_recalled(self) -> None:
        self.write_sediment(program("S1", "kept", "库存回写"))
        found = sediment.prior_art([self.sediment], ["库存回写"])
        self.assertEqual([x["id"] for x in found], ["S1"])

    def test_scope_matches_the_symptom_too(self) -> None:
        self.write_lessons(lesson("L1", "authoritative", "别的域"))
        self.assertTrue(lessons.prior_art([self.lessons], ["回写卡住"]))

    def test_most_used_first(self) -> None:
        self.write_lessons(
            lesson("L1", "authoritative", "库存", uses=1),
            lesson("L2", "authoritative", "库存", uses=9),
        )
        found = lessons.prior_art([self.lessons], ["库存"])
        self.assertEqual([x["id"] for x in found], ["L2", "L1"])

    # --- what stays out -----------------------------------------------

    def test_candidate_lesson_never_reaches_a_brief(self) -> None:
        """recall prints candidates to a reader who was warned. A brief is not that reader."""
        self.write_lessons(lesson("L1", "candidate", "库存回写"))
        self.assertEqual(lessons.prior_art([self.lessons], ["库存回写"]), [])

    def test_candidate_program_never_reaches_a_brief(self) -> None:
        self.write_sediment(program("S1", "candidate", "库存回写"))
        self.assertEqual(sediment.prior_art([self.sediment], ["库存回写"]), [])

    def test_retired_stays_out(self) -> None:
        self.write_lessons(lesson("L1", "retired", "库存回写"))
        self.assertEqual(lessons.prior_art([self.lessons], ["库存回写"]), [])

    def test_out_of_scope_stays_out(self) -> None:
        self.write_lessons(lesson("L1", "authoritative", "结算"))
        self.assertEqual(lessons.prior_art([self.lessons], ["库存回写"]), [])

    def test_top_caps_the_recall(self) -> None:
        self.write_lessons(*[lesson(f"L{n}", "authoritative", "库存") for n in range(1, 8)])
        self.assertEqual(len(lessons.prior_art([self.lessons], ["库存"], top=3)), 3)

    def test_recall_writes_nothing(self) -> None:
        """An automatic injection is not the lesson having helped, so uses does not move."""
        self.write_lessons(lesson("L1", "authoritative", "库存", uses=4))
        before = self.lessons.read_text(encoding="utf-8")
        lessons.prior_art([self.lessons], ["库存"])
        self.assertEqual(self.lessons.read_text(encoding="utf-8"), before)

    def test_missing_ledger_is_an_empty_recall(self) -> None:
        self.assertEqual(lessons.prior_art([self.root / "nope.yaml"], ["库存"]), [])
        self.assertEqual(sediment.prior_art([self.root / "nope.yaml"], ["库存"]), [])

    def test_same_id_in_two_ledgers_is_listed_once(self) -> None:
        self.write_lessons(lesson("L1", "authoritative", "库存"))
        other = self.root / "kernel.yaml"
        other.write_text("schema_version: 1\nlessons:\n" + lesson("L1", "authoritative", "库存"),
                         encoding="utf-8")
        self.assertEqual(len(lessons.prior_art([self.lessons, other], ["库存"])), 1)

    # --- the brief ----------------------------------------------------

    def test_scopes_come_from_the_feature_label_and_write_set(self) -> None:
        scopes = prior_art.scopes(
            "ticket-9",
            label="回写",
            scope="A",
            writes=["src/app.py", "docs/x.md"],
            shard="web/one.ts",
        )
        self.assertEqual(scopes, ["ticket-9", "回写", "A", "src", "docs", "web"])

    def test_a_broken_ledger_does_not_break_the_brief(self) -> None:
        """Composing a brief must not be the thing that fails over an optional line."""
        ticket = self.root / ".idev" / "task" / "demo"
        ticket.mkdir(parents=True)
        (ticket / "lessons.yaml").write_text("lessons: [[[\n", encoding="utf-8")
        brief = {"writes": ["src/app.py"]}
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            lines = workflow._prior_art(brief, {"label": ""}, ticket, self.root, "demo")
        self.assertEqual(lines, [])
        self.assertEqual(err.getvalue(), "")

    def test_the_brief_says_prior_art_is_not_an_answer(self) -> None:
        run = {"feature": "demo"}
        step = {"id": "c", "kind": "deliver.code_pass", "with": {}}
        brief = {"ticket_home": "t", "repo": "r", "stage": "code", "risk_tier": "P1",
                 "must_read": "m", "idev_root": "i", "with": {},
                 "prior_art": ["L1 [经验] 现象 x | 动作 y | 不适用于 z | 依据 ev/1.log"]}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            workflow.print_brief(run, step, "idev-coder", 1, brief)
        text = out.getvalue()
        self.assertIn("既往: L1 [经验]", text)
        self.assertIn("这是约束不是答案", text)

    def test_no_prior_art_prints_no_line_at_all(self) -> None:
        run = {"feature": "demo"}
        step = {"id": "c", "kind": "deliver.code_pass", "with": {}}
        brief = {"ticket_home": "t", "repo": "r", "stage": "code", "risk_tier": "P1",
                 "must_read": "m", "idev_root": "i", "with": {}}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            workflow.print_brief(run, step, "idev-coder", 1, brief)
        self.assertNotIn("既往", out.getvalue())


if __name__ == "__main__":
    unittest.main()
