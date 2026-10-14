#!/usr/bin/env python3
"""Check a UI playbook covers the lifecycle, in order, on tagged entities.

    ui-playbook.py --repo DIR [--e2e DIR]        # check the playbook
    ui-playbook.py --repo DIR --plan             # what is still uncovered
    ui-playbook.py --schema                      # the playbook contract

Existing tooling answers "does the e2e source mention this token"
(ui-coverage-check) and "what surfaces exist" (ui-surface-scan). Neither
answers the question a lifecycle playbook actually turns on: **does each
flow create its own subject, read it, change it, put it back, and clean
up — in that order, on an entity marked as test-made?**

That order is not ceremony. Each phase protects the next:

  create   a flow that reuses someone else's data fails for reasons that
           have nothing to do with the code under test
  tag      an untagged test entity is indistinguishable from real data, so
           cleanup cannot be safe and neither can a human looking at prod
  read     reading back what you just created is the cheapest check that
           the write actually landed — before any mutation muddies it
  change   the mutation under test
  restore  put it back, so a re-run starts from the same place. NOT strict:
           「符合预期即可」—— an irreversible step records what it expects
           instead of pretending to undo
  cleanup  the entity goes away, or the next run inherits the mess

What this does NOT check: whether the assertions are meaningful. A flow can
have all six phases and assert nothing. That is for review and for verify.

Exit: 0 ok, 1 findings, 2 cannot read.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import safeyaml  # noqa: E402
import textwidth as tw  # noqa: E402

PHASES = ("create", "read", "change", "restore", "cleanup")
PHASE_WHY = {
    "create": "自己造主体 —— 复用别人的数据会因与被测代码无关的原因失败",
    "read": "读回刚建的 —— 最便宜的一次「写真的落了吗」,且在变更搅浑之前",
    "change": "被测的那次变更",
    "restore": "归位,让重跑从同一处开始(非强制:不可逆的写明预期即可)",
    "cleanup": "实体消失,否则下一轮继承一堆垃圾",
}

# How a flow declares its phases. A comment marker keeps this readable in
# the test source itself, rather than hiding the contract in a side file.
PHASE_MARK = re.compile(r"(?mi)^\s*(?://|/\*|\*|#)\s*@phase[:\s]+(\w+)")
# test.step('create: ...') is the other accepted form — it shows up in the
# Playwright trace viewer, which is where someone debugging actually looks.
STEP_PHASE = re.compile(r"""(?mi)\btest\.step\s*\(\s*['"`]\s*(\w+)\s*[::]""")
# The tag that makes a test entity recognisable in a real system.
TAG_RE = re.compile(r"(?i)(AUTOTEST|E2E_|__e2e|autotest[-_]?)")
ASSERT_RE = re.compile(r"\bexpect\s*\(|\.toHave|\.toBe|\.toContain|assert\b")
# Hard-coded ids are how a flow quietly starts depending on someone's data.
FIXED_ID = re.compile(r"""['"](?:\d{6,}|[0-9a-f]{8}-[0-9a-f]{4}-)""")

SCHEMA = """\
# UI 剧本契约
#
# 每个 flow 覆盖一个实体的完整生命周期,顺序固定。两种声明方式都认:
#
#   // @phase: create          注释标记,留在源码里好读
#   test.step('create: 新建实例', ...)   Playwright 的 step,出现在 trace viewer 里
#
# 六件事:
#
#   create    自己造主体。名字带自动化标记(AUTOTEST / E2E_ / __e2e)
#   read      读回刚建的实体,检查只读信息
#   change    做被测的那次变更
#   restore   归位。**非强制** —— 不可逆的操作写明预期即可:
#             // @phase: restore (irreversible: 审批通过后不可撤回,预期状态为 approved)
#   cleanup   删除实体。失败也要尝试(afterEach / finally)
#
# 标记为什么必须:没标记的测试实体和真实数据分不开 —— 清理不敢做,
# 线上看到它的人也不知道那是什么。
#
# e2e/inventory.json 里每个 required token 要挂 wave(由 ui-coverage-check 管),
# 本工具管的是 flow 自身的生命周期完整性。
#
# 目录约定(沿用 ui-coverage-check):
#   e2e/flows/*.spec.ts      剧本
#   e2e/helpers/*.ts         共用步骤
#   e2e/inventory.json       交互面清单(ui-surface-scan 产出)
"""


class Finding:
    __slots__ = ("flow", "rule", "detail")

    def __init__(self, flow: str, rule: str, detail: str) -> None:
        self.flow, self.rule, self.detail = flow, rule, detail

    def __str__(self) -> str:
        return f"FAIL [{self.flow}] {self.rule}\n       {self.detail}"


def phases_in(text: str) -> list[str]:
    """Phases in the order they appear, from either declaration form."""
    hits: list[tuple[int, str]] = []
    for m in PHASE_MARK.finditer(text):
        hits.append((m.start(), m.group(1).lower()))
    for m in STEP_PHASE.finditer(text):
        name = m.group(1).lower()
        if name in PHASES:
            hits.append((m.start(), name))
    hits.sort()
    # Collapse consecutive repeats: a phase may legitimately span several
    # steps, what matters is the order of first appearance.
    out: list[str] = []
    for _, name in hits:
        if not out or out[-1] != name:
            out.append(name)
    return out


def check_flow(path: Path, out: list[Finding]) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    flow = path.name
    found = phases_in(text)

    if not found:
        out.append(Finding(
            flow, "no-phases",
            "没有任何阶段标记。用 `// @phase: create` 或 "
            "`test.step('create: ...')` 标出 create/read/change/restore/cleanup"))
        return

    unique = [p for p in PHASES if p in found]
    missing = [p for p in PHASES if p not in found]
    for p in missing:
        if p == "restore":
            # restore is the one that may be legitimately absent, but only
            # when the flow says why.
            if not re.search(r"(?i)irreversible|不可逆|不可撤|单向", text):
                out.append(Finding(
                    flow, "missing-restore",
                    "没有 restore 阶段。不可逆的操作可以不归位,但要写明:"
                    "`// @phase: restore (irreversible: <为什么> ,预期状态 <X>)`"))
        else:
            out.append(Finding(flow, f"missing-{p}",
                               f"缺 {p} 阶段 —— {PHASE_WHY[p]}"))

    # Order: the sequence of first appearances must follow PHASES — but
    # cleanup inside afterEach/afterAll/finally is *written* early and *runs*
    # last, which is exactly the shape we want. Judging it by text position
    # would punish the correct form.
    hook_cleanup = bool(
        re.search(r"(?s)(?:afterEach|afterAll|finally)\b.{0,300}?@phase[:\s]+cleanup", text)
        or re.search(r"(?s)(?:afterEach|afterAll|finally)\b.{0,300}?step\s*\(\s*['\"`]\s*cleanup", text)
    )
    seq = [p for p in found if p in PHASES and not (p == "cleanup" and hook_cleanup)]
    seen: list[str] = []
    for p in seq:
        if p not in seen:
            seen.append(p)
    expected = [p for p in PHASES if p in seen]
    if seen != expected:
        note = "(cleanup 在 afterEach/finally 里,不计入文本顺序)" if hook_cleanup else ""
        out.append(Finding(
            flow, "phase-order",
            f"阶段顺序是 {' → '.join(seen)}{note},应为 {' → '.join(expected)}。"
            "读回要在变更之前(否则分不清写没写进去),清理要在最后"))

    # The entity must be recognisable as test-made.
    if "create" in found and not TAG_RE.search(text):
        out.append(Finding(
            flow, "untagged-entity",
            "create 阶段没有自动化标记(AUTOTEST / E2E_ / __e2e)。"
            "没标记的测试实体和真实数据分不开 —— 清理不敢做,"
            "线上看到它的人也不知道那是什么"))

    # Cleanup that only runs on the happy path leaves debris behind.
    if "cleanup" in found and not re.search(r"afterEach|afterAll|finally|\.finally\(", text):
        out.append(Finding(
            flow, "cleanup-not-guaranteed",
            "cleanup 没有放在 afterEach / afterAll / finally 里 —— "
            "用例中途失败时它不会执行,下一轮继承垃圾"))

    if not ASSERT_RE.search(text):
        out.append(Finding(flow, "no-assertion",
                           "整个 flow 没有任何断言 —— 它只是点了一遍界面"))

    # A fixed id is how a flow quietly starts depending on someone's data.
    m = FIXED_ID.search(text)
    if m and "create" in found:
        out.append(Finding(
            flow, "hard-coded-id",
            f"出现写死的 id「{m.group(0)[1:]}…」—— create 阶段既然自己造了主体,"
            "就该用它返回的 id。写死的 id 让剧本依赖某份特定数据"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--e2e", type=Path, help="e2e dir (default: <repo>/e2e)")
    parser.add_argument("--plan", action="store_true", help="what is still uncovered")
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()

    if args.schema:
        print(SCHEMA)
        return 0

    repo = args.repo.resolve()
    e2e = (args.e2e or (repo / "e2e")).resolve()
    if not e2e.is_dir():
        print(f"BLOCKED no e2e directory at {e2e}", file=sys.stderr)
        print("HINT    剧本放 e2e/flows/*.spec.ts,共用步骤放 e2e/helpers/", file=sys.stderr)
        print("HINT    契约见 --schema", file=sys.stderr)
        return 2

    flows = sorted((e2e / "flows").glob("*.spec.*")) if (e2e / "flows").is_dir() else []
    inv_path = e2e / "inventory.json"
    inventory = []
    if inv_path.is_file():
        try:
            inventory = json.loads(inv_path.read_text(encoding="utf-8")).get("tokens", [])
        except (json.JSONDecodeError, OSError, AttributeError):
            print(f"WARN  cannot read {inv_path}", file=sys.stderr)

    if args.plan:
        required = [t for t in inventory if isinstance(t, dict) and t.get("required")]
        by_wave: dict[str, list] = {}
        for t in required:
            by_wave.setdefault(str(t.get("wave") or "(未挂 wave)"), []).append(t)
        print(f"# 剧本计划  {e2e}")
        print(f"# required token {len(required)} 个,flow {len(flows)} 个")
        print()
        for wave in sorted(by_wave):
            toks = by_wave[wave]
            print(f"  {tw.ljust(wave, 24)} {len(toks)} 个交互面")
            for t in toks[:6]:
                print(f"      {t.get('page', '?')}  {(t.get('needles') or [t.get('token', '?')])[0]}")
            if len(toks) > 6:
                print(f"      … 另 {len(toks) - 6} 个")
        print()
        if "(未挂 wave)" in by_wave:
            print("未挂 wave 的 token 不会被任何剧本覆盖 —— 先归到一个 wave 里。")
        print("每个 wave 一个 flow,flow 内走完 create → read → change → restore → cleanup。")
        return 0 if flows else 1

    findings: list[Finding] = []
    if not flows:
        print(f"# ui-playbook  {e2e}")
        print()
        print("FAIL 没有任何 flow(e2e/flows/*.spec.*)")
        print()
        print("剧本从 inventory 的 wave 来:`--plan` 看还有哪些交互面没覆盖。")
        print("契约见 `--schema`。")
        return 1

    for f in flows:
        check_flow(f, findings)

    print(f"# ui-playbook  {e2e}")
    print(f"# {len(flows)} 个 flow,inventory 里 {len(inventory)} 个 token")
    print()

    if findings:
        for f in findings:
            print(f)
        print()
        print(f"ui-playbook FAIL  {len(findings)} 处")
        print()
        print("生命周期的顺序不是仪式:read 在 change 之前才分得清「写没写进去」;")
        print("实体打标了清理才敢做;cleanup 在 finally 里失败时才会执行。")
        return 1

    print(f"ui-playbook PASS  {len(flows)} 个 flow 的生命周期完整")
    print()
    print("**阶段齐 ≠ 测得对。** 这里只查「六件事做了没、顺序对不对、实体标了没」——")
    print("断言是否有意义要人评审,红绿仍走 verify。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
