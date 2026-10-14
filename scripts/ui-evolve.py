#!/usr/bin/env python3
"""Spot state conflicts while a UI playbook is being written.

For the authoring stage: run it as you add flows, before anyone waits on a
red run to find out the playbook contradicts itself.

    ui-evolve.py --repo DIR [--e2e DIR]            # scan flows for conflicts
    ui-evolve.py --repo DIR --report RESULT.json   # also read a run result
    ui-evolve.py --schema                          # the state-switch contract

The problem this solves is not a flaky test. It is a playbook whose state
assumptions contradict each other: one flow turns authentication on, the
next one needs it off, and no amount of re-running fixes that.
`ui.clean_pass_loop` re-runs the whole lifecycle until it is green — which
never converges here, because the conflict is structural.

Catching it at authoring time is the cheap moment. The same conflict found
by a red run costs a full lifecycle run plus the time spent suspecting the
product code.

So this reads the flows, works out which global switches each one flips and
which it depends on, and reports where the order makes a later flow
impossible. For each conflict it offers the two restructurings that actually
work:

  **branch**   two flows, one per switch state, each self-contained
  **reorder**  move the switch-flipping flow last, so everything that
               depends on the default state runs first

**It proposes; it never edits.** At authoring time the author is right
there — the useful output is "here are the two structures that work", not a
silently rewritten file. (And a tool that rewrote tests until they passed
would be marking its own homework.) `--report` lets a red run feed the same
analysis, for the case where a conflict slipped through.

Exit: 0 no conflict, 1 conflicts found, 2 cannot read.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import textwidth as tw  # noqa: E402

SCHEMA = """\
# 全局状态开关契约
#
# 剧本里凡是改变**后续场景前置条件**的操作,都要声明。否则下一个场景会在
# 一个它没预期的世界里跑,而重跑一万次也不会好 —— 冲突是结构性的。
#
#   // @switch: auth on            本 flow 把 auth 打开了(留给后续)
#   // @switch: auth off           本 flow 把它关了
#   // @switch: auth restore       本 flow 用完归位(不影响后续)
#   // @requires: auth off         本 flow 需要 auth 处于 off 才能跑
#
# 常见的全局开关:auth(鉴权)· approval(审批)· readonly(只读模式)·
# feature flag · tenant(租户切换)· locale(语言)
#
# 两种可行的重构(ui-evolve.py 会提,但不替你改):
#
#   branch   按开关状态拆两个 flow,各自自洽:
#            auth-on.spec.ts   里面 @switch: auth on  + @requires: auth on
#            auth-off.spec.ts  里面 @switch: auth off + @requires: auth off
#            代价:剧本数量翻倍;收益:每个 flow 不依赖别人留下的状态
#
#   reorder  把动开关的 flow 排到最后,前面的场景都在默认状态下跑:
#            // @order: last   (或 @order: first / @order: <数字>)
#            代价:开关相关的覆盖集中在尾部;收益:复杂度最低,改动最小
#
# 选哪个:开关影响**多个**场景的行为 → branch;只是「最后顺便验一下开关本身」
# → reorder。后者是你描述的「串完其它场景后,最后再验鉴权和关鉴权来降低复杂度」。
"""

SWITCH = re.compile(r"(?mi)^\s*(?://|/\*|\*|#)\s*@switch[:\s]+(\w[\w-]*)\s+(on|off|restore)\b")
REQUIRES = re.compile(r"(?mi)^\s*(?://|/\*|\*|#)\s*@requires[:\s]+(\w[\w-]*)\s+(on|off)\b")
ORDER = re.compile(r"(?mi)^\s*(?://|/\*|\*|#)\s*@order[:\s]+(first|last|\d+)\b")

# Heuristics for a flow that flips a switch without saying so. These are the
# words that show up in the code when it happens.
IMPLIED_ON = re.compile(r"(?i)(?:enable|turn[-_ ]?on|open)[-_ ]?(auth|approval|readonly|rbac)"
                        r"|(auth|approval|rbac)[-_ ]?(?:enable|on)\b"
                        r"|开启(?:鉴权|认证|审批)|打开(?:鉴权|认证|审批)")
IMPLIED_OFF = re.compile(r"(?i)(?:disable|turn[-_ ]?off|close)[-_ ]?(auth|approval|readonly|rbac)"
                         r"|(auth|approval|rbac)[-_ ]?(?:disable|off)\b"
                         r"|关闭(?:鉴权|认证|审批)|approval[-_ ]?off")
# Failures that mean "the world was not what this flow expected", as opposed
# to a real defect. These are the signatures worth proposing a restructure for.
AUTH_FAIL = re.compile(r"(?i)401|403|unauthor|forbidden|需要鉴权|未登录|no permission|权限不足")


class Flow:
    __slots__ = ("path", "name", "switches", "requires", "order", "implied")

    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = path.name
        text = path.read_text(encoding="utf-8", errors="replace")
        self.switches = [(m.group(1), m.group(2)) for m in SWITCH.finditer(text)]
        self.requires = [(m.group(1), m.group(2)) for m in REQUIRES.finditer(text)]
        # Strip the declaration lines before the heuristics run: `@requires:
        # auth off` states a dependency, not an action, and reading it as a
        # flip is a false positive that teaches people to ignore findings.
        body = SWITCH.sub("", REQUIRES.sub("", ORDER.sub("", text)))
        om = ORDER.search(text)
        self.order = om.group(1) if om else ""
        # An undeclared flip is worse than a declared one: nothing downstream
        # can see it coming.
        self.implied: list[tuple[str, str]] = []
        declared = {s for s, _ in self.switches}
        for rx, state in ((IMPLIED_ON, "on"), (IMPLIED_OFF, "off")):
            for m in rx.finditer(body):
                sw = next((g for g in m.groups() if g), "auth").lower()
                if sw not in declared:
                    self.implied.append((sw, state))
        # Dedupe while keeping order.
        seen = set()
        self.implied = [x for x in self.implied if not (x in seen or seen.add(x))]

    def leaves(self) -> dict[str, str]:
        """Switch states this flow leaves behind for the next one."""
        out: dict[str, str] = {}
        for sw, state in self.switches:
            if state == "restore":
                out.pop(sw, None)
            else:
                out[sw] = state
        return out


class Conflict:
    __slots__ = ("kind", "switch", "setter", "victim", "detail", "fix")

    def __init__(self, kind: str, switch: str, setter: str, victim: str,
                 detail: str, fix: str) -> None:
        self.kind, self.switch = kind, switch
        self.setter, self.victim = setter, victim
        self.detail, self.fix = detail, fix


def ordered(flows: list[Flow]) -> list[Flow]:
    """Playwright runs files alphabetically unless told otherwise."""
    def key(f: Flow) -> tuple:
        if f.order == "first":
            return (0, 0, f.name)
        if f.order == "last":
            return (2, 0, f.name)
        if f.order.isdigit():
            return (1, int(f.order), f.name)
        return (1, 10**6, f.name)
    return sorted(flows, key=key)


def analyse(flows: list[Flow]) -> tuple[list[Conflict], list[str]]:
    out: list[Conflict] = []
    notes: list[str] = []
    seq = ordered(flows)

    # Walk the run in order, carrying the switch state forward.
    state: dict[str, tuple[str, str]] = {}   # switch -> (value, who set it)
    for f in seq:
        for sw, want in f.requires:
            have = state.get(sw)
            if have and have[0] != want:
                out.append(Conflict(
                    "requires-conflict", sw, have[1], f.name,
                    f"{have[1]} 把 {sw} 置为 {have[0]},而 {f.name} 需要它是 {want} —— "
                    f"按当前顺序,{f.name} 跑不起来,**重跑多少次都一样**",
                    f"branch:按 {sw} 的 on/off 拆两个自洽的 flow;"
                    f"或 reorder:给 {have[1]} 加 `// @order: last`,"
                    f"让依赖默认状态的场景先跑完"))
        for sw, st in f.leaves().items():
            state[sw] = (st, f.name)

    # An undeclared flip is invisible to everything downstream.
    for f in flows:
        for sw, st in f.implied:
            out.append(Conflict(
                "undeclared-switch", sw, f.name, "(后续全部)",
                f"{f.name} 看起来把 {sw} 置为 {st},但没有 `@switch: {sw} {st}` 声明 —— "
                "后续场景无法预见这个变化,也无法被本工具检出冲突",
                f"在该 flow 里声明 `// @switch: {sw} {st}`;"
                f"若它用完就归位,写 `// @switch: {sw} restore`"))

    # A switch left on at the end of the run leaks into the next run.
    leftover = {sw: who for sw, (val, who) in state.items() if val}
    for sw, who in leftover.items():
        last = seq[-1].name if seq else "?"
        if who != last:
            notes.append(
                f"{who} 把 {sw} 置为 {state[sw][0]} 且没归位,它会留到下一轮 —— "
                f"把它排到最后(`// @order: last`)或加 `@switch: {sw} restore`")

    return out, notes


def from_report(path: Path, flows: list[Flow]) -> list[Conflict]:
    """Conflicts a real run revealed: an auth-shaped failure in a flow that
    never declared it needs a particular state."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARN cannot read {path}: {exc}", file=sys.stderr)
        return []

    by_name = {f.name: f for f in flows}
    out: list[Conflict] = []

    def visit(node: object) -> None:
        if isinstance(node, dict):
            title = str(node.get("title") or node.get("name") or "")
            err = json.dumps(node.get("errors") or node.get("error") or "", ensure_ascii=False)
            loc = str(node.get("file") or node.get("location") or "")
            if AUTH_FAIL.search(err):
                fname = Path(loc).name or title
                flow = by_name.get(fname)
                declared = [s for s, _ in (flow.requires if flow else [])]
                if not declared:
                    out.append(Conflict(
                        "runtime-state-failure", "auth", "(上游某个 flow)", fname or title,
                        f"运行时报鉴权相关失败,而 {fname or title} 没有声明它需要的状态 —— "
                        "这更可能是前置状态不对,不是被测代码的缺陷",
                        "先补 `// @requires: auth <on|off>`,再决定 branch 还是 reorder。"
                        "**在确认是状态问题之前,不要把它当成产品 bug 去改代码**"))
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for v in node:
                visit(v)

    visit(data)
    # Dedupe by victim.
    seen = set()
    return [c for c in out if not (c.victim in seen or seen.add(c.victim))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--e2e", type=Path)
    parser.add_argument("--report", type=Path, help="a Playwright json report to read failures from")
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()

    if args.schema:
        print(SCHEMA)
        return 0

    e2e = (args.e2e or (args.repo.resolve() / "e2e")).resolve()
    flows_dir = e2e / "flows"
    if not flows_dir.is_dir():
        print(f"BLOCKED no e2e/flows at {flows_dir}", file=sys.stderr)
        return 2

    flows = [Flow(p) for p in sorted(flows_dir.glob("*.spec.*"))]
    if not flows:
        print(f"BLOCKED no flows in {flows_dir}", file=sys.stderr)
        return 2

    conflicts, notes = analyse(flows)
    if args.report and args.report.is_file():
        conflicts += from_report(args.report, flows)

    print(f"# ui-evolve  {e2e}")
    print(f"# {len(flows)} 个 flow")
    print()

    print("## 执行顺序与状态流转")
    print()
    state: dict[str, str] = {}
    for f in ordered(flows):
        marks = []
        for sw, st in f.switches:
            marks.append(f"{sw}→{st}")
        for sw, st in f.requires:
            marks.append(f"需要 {sw}={st}")
        tag = f"  [{', '.join(marks)}]" if marks else ""
        order = f"  @order:{f.order}" if f.order else ""
        print(f"  {tw.ljust(f.name, 30)}{tag}{order}")
        state.update(f.leaves())
    if state:
        print()
        print(f"  跑完之后遗留: {', '.join(f'{k}={v}' for k, v in sorted(state.items()))}")
    print()

    if not conflicts:
        print("ui-evolve PASS  没有发现状态冲突")
        for n in notes:
            print(f"NOTE {n}")
        print()
        print("**没冲突 ≠ 剧本够好。** 这里只查状态开关的相容性;")
        print("覆盖面看 `ui-playbook.py --plan`,生命周期看 `ui-playbook.py`。")
        return 0

    by_kind: dict[str, list[Conflict]] = {}
    for c in conflicts:
        by_kind.setdefault(c.kind, []).append(c)

    labels = {
        "requires-conflict": "前置状态被上游改掉了",
        "undeclared-switch": "改了全局开关却没声明",
        "runtime-state-failure": "运行时失败像是状态问题,不像缺陷",
    }
    for kind, items in by_kind.items():
        print(f"## {labels.get(kind, kind)}  ({len(items)})")
        print()
        for c in items:
            print(f"  冲突: {c.setter} → {c.victim}  [{c.switch}]")
            print(f"    {c.detail}")
            print(f"    改法: {c.fix}")
            print()

    for n in notes:
        print(f"NOTE {n}")
    if notes:
        print()

    print(f"ui-evolve FAIL  {len(conflicts)} 处状态冲突")
    print()
    print("**这类失败重跑不会好** —— `ui.clean_pass_loop` 从头再跑一轮,冲突还在同一处。")
    print("两种改法见 `--schema`:branch(按开关拆两个自洽 flow)或")
    print("reorder(把动开关的排最后,前面都在默认状态下跑)。")
    print()
    print("**本工具只提方案,不改剧本。** 编写阶段作者就在现场,有用的输出是")
    print("「这两种结构都成立」,不是悄悄改掉文件。采纳哪种由你定,改完重跑确认。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
