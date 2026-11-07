#!/usr/bin/env python3
"""A low-value stop is corrected from the rule already written.

    python3 scripts/test_process_eval.py
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = HERE / "process-eval.py"

spec = importlib.util.spec_from_file_location("process_eval", SCRIPT)
pe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe)


TRACE = """schema_version: 2
feature: {feature}
intent: "往下"
invoke:
  trigger: "{trigger}"
  how: continuation
route:
  scenario: S2
stop: "{stop}"
next: ""
calls:
  - kind: script
    name: check-feature.sh
"""


def write_trace(directory: Path, name: str, trigger: str, stop: str, feature: str = "demo") -> None:
    directory.joinpath(name).write_text(
        TRACE.format(feature=feature, trigger=trigger, stop=stop),
        encoding="utf-8",
    )


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, check=False,
    )


class Stop(unittest.TestCase):
    def test_rubber_stamp_and_nudge_are_corrected(self):
        asked = run("stop", "--stop", "请确认实现审核")
        self.assertEqual(asked.returncode, 0, asked.stderr)
        self.assertIn("now=CORRECT", asked.stdout)
        self.assertIn("id=ask-known", asked.stdout)
        self.assertIn("不问人确认", asked.stdout)

        nudge = run("stop", "--quote", "验收", "--stop", "验收没有写入")
        self.assertIn("id=rubber-proceed", nudge.stdout)
        self.assertIn("不记 stop", nudge.stdout)
        self.assertNotIn("later=PROPOSE", nudge.stdout)

    def test_real_holds_and_decision_gates_stay_asked(self):
        cases = {
            ("--stop", "实现审核有矛盾"): "id=real-hold",
            ("--quote", "打开基线"): "id=named",
            ("--quote", "解除密封"): "id=real-hold",
            ("--quote", "不要继续"): "id=reply",
            ("--quote", "把实现审核的失败项改到通过"): "id=work",
        }
        for args, marker in cases.items():
            with self.subTest(args=args):
                done = run("stop", *args)
                self.assertIn("now=ASK", done.stdout)
                self.assertIn(marker, done.stdout)
                self.assertNotIn("now=CORRECT", done.stdout)

        gated = run("stop", "--decision", "--quote", "确认")
        self.assertIn("id=decision-gate", gated.stdout)
        self.assertIn("now=ASK", gated.stdout)
        leave = run("stop", "--decision", "--quote", "验收")
        self.assertIn("id=leave-decision", leave.stdout)
        self.assertIn("决策保持开着", leave.stdout)
        stamped = run("stop", "--decision", "--stop", "请确认实现审核")
        self.assertIn("now=ASK", stamped.stdout)
        signal = run("stop", "--stop", "请确认实现审核", "--signals", "frontier")
        self.assertIn("id=real-hold", signal.stdout)

    def test_empty_is_not_a_stop(self):
        done = run("stop")
        self.assertIn("now=KEEP", done.stdout)
        self.assertIn("没有要判断的停问", done.stdout)


class Scan(unittest.TestCase):
    def test_repeated_upstream_stop_proposes_and_does_not_edit_skill(self):
        table = pe.load_scaffolds(ROOT / "references" / "scaffolds.yaml")
        count = int(table["stop-on-nudge"]["min_fires"])
        skill = (ROOT / "SKILL.md").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for index in range(count):
                write_trace(directory, "p%02da.yaml" % index, "实现这个功能", "请看一下")
                write_trace(directory, "p%02db.yaml" % index, "继续", "")
            out = directory / "out"
            first = run("scan", "--traces", tmp, "--window", "50", "--propose", "--out", str(out))
            self.assertIn("later=PROPOSE", first.stdout)
            self.assertIn("id=stop-on-nudge", first.stdout)
            self.assertIn("scaffold_idle=1", first.stdout)
            self.assertIn("不改 Skill", first.stdout)
            draft = next(out.glob("*-process-eval.md"))
            body = draft.read_text(encoding="utf-8")
            self.assertIn("status: draft", body)
            self.assertIn("accept: later", body)
            self.assertIn("不改 SKILL", body)
            self.assertNotIn("/Users", body)
            second = run("scan", "--traces", tmp, "--propose", "--out", str(out))
            self.assertIn("PROPOSE open", second.stdout)
            self.assertEqual(len(list(out.glob("*-process-eval.md"))), 1)
        self.assertEqual(skill, (ROOT / "SKILL.md").read_bytes())

    def test_one_event_and_a_missed_check_do_not_retire_the_scaffold(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_trace(directory, "a.yaml", "实现这个功能", "请看一下")
            write_trace(directory, "b.yaml", "继续", "")
            once = run("scan", "--traces", tmp)
            self.assertNotIn("later=PROPOSE", once.stdout)
            self.assertIn("unproven=stop-on-nudge", once.stdout)

            write_trace(directory, "c.yaml", "验收", "等一下")
            write_trace(directory, "d.yaml", "验收", "等一下")
            bad = run("scan", "--traces", tmp)
            self.assertIn("id=rubber-proceed", bad.stdout)
            self.assertIn("later=PROPOSE", bad.stdout)
            self.assertIn("id=stop-on-nudge", bad.stdout)
            self.assertIn("now=KEEP", bad.stdout)

    def test_except_drops_the_draft_window(self):
        table = pe.load_scaffolds(ROOT / "references" / "scaffolds.yaml")
        count = int(table["stop-on-nudge"]["min_fires"])
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            names = []
            for index in range(count):
                go = "p%02db.yaml" % index
                write_trace(directory, "p%02da.yaml" % index, "实现这个功能", "请看一下")
                write_trace(directory, go, "继续", "")
                names.append(go)
            skip = directory / "except.txt"
            skip.write_text("\n".join(names), encoding="utf-8")
            done = run("scan", "--traces", tmp, "--except", str(skip), "--propose", "--out", str(directory / "out"))
            self.assertNotIn("later=PROPOSE", done.stdout)
            self.assertIn("PROPOSE no", done.stdout)

    def test_replay_narrows_only_when_the_failure_is_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            delegations = Path(tmp) / "delegations"
            delegations.mkdir()
            traces = Path(tmp) / "traces"
            traces.mkdir()
            for index, prior in enumerate(("测试失败了", "断言不一致")):
                delegations.joinpath("r%d.yaml" % index).write_text(
                    "attempt: 2\noutcome: PASS\nbrief:\n  prior_failure: \"%s\"\n" % prior,
                    encoding="utf-8",
                )
            idle = run("scan", "--traces", str(traces), "--delegations", str(delegations))
            self.assertIn("id=context-replay", idle.stdout)
            self.assertIn("later=PROPOSE", idle.stdout)
            delegations.joinpath("r2.yaml").write_text(
                "attempt: 2\noutcome: FAIL\nbrief:\n  prior_failure: \"没读 coding.md\"\n",
                encoding="utf-8",
            )
            kept = run("scan", "--traces", str(traces), "--delegations", str(delegations))
            self.assertIn("now=KEEP", kept.stdout)
            self.assertNotIn("later=PROPOSE", kept.stdout)

    def test_missing_traces_are_unproven(self):
        done = run("scan", "--traces", "/tmp/idev-process-eval-missing")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("unproven=no-traces", done.stdout)

    def test_block_scalar_stop_is_read(self):
        text = "feature: demo\ninvoke:\n  trigger: \"实现\"\nstop: |\n  请确认实现审核\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.yaml"
            path.write_text(text, encoding="utf-8")
            row = pe.read_trace(path)
        self.assertEqual(row["trigger"], "实现")
        self.assertIn("请确认实现审核", row["stop"])
        self.assertTrue(pe.ask_known(row["stop"]))


class Contract(unittest.TestCase):
    def test_phrases_stay_in_the_authority_pages(self):
        page = (ROOT / "references" / "process-eval.md").read_text(encoding="utf-8")
        signoff = (ROOT / "references" / "chat-confirm-signoff.md").read_text(encoding="utf-8")
        for phrase in pe.NON_STOPS:
            self.assertIn(phrase, page)
        for phrase in ("审查签收", "实现审核", "测试结果确认", "文档定稿"):
            self.assertIn(phrase, signoff)
        self.assertIn("不自动改 Skill", page)
        self.assertIn("accept: later", page)


if __name__ == "__main__":
    unittest.main()
