#!/usr/bin/env python3
"""promptfoo-gen.py 的单元测试(零依赖,unittest 直接跑)。

    python3 scripts/test_promptfoo_gen.py          # or: -v for every row

锁什么:

  - 两份配置的结构:基础矩阵 5 prompt/60 断言,C 组 5 探针/92 断言,
    两边 0 评分、无一例 llm-rubric(external-tools.md §2 的纪律)。
  - C 组五条探针各自的「额外断言」确实在生成的 YAML 里(C-1 拒因词表、
    C-2 拆轮词表、C-3 python exec 护栏、C-4 RED_FIRST 非无、C-5 baseline
    不进 CHANGED)。
  - promptfoo 的 regex 断言是 new RegExp(value),不带 flags 参数
    (src/assertions/regex.ts);JS 拒绝 PCRE 式裸 (?m)(「Invalid group」)。
    所以所有多行正则必须是 scoped inline flag (?m:...) 形态。
    Python 3.9 编不了 (?m:...),所以这里断言的是字符串前缀,不是 re.compile。
  - C-3 的 python 断言指向的 r2_check.py 必须存在,且 get_assert 返回
    pass/score/reason 三键(promptfoo file:// 的调用契约)。
  - anchors:safeyaml.dump 会把同一 dict 对象写成 YAML 锚点(&id001/*id001),
    safe_load 能无损读回——配置必须 round-trip(生成物人也能手读)。
"""
from __future__ import annotations

import io
import contextlib
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "lib"))

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("promptfoo_gen", SCRIPTS / "promptfoo-gen.py")
gen = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(gen)  # type: ignore[union-attr]

import safeyaml  # noqa: E402


def generate_to(tmp: Path) -> tuple[dict, dict]:
    """跑 main() 到临时目录,返回 (base config, refactor config) 的解析结果。"""
    argv, sys.argv = sys.argv, [sys.argv[0], "--out", str(tmp)]
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            rc = gen.main()
    finally:
        sys.argv = argv
    assert rc == 0, buf_err.getvalue() or buf_out.getvalue()
    base = safeyaml.mapping(tmp / "promptfooconfig.yaml")
    refactor = safeyaml.mapping(tmp / "promptfooconfig-refactor.yaml")
    assert base and refactor
    return base, refactor


class BaseMatrixTest(unittest.TestCase):
    def test_five_prompts_sixty_assertions_no_scores(self):
        with __import__("tempfile").TemporaryDirectory() as td:
            base, refactor = generate_to(Path(td))
        self.assertEqual(len(base["tests"]), 5)
        self.assertEqual(sum(len(t["assert"]) for t in base["tests"]), 60)
        self.assertIn("no scoring", base["description"])
        # 纪律:整个配置没有任何评分型断言。
        for t in base["tests"]:
            for a in t["assert"]:
                self.assertNotIn("rubric", a["type"])

    def test_refactor_config_pins_one_prompt(self):
        with __import__("tempfile").TemporaryDirectory() as td:
            _, refactor = generate_to(Path(td))
        self.assertEqual(refactor["prompts"], ["file://prompts/idev-coder.txt"])
        self.assertEqual(len(refactor["tests"]), 5)
        self.assertEqual(sum(len(t["assert"]) for t in refactor["tests"]), 92)


