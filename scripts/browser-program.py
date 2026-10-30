#!/usr/bin/env python3
"""Admit or refuse one browser program. No browser and no external CLI.

    browser-program.py --schema
    browser-program.py admit --lane FILE     # submission YAML on stdin
    browser-program.py apply --lane FILE     # receipt YAML on stdin
    browser-program.py advise                # receipt YAML on stdin; no lane
    browser-program.py scene                 # which scene fields are still missing
    browser-program.py tally --lane FILE     # four counts, not a score

The lane is the receipt store. admit registers a queued receipt before the
caller runs the program. The same request id returns that receipt and does
not run again. A program that changes the page runs once per task; a later
request id with the same text is refused. Checking the page afterwards is a
different, read-only program.

Exit: 0 run or stored, 1 rejected, 2 unreadable input.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import browser_advise  # noqa: E402
import browser_history  # noqa: E402
import browser_lane as lane  # noqa: E402
import safeyaml  # noqa: E402

ACTIVE_LIMIT = lane.ACTIVE_LIMIT
INLINE_CAP = lane.INLINE_CAP
admit = lane.admit
advise = browser_advise.advise
scene = browser_advise.scene
tally = browser_history.tally
apply = lane.apply
put = lane.put
PASS_LINE = "PASS 只说明没撞上已知的硬错，不说明页面做对了"

SCHEMA = """\
# 浏览器程序
#
# 全文：references/browser-program.md
#
# admit 的 op：run（默认）| inspect | finish | discard | claim
# run 的标准输入：
#   task, request_id, program
#   mutates: 默认 false。文本里已有点击、填写、按键、选择、上传时照样算改页面
#   target: named（默认）或 visual
#   background: 默认在后台。false 或 foreground: true 拒绝
# inspect：task + request_id，取回执，不执行
# finish：task，保留回执，任务可继续
# discard：task，可选 tabs。认领过的标签页不能出现在 tabs 里
# claim：task + tab_ids
# 同时未丢弃的任务最多 8 个
#
# apply 在 run 的字段之外再加：
#   status: queued | running | succeeded | failed | interrupted
#   mutation: none | possible | unknown
#   verified, business_ok（办成必须 verified，且 outcome 不是 unknown）
#   block_reason 或 errors：status 为 failed 时至少有一个
#   duration_ms: 非负整数，可省略
#   result, errors, page_changes: 字符串不超过 4096。截图用文件，不放 base64
#
# advise 读一条回执，只回答下一段：
#   wait | probe | late | tighten | unblock | continue | hold
# scene 读一条回执，列出现场还缺的项。截图是文件路径。
# tally 把一条 lane 分成 false_success / unknown / failed / verified。四个数不加总。
# advise 和 scene 不写 lane。0 给出结果，1 回执不成立。
#
# 拒绝：task_required request_id program_required target op tab_ids tabs missing
#       force_click evaluate_click inline_image outside_task coordinate_for_named
#       assertion_required parallel_write steals_focus task_limit
#       new_id_required write_once status mutation business_unverified
#       outcome_unknown block_reason duration_ms unreduced_result errors
#       page_changes claimed_tab screenshot listen_late page_left_open
#       position_retry idempotency_key
#
# 退出码：0 可执行或取回，1 拒绝，2 读不了。
"""


def read_body() -> dict | None:
    return safeyaml.mapping_from_text(sys.stdin.read())


def lane_broken(path: Path) -> bool:
    return path.exists() and safeyaml.mapping(path) is None


def print_result(payload: dict, ok: bool) -> int:
    sys.stdout.write(safeyaml.dump(payload))
    if not ok:
        return 1
    print(PASS_LINE)
    return 0


def _admit_mutate(data: dict, submission: dict, box: dict) -> dict:
    decision = admit(data, submission)
    box["decision"] = decision
    if decision.get("lane") is not None:
        return decision["lane"]
    if decision["action"] != "run":
        return data
    return put(data, decision["receipt"])


def command_admit(path: Path) -> int:
    submission = read_body()
    if submission is None:
        print("submission unreadable")
        return 2
    if lane_broken(path):
        print("lane unreadable")
        return 2
    box: dict = {}
    safeyaml.save_locked(path, lambda data: _admit_mutate(data, submission, box))
    decision = box["decision"]
    shown = {key: value for key, value in decision.items() if key != "lane"}
    return print_result(shown, decision["action"] != "reject")


def _apply_mutate(data: dict, receipt: dict, box: dict) -> dict:
    result = apply(data, receipt)
    shown = {"ok": result["ok"], "reason": result["reason"]}
    if result["ok"]:
        task = str(receipt["task"])
        shown["receipt"] = lane.task_map(result["lane"], task)[str(receipt["request_id"])]
    box["shown"] = shown
    box["ok"] = result["ok"]
    return result["lane"]


def command_advise() -> int:
    receipt = read_body()
    if receipt is None:
        print("receipt unreadable")
        return 2
    decision = advise(receipt)
    sys.stdout.write(safeyaml.dump(decision))
    if decision["action"] == "reject":
        return 1
    return 0


def command_scene() -> int:
    receipt = read_body()
    if receipt is None:
        print("receipt unreadable")
        return 2
    report = scene(receipt)
    sys.stdout.write(safeyaml.dump(report))
    if report["ready"]:
        return 0
    return 1


def command_tally(path: Path) -> int:
    if path.exists() and lane_broken(path):
        print("lane unreadable")
        return 2
    data = safeyaml.mapping(path) if path.exists() else {}
    sys.stdout.write(safeyaml.dump(tally(data or {})))
    return 0


def command_apply(path: Path) -> int:
    receipt = read_body()
    if receipt is None:
        print("receipt unreadable")
        return 2
    if lane_broken(path):
        print("lane unreadable")
        return 2
    box: dict = {}
    safeyaml.save_locked(path, lambda data: _apply_mutate(data, receipt, box))
    return print_result(box["shown"], box["ok"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", choices=("admit", "apply", "advise", "scene", "tally"))
    parser.add_argument("--lane", type=Path)
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args(argv)
    if args.schema:
        print(SCHEMA, end="")
        return 0
    if args.command == "advise":
        return command_advise()
    if args.command == "scene":
        return command_scene()
    if not args.command or args.lane is None:
        parser.error("admit、apply 和 tally 都要 --lane")
    if args.command == "admit":
        return command_admit(args.lane)
    if args.command == "tally":
        return command_tally(args.lane)
    return command_apply(args.lane)


if __name__ == "__main__":
    sys.exit(main())
