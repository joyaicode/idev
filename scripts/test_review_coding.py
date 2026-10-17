#!/usr/bin/env python3
r"""check_review_coding's refactor branch, table-driven.

The second Python unit test in this repo (test_signoff.py was the first),
same ground rules: unittest rather than pytest so the macOS system
interpreter (3.9.6) runs it with nothing installed.

What it locks: when review.md claims 重构/结构调整, the machine check
demands a guard it can name — R1-R6 noted, or a 护栏 line with a real value.
coding-tables.md §3.1 R1 makes the guard the admission condition for
wearing the refactor hat at all; §3.4 puts it in the出门 checklist. What it
deliberately does NOT judge: whether the named guard can actually run and
flip red/green. That is the human's semantic gate — structure-green is not
a semantic lock.

History: this branch shipped with no test and two holes. "护栏: 无" passed
because \S counts 无 as a value, and a bare "护栏:" matched through the
newline into the next bullet. Both are now FAIL. The selfcheck fixture
(selfcheck.sh "refactor without guard") covers the no-guard-line case
end-to-end; this file owns the field grammar.

    python3 scripts/test_review_coding.py          # or: -v for every row
"""
from __future__ import annotations

import io
import contextlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# check-feature.py has a dash in its name, which import cannot express.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "check_feature", Path(__file__).resolve().parent / "check-feature.py"
)
cf = importlib.util.module_from_spec(_spec)
sys.modules["check_feature"] = cf
_spec.loader.exec_module(cf)  # noqa: E402

# The five checks that must stay independent of the refactor claim: the
# refactor branch must not un-fail any of them, nor fail them itself.
BASE = """- 场景命中: 零命中
- 气味命中: 无（已扫）
- 纠正: 无
- 五轴: 正确性过；可读性过；架构过；安全过；性能过
- 栈指南: java8
- 增强扫描: 已跑 coding-scan + 五轴 + 栈指南
"""


def run_coding(extra: str) -> list:
    """check_review_coding on BASE + extra lines; returns the error list."""
    errors = []
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cf.check_review_coding("## 编码规范\n\n" + BASE + extra, errors)
    return errors


def refactor_errors(errors: list) -> list:
    return [e for e in errors if "refactor" in e]


class NotClaimed(unittest.TestCase):
    """重构: 无 must not trigger the guard demand at all."""

    def test_no_claim_no_guard_demand(self) -> None:
        self.assertEqual(refactor_errors(run_coding("- 重构: 无\n")), [])

    def test_guards_present_without_claim_pass(self) -> None:
        body = "- 重构: 无\n- 护栏: FooServiceTest\n- R 条件: R1–R6 均满足\n"
        self.assertEqual(refactor_errors(run_coding(body)), [])


class GuardGrammar(unittest.TestCase):
    """A claimed refactor needs a guard the reviewer can name."""

    def test_claim_with_nothing_fails(self) -> None:
        self.assertTrue(refactor_errors(run_coding("- 重构: 有\n")))

    def test_named_test_class_passes(self) -> None:
        body = "- 重构: 有（预备式）\n- 护栏: FooServiceTest\n"
        self.assertEqual(refactor_errors(run_coding(body)), [])

    def test_verify_case_named_passes(self) -> None:
        body = "- 重构: 有\n- 护栏: verify case boundary-03\n"
        self.assertEqual(refactor_errors(run_coding(body)), [])

    def test_guard_none_fails(self) -> None:
        """护栏: 无 is the admission condition failing, not a value.

        coding-tables.md §3.1 R1: 缺任一条 → 不准宣称在重构，先补条件。
        """
        errors = refactor_errors(run_coding("- 重构: 有\n- 护栏: 无\n"))
        self.assertEqual(len(errors), 1)
        self.assertIn("names no guard", errors[0])

    def test_guard_placeholder_words_fail(self) -> None:
        for word in ("暂无", "没有", "待补", "TODO", "None"):
            with self.subTest(word=word):
                self.assertTrue(
                    refactor_errors(run_coding("- 重构: 有\n- 护栏: %s\n" % word)),
                    "护栏: %s must not count as a guard" % word,
                )

    def test_guard_none_with_qualifier_fails(self) -> None:
        """无 followed by a clause that only restates the absence."""
        for val in ("无（已扫）", "无。", "无，只有手工核对"):
            with self.subTest(val=val):
                self.assertTrue(
                    refactor_errors(run_coding("- 重构: 有\n- 护栏: %s\n" % val)),
                    "护栏: %s must not count as a guard" % val,
                )

    def test_guard_none_as_prefix_of_real_name_passes(self) -> None:
        """无 starting a real guard name is a value, not a denial.

        The split: "无" + restatement fails; "无" as the first character of
        an identifier passes. The comma and the full stop are the seam —
        无缺陷回归测试 is a name, 无，手工核对 is a denial.
        """
        self.assertEqual(
            refactor_errors(run_coding("- 重构: 有\n- 护栏: 无缺陷回归测试\n")), []
        )

    def test_guard_empty_fails(self) -> None:
        r"""A bare 护栏: with nothing after the colon.

        The old search matched through the newline into the next bullet —
        the follow-on 五轴 line satisfied \s*\S and the empty guard passed.
        """
        self.assertTrue(refactor_errors(run_coding("- 重构: 有\n- 护栏:\n")))

    def test_guard_empty_does_not_eat_next_line(self) -> None:
        errors = refactor_errors(
            run_coding("- 重构: 有\n- 护栏:\n- R 条件: R1–R6 均满足\n")
        )
        # The R 条件 line still counts: the empty guard is not the only
        # guard named, but the empty line must not have swallowed it.
        self.assertEqual(errors, [])


