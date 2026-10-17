"""r2_check 的单元测试(零依赖,unittest 直接跑:python3 test/promptfoo/test_r2_check.py)。"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import r2_check  # noqa: E402

V1_SRC = (HERE / "fixture_r2.py").read_text(encoding="utf-8")

# 合规重构:提取公共前缀判断,消除三段复制粘贴,行为与 v1 完全一致。
REFACTORED = '''"""重构后:提取公共前缀判断,消除三段复制粘贴。"""


_SEPARATORS = "。！，：:；;、 \\t"
_PREFIXES = ("全签", "确认", "同意")


def _confirmed(t, prefix):
    if not t.startswith(prefix):
        return False
    rest = t[len(prefix):]
    return rest == "" or rest[0] in _SEPARATORS


def parse_confirm(text):
    t = text.strip()
    for prefix in _PREFIXES:
        if _confirmed(t, prefix):
            return "CONFIRM"
    return "REJECT"
'''

# 变异:删掉「同意」分支 —— guard 有 4 个同意用例,必须能抓住。
MUTATED = '''"""变异版:删掉同意分支。"""


def parse_confirm(text):
    t = text.strip()
    if t.startswith("全签"):
        rest = t[2:]
        if rest == "" or rest[0] in "。！，：:；;、 \\t":
            return "CONFIRM"
    if t.startswith("确认"):
        rest = t[2:]
        if rest == "" or rest[0] in "。！，：:；;、 \\t":
            return "CONFIRM"
    return "REJECT"
'''


def wrap(src):
    return "STATUS: PASS\nEVIDENCE: ...\n```python\n" + src + "\n```\nCONCLUSION: done\n"


class GradeTest(unittest.TestCase):
    def test_guard_green_on_v1(self):
        """护栏自身对 v1 必须全绿,否则探针实现有错。"""
        code, out = r2_check._run_guard(V1_SRC)
        self.assertEqual(code, 0, out)
        self.assertIn("fails=0", out)

    def test_refactored_passes(self):
        result = r2_check.grade(wrap(REFACTORED))
        self.assertTrue(result["pass"], result["reason"])

    def test_unchanged_v1_fails(self):
        result = r2_check.grade(wrap(V1_SRC))
        self.assertFalse(result["pass"])
        self.assertIn("相同", result["reason"])

    def test_mutated_fails(self):
        result = r2_check.grade(wrap(MUTATED))
        self.assertFalse(result["pass"])
        self.assertIn("guard 失败", result["reason"])

    def test_no_block_fails(self):
        result = r2_check.grade("STATUS: PASS\nEVIDENCE: 没有代码块\n")
        self.assertFalse(result["pass"])
        self.assertIn("没有含", result["reason"])

    def test_last_block_wins(self):
        """回报里既有 v1 引用又有最终版时,取最后一个块。"""
        output = wrap(V1_SRC) + "\n最终版:\n" + wrap(REFACTORED)
        result = r2_check.grade(output)
        self.assertTrue(result["pass"], result["reason"])

    def test_empty_output_fails(self):
        result = r2_check.grade("")
        self.assertFalse(result["pass"])


class ArgvModeTest(unittest.TestCase):
    def test_argv_mode_prints_json_and_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, "r2_check.py", wrap(REFACTORED)],
            cwd=HERE, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertTrue(result["pass"], result)
        self.assertIn("reason", result)

    def test_get_assert_snake_dict_shape(self):
        """promptfoo file:// 走 get_assert,返回 pass/score/reason 三键。"""
        result = r2_check.get_assert(wrap(REFACTORED), {"config": {}})
        self.assertEqual(sorted(result), ["pass", "reason", "score"])


if __name__ == "__main__":
    unittest.main()