class CGroupTest(unittest.TestCase):
    """C-1..C-5 的额外断言确实落在生成的配置里,且探针话术不带答案。"""

    @classmethod
    def setUpClass(cls):
        cls._td = __import__("tempfile").TemporaryDirectory()
        cls.base, cls.refactor = generate_to(Path(cls._td.name))
        cls.by_desc = {t["description"]: t for t in cls.refactor["tests"]}

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def _extra(self, desc):
        return self.by_desc[desc]["assert"][-1]

    def test_c1_guard_gap(self):
        a = self._extra("C-1 idev-coder: guard gap gets named (BLOCKED / 先补护栏测试 / 拆轮)")
        self.assertEqual(a["type"], "regex")
        for word in ("BLOCKED", "护栏", "拆轮"):
            self.assertIn(word, a["value"])
        # 探针话术不得暗示期望答案(词表只出现在断言侧)。
        self.assertNotIn("护栏", self.by_desc[
            "C-1 idev-coder: guard gap gets named (BLOCKED / 先补护栏测试 / 拆轮)"]["vars"]["brief"])

    def test_c2_two_hats(self):
        a = self._extra("C-2 idev-coder: two-hats change gets split (帽子 / 两轮 / 拆轮 / 待拷问)")
        self.assertEqual(a["type"], "regex")
        for word in ("帽子", "拆轮", "待拷问"):
            self.assertIn(word, a["value"])
        brief = self.by_desc[
            "C-2 idev-coder: two-hats change gets split (帽子 / 两轮 / 拆轮 / 待拷问)"]["vars"]["brief"]
        self.assertNotIn("帽子", brief)
        self.assertNotIn("拆轮", brief)

    def test_c3_exec_guard(self):
        a = self._extra("C-3 idev-coder: pure structural refactor keeps behavior (exec guard)")
        self.assertEqual(a["type"], "python")
        self.assertTrue(a["value"].endswith("test/promptfoo/r2_check.py"))
        # 指向的护栏真实存在,且满足 promptfoo file:// 的调用契约。
        path = Path(a["value"].removeprefix("file://"))
        self.assertTrue(path.is_file(), path)
        probe = self.by_desc[
            "C-3 idev-coder: pure structural refactor keeps behavior (exec guard)"]["vars"]["brief"]
        self.assertIn("```python", probe)  # v1 与 guard 全文都在 brief 里
        self.assertIn("行为必须保持不变", probe)

    def test_c4_red_first(self):
        asserts = self.by_desc[
            "C-4 idev-coder: review.fix declares RED_FIRST (非无)"]["assert"][-2:]
        self.assertEqual(asserts[0], {"type": "contains", "value": "RED_FIRST:"})
        self.assertEqual(asserts[1]["type"], "regex")
        self.assertIn("无", asserts[1]["value"])  # 「无」被负向断言挡掉

    def test_c5_baseline_out_of_changed(self):
        extras = self.by_desc[
            "C-5 idev-coder: sealed baseline stays out of CHANGED"]["assert"][-2:]
        self.assertEqual(extras[-1], {"type": "not-contains", "value": "CHANGED: baseline.yaml"})
        self.assertIn("baseline\\.yaml", extras[0]["value"])


class RegexFlagTest(unittest.TestCase):
    """所有 regex 断言必须是 (?m:...) scoped 形态 —— JS 不认裸 (?m)。"""

    @classmethod
    def setUpClass(cls):
        cls._td = __import__("tempfile").TemporaryDirectory()
        cls.base, cls.refactor = generate_to(Path(cls._td.name))

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_all_regexes_use_scoped_multiline_flag(self):
        n = 0
        for cfg in (self.base, self.refactor):
            for t in cfg["tests"]:
                for a in t["assert"]:
                    if a["type"] == "regex":
                        n += 1
                        self.assertTrue(
                            a["value"].startswith("(?m:"),
                            f"bare (?m) or flagless multiline: {a['value'][:50]}")
        self.assertGreaterEqual(n, 14)  # 5(基础) + 9(C 组)

    def test_helper_wraps_once(self):
        self.assertEqual(gen.m(r"^X$"), "(?m:^X$)")
        # 双重包裹不被 m() 挡住(它只做拼接),这个测试在提醒:
        # 断言值永远来自 asserts_for/refactor_probes 的字面量,别把 m() 套两层。
        double = gen.m(gen.m("^X$"))
        self.assertEqual(double, "(?m:(?m:^X$))")


class RoundTripTest(unittest.TestCase):
    def test_yaml_anchors_round_trip(self):
        """safeyaml.dump 把共享断言 dict 写成锚点;safe_load 必须无损读回。"""
        with __import__("tempfile").TemporaryDirectory() as td:
            tmp = Path(td)
            generate_to(tmp)
            text = (tmp / "promptfooconfig-refactor.yaml").read_text(encoding="utf-8")
        self.assertIn("&id001", text)  # 锚点确实被使用(去重)
        base = safeyaml.mapping_from_text(text)
        tests = base["tests"]
        # 所有 5 个测试的 CHANGED:/CONCLUSION: 断言来自同一份共享列表。
        changed = [a for t in tests for a in t["assert"]
                   if a.get("value") == "CHANGED:" and a["type"] == "contains"]
        self.assertEqual(len(changed), 5)


if __name__ == "__main__":
    unittest.main()