class RConditionGrammar(unittest.TestCase):
    """R 条件 accepts the出门 wording (R1–R6, en or hyphen) or a bare R#."""

    def test_r_en_dash_all_passes(self) -> None:
        self.assertEqual(
            refactor_errors(run_coding("- 重构: 有\n- R 条件: R1–R6 均满足\n")), []
        )

    def test_r_hyphen_all_passes(self) -> None:
        self.assertEqual(
            refactor_errors(run_coding("- 重构: 有\n- R 条件: R1-R6 均满足\n")), []
        )

    def test_r_single_number_passes(self) -> None:
        # Machine check counts a named R# as "the condition was considered".
        # Whether all six truly hold is the human's call (§3.4), not \bR[1-6]\b.
        self.assertEqual(refactor_errors(run_coding("- 重构: 有\n- R 条件: R1\n")), [])

    def test_r_empty_fails(self) -> None:
        self.assertTrue(refactor_errors(run_coding("- 重构: 有\n- R 条件:\n")))

    def test_r_none_word_fails(self) -> None:
        """R 条件: 无 — the same swallow hazard as 护栏: 无.

        The value regex demands a real R-number (R[1-6]) or 满足 after the
        colon; 无 names nothing. (What it must not demand: that all six
        conditions actually hold — that judgement belongs to the reviewer,
        not to a regex. See test_r_single_number_passes.)
        """
        errors = refactor_errors(run_coding("- 重构: 有\n- R 条件: 无\n"))
        self.assertEqual(len(errors), 1)
        self.assertIn("needs R1-R6 or 护栏", errors[0])

    def test_r_none_word_with_guard_still_passes(self) -> None:
        body = "- 重构: 有\n- R 条件: 无\n- 护栏: FooServiceTest\n"
        self.assertEqual(refactor_errors(run_coding(body)), [])


class ClaimSynonyms(unittest.TestCase):
    """结构调整 is the same claim under another name (§3.5, one编号真源)."""

    def test_structure_change_claimed_fails_without_guard(self) -> None:
        self.assertTrue(refactor_errors(run_coding("- 结构调整: 有\n")))

    def test_structure_change_with_guard_passes(self) -> None:
        body = "- 结构调整: 有\n- 护栏: FooServiceTest\n"
        self.assertEqual(refactor_errors(run_coding(body)), [])

    def test_fullwidth_colon(self) -> None:
        body = "- 重构：有（预备式）\n- 护栏：FooServiceTest\n"
        self.assertEqual(refactor_errors(run_coding(body)), [])

    def test_ordered_list_marker(self) -> None:
        body = "1. 重构: 有\n2. 护栏: FooServiceTest\n"
        self.assertEqual(refactor_errors(run_coding(body)), [])


class Independence(unittest.TestCase):
    """The refactor branch must not touch the other five checks."""

    def test_claim_does_not_mask_missing_five_axes(self) -> None:
        # BASE minus the 五轴 line: the refactor claim, properly guarded,
        # must not make the missing axes check pass.
        body = BASE.replace(
            "- 五轴: 正确性过；可读性过；架构过；安全过；性能过\n", ""
        ) + "- 重构: 有\n- 护栏: FooServiceTest\n"
        errors = []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cf.check_review_coding("## 编码规范\n\n" + body, errors)
        self.assertTrue(any("五轴" in e for e in errors))

    def test_guard_alone_does_not_satisfy_missing_section(self) -> None:
        # No 编码规范 section at all: the refactor grammar never runs.
        errors = []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cf.check_review_coding("# R\n\n## 本轮允许改的路径\n", errors)
        self.assertTrue(any("missing 编码规范" in e for e in errors))


class FilledExamplePasses(unittest.TestCase):
    """The example block in review.example.md, filled in, must be green."""

    def test_filled_example(self) -> None:
        body = """- 场景命中: P1（第三次展开规则 → 静态工厂）
- 气味命中: C2（缺值省略）
- 纠正: `FooService.java` — 缺 platform 改立刻 400；提取 `requirePlatform`
- 重构: 有（预备式）
- 护栏: `FooServiceTest`
- R 条件: R1–R6 均满足
- 五轴: 正确性过；可读性命中已改；架构过；安全过；性能过
- 栈指南: java8
- 增强扫描: 已跑
"""
        errors = []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cf.check_review_coding("## 编码规范\n\n" + body, errors)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
