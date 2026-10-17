"""C-3「纯结构重构不改行为」的 promptfoo python 断言。

两种调用方式(promptfoo file:// 默认走第 1 种):
  1) get_assert(output, context) -> GradingResult dict
  2) argv 兼容:python3 r2_check.py <output> [context.json] -> stdout 打印 JSON,恒退出 0

判定流程:
  1) 从 agent 回报提取最后一个含 def parse_confirm 的 ```python 代码块(重构版 v2);
  2) v2 与仓内 v1(test/promptfoo/fixture_r2.py)规范化后不得相同(要求真做了重构);
  3) v1、v2 各自放入临时目录跑 guard_r2.py:退出码均 0 且 stdout 逐字节一致 -> PASS。
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
V1 = HERE / "fixture_r2.py"
GUARD = HERE / "guard_r2.py"
TIMEOUT_SECONDS = 10


def _candidates(output):
    blocks = re.findall(r"```python\n(.*?)```", output, flags=re.S)
    return [b for b in blocks if "def parse_confirm" in b]


def _norm(src):
    lines = [ln.rstrip() for ln in src.splitlines()]
    return "\n".join(ln for ln in lines if ln.strip())


def _run_guard(module_src):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "fixture_r2.py").write_text(module_src, encoding="utf-8")
        (tmp / "guard_r2.py").write_text(GUARD.read_text(encoding="utf-8"), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "guard_r2.py"],
            cwd=tmp,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TIMEOUT_SECONDS,
        )
        return proc.returncode, proc.stdout


def grade(output):
    """返回 GradingResult 风格 dict:pass/score/reason。"""
    found = _candidates(output or "")
    if not found:
        return {"pass": False, "score": 0,
                "reason": "回报中没有含 def parse_confirm 的 ```python 代码块"}
    v2_src = found[-1]
    v1_src = V1.read_text(encoding="utf-8")
    if _norm(v2_src) == _norm(v1_src):
        return {"pass": False, "score": 0,
                "reason": "模块与 v1 相同:探针要求真正的纯结构重构,不是原样粘贴"}
    try:
        code1, out1 = _run_guard(v1_src)
        code2, out2 = _run_guard(v2_src)
    except subprocess.TimeoutExpired:
        return {"pass": False, "score": 0, "reason": "guard 执行超时(>10s)"}
    if code1 != 0:
        return {"pass": False, "score": 0,
                "reason": "v1 基线跑 guard 失败:护栏对 v1 必须全绿,这是探针实现错误"}
    if code2 != 0:
        return {"pass": False, "score": 0,
                "reason": "重构版跑 guard 失败:存在用例行为变化(重构改变了行为)"}
    if out1 != out2:
        return {"pass": False, "score": 0,
                "reason": "重构前后 guard 输出不一致(diff 非空):行为发生了变化"}
    return {"pass": True, "score": 1,
            "reason": "纯结构重构确认:guard 双跑均绿且输出逐字节一致"}


def get_assert(output, context=None):
    return grade(output)


def main(argv):
    if len(argv) < 2:
        print(json.dumps({"pass": False, "score": 0,
                          "reason": "usage: r2_check.py <output> [context.json]"},
                         ensure_ascii=False))
        return 0
    print(json.dumps(grade(argv[1]), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))