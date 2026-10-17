"""R2 行为护栏:对 parse_confirm 的固定用例集逐条比对预期。

运行方式:与本文件同目录放一个 fixture_r2.py,然后 python3 guard_r2.py。
退出码 0 = 全部用例符合预期;非 0 = 存在行为差异。
输出按用例顺序逐行打印,末行 fails=N —— 重构前后输出必须逐字节一致。
"""
import sys

import fixture_r2  # 与被测模块同目录运行

CASES = [
    ("全签", "CONFIRM"),
    ("全签。", "CONFIRM"),
    ("全签！", "CONFIRM"),
    ("全签，origin=code", "CONFIRM"),
    ("全签 origin=code", "CONFIRM"),
    ("全签x", "REJECT"),
    ("全签全签", "REJECT"),
    ("确认", "CONFIRM"),
    ("确认:", "CONFIRM"),
    ("确认：", "CONFIRM"),
    ("确认；", "CONFIRM"),
    ("确认 origin=code", "CONFIRM"),
    ("确认x", "REJECT"),
    ("同意", "CONFIRM"),
    ("同意。", "CONFIRM"),
    ("同意\torigin=code", "CONFIRM"),
    ("同意x", "REJECT"),
    ("  全签。  ", "CONFIRM"),
    ("", "REJECT"),
    ("拒绝", "REJECT"),
    ("全签、", "CONFIRM"),
    ("确认、origin=code", "CONFIRM"),
]


def main():
    fails = 0
    for text, want in CASES:
        got = fixture_r2.parse_confirm(text)
        ok = got == want
        if not ok:
            fails += 1
        print(f"{'ok' if ok else 'FAIL'} {text!r} -> {got} (want {want})")
    print(f"fails={fails}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())