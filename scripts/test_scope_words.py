#!/usr/bin/env python3
"""scope-words: the sweep catches what it claims to catch.

Absorbed from joy-dev's check-docs-governance --scope-words: before a
one-off problem is promoted into a general rule, the draft gets swept
for universal quantifiers and each hit is narrowed or justified. The
sweep is only worth its seat if it (a) finds every word in a hostile
draft, (b) stays quiet on a clean one, and (c) --check flips the exit
code so a pipeline can rely on it.

    python3 scripts/test_scope_words.py
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "scope-words.py"


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=30,
    )


class ScopeWords(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="idev-scope-words-")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, body: str) -> Path:
        path = Path(self._tmp.name) / "draft.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_every_word_in_the_list_is_caught(self) -> None:
        # Normative words count anywhere; quantifiers need an imperative
        # marker on the same line, so their probe lines carry one.
        probes = {
            "只有": "只有本阶段可写。",
            "一律": "一律拒绝。",
            "必须": "必须核对。",
            "不得": "不得跳过。",
            "全部": "全部都要核对。",
            "所有": "所有回报都需附证据。",
            "均": "均应留痕。",
            "仅": "仅此一处不改，其余都要过。",
            "不再": "不再新增门禁，新规则需先过提案。",
            "无一例外": "无一例外，全部不准绕过。",
        }
        path = self._write("\n".join(probes.values()))
        proc = run([str(path)])
        for word in probes:
            self.assertIn(word, proc.stdout, "missed %r" % word)

    def test_quantifier_in_statistical_prose_is_not_a_hit(self) -> None:
        # The experiment that split the vocabulary: on a real proposal 3 of
        # 3 hits were evidence statements ("8 个脚本全部直读 run.yaml").
        # Quantifiers without an imperative marker are prose, not scope.
        path = self._write("8 个脚本全部直读 run.yaml，无一读 SQLite。\n其余均未改动。\n")
        proc = run([str(path), "--check"])
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_clean_draft_is_quiet_and_zero(self) -> None:
        path = self._write("这是一个普通段落，没有范围词。\n另一行也只是叙述。\n")
        proc = run([str(path), "--check"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("只有", proc.stdout)

    def test_check_flips_the_exit_code_on_a_hit(self) -> None:
        path = self._write("必须全做，不得推迟。\n")
        self.assertEqual(run([str(path)]).returncode, 0, "plain listing never fails")
        self.assertEqual(run([str(path), "--check"]).returncode, 1,
                         "--check is the pipeline lane; a hit must be loud")

    def test_unreadable_file_is_a_warn_not_a_crash(self) -> None:
        missing = Path(self._tmp.name) / "nope.md"
        proc = run([str(missing)])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("WARN", proc.stderr)


if __name__ == "__main__":
    unittest.main()
