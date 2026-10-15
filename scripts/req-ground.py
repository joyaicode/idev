#!/usr/bin/env python3
"""Ground a requirement in the code that already exists, before sealing it.

    req-ground.py --feature F [--repo DIR]      # check the grounding
    req-ground.py --feature F --probe           # what to go read
    req-ground.py --schema                      # the grounding block

The baseline is sealed at req-review and becomes the measuring stick for
everything after it. But impact analysis only appears at `arch`
(experts.md: codegraph_impact --depth 1) — which is *after* the seal. So a
requirement can be sealed by people who never looked at the code, and the
conflict surfaces one stage later, when the only way out is a reopen:
revision + 1, every old slice and case void.

Moving the look earlier is cheap. Reading the existing logic before sealing
costs an hour; finding the contradiction after sealing costs a reopen plus
everything built on the wrong baseline.

So each baseline item carries a `grounding` block answering four questions
a machine can check are *present* (it cannot check they are *right*):

    touches       which existing code this requirement lands on
    conflicts     where it contradicts logic that is already there
    boundary      what is explicitly NOT in scope
    direction     how it fits the product's current evolution

and, when the requirement is a response to the market, a `comparison`
block: what competitors do, where this deliberately differs, and why.

**A conflict is not a finding to note and move past.** experts.md is
explicit: 和已锁契约冲突却不写进问题 is a reject. A declared conflict must
appear as a grill question, and grilling runs until the detail is settled —
that is a conversation with a person, not a field to fill.

What this cannot judge: whether the reading is correct, whether the
comparison is fair, whether the direction call is right. Those are the
grill's job. Silence here means the homework was declared, not that it was
done well.

Exit: 0 grounded, 1 findings, 2 cannot read.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402

sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
try:
    import doc_home  # noqa: E402
except ImportError:
    print(f"BLOCKED cannot import doc_home from {kind_agents.kernel_root()}", file=sys.stderr)
    raise SystemExit(2) from None

SCHEMA = """\
# baseline.yaml 的 grounding 块(每个 item 下,密封前必填)
#
# 需求不能脱离这个工程谈。密封之后基线就是尺,而影响面评估原本要到 arch 才做 ——
# 那时发现冲突只能 reopen(revision + 1,旧 slice / case 全作废)。
# 把「读代码」前移到密封之前,成本是一小时;发现晚了,成本是一整轮。
#
# items:
#   - id: B1
#     must: 登录失败给出可定位提示
#     acceptance: 3 秒内返回带错误码的提示
#     grounding:
#       touches:                      # 落在哪些既有代码上(file:symbol)
#         - src/auth/login.py:authenticate
#         - src/gateway/filter.py:AuthFilter
#       impact:                       # 调用方(codegraph_impact --depth 1 提名)
#         - src/api/session.py:create_session
#       conflicts:                    # 与存量逻辑的冲突点
#         - where: src/auth/login.py:authenticate
#           existing: 现在统一返回 AUTH_FAILED,不区分原因
#           tension: 本需求要区分「密码错」与「账号锁定」,与既有的「不泄漏账号状态」相悖
#           grill: Q3            # ← 必须挂到 grill.md 的问句
#       boundary:                     # 明确不做什么(纵向边界)
#         - 不改第三方 SSO 的回调逻辑
#         - 不动既有错误码的编号规则
#       direction: |                  # 与产品当前演进方向的关系
#         与 ADR-012「可观测性优先」一致:错误码可被日志聚合。
#         不涉及 ADR-007 的鉴权模型变更。
#
#     comparison:                     # 可选:竞品横向对比(市场驱动的需求建议写)
#       peers:
#         - name: 竞品 A
#           behaviour: 区分密码错/账号锁定,并给出剩余重试次数
#         - name: 竞品 B
#           behaviour: 统一提示,不区分
#       differs: 我们不给剩余重试次数
#       why: 剩余次数会被用来枚举有效账号;见 ADR-007 的威胁模型
#       grill: Q5                     # 与竞品差异大 → 必须拷问
#
# 可机检的(--check):
#   touches 非空且是 file:symbol · 有 conflicts 就必须挂 grill 问句 ·
#   boundary 非空 · direction 非空 · comparison 的 differs 要有 why 和 grill
#
# 机器判不了的(交 grill 和人):读得对不对、对比公不公平、方向判断是否成立。
"""

ANCHOR = re.compile(r"[\w./-]+\.\w+:[\w.$<>-]+")
GRILL_REF = re.compile(r"(?i)^(?:Q)?\d+$|^Q[\w-]+$")


class Finding:
    __slots__ = ("item", "rule", "detail")

    def __init__(self, item: str, rule: str, detail: str) -> None:
        self.item, self.rule, self.detail = item, rule, detail

    def __str__(self) -> str:
        return f"FAIL [{self.item}] {self.rule}\n       {self.detail}"


def grill_questions(home: Path) -> set[str]:
    """Question ids already raised in grill.md."""
    path = home / "grill.md"
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8", errors="replace")
    out = set()
    for m in re.finditer(r"(?mi)^\s*(?:[-*]\s*)?\**\s*(Q\d+|\d+)[.)、]?\s", text):
        q = m.group(1).upper()
        out.add(q if q.startswith("Q") else f"Q{q}")
    return out


def check_item(item: dict, grills: set[str], out: list[Finding]) -> None:
    iid = str(item.get("id", "?"))
    g = item.get("grounding")

    if not isinstance(g, dict):
        out.append(Finding(
            iid, "no-grounding",
            "没有 grounding 块 —— 这条需求落在哪段既有代码上?和什么冲突?边界在哪?"
            "密封之后再发现要 reopen,代价是 revision + 1 加旧 slice/case 全作废。"
            "`scripts/req-ground.py --schema` 看格式"))
        return

    touches = safeyaml.as_list(g.get("touches"))
    if not touches:
        out.append(Finding(iid, "no-touches",
                           "grounding.touches 为空 —— 需求不能脱离这个工程谈。"
                           "用 codegraph_context 找到它落在哪些 file:symbol 上"))
    else:
        bare = [str(t) for t in touches if not ANCHOR.search(str(t))]
        if bare:
            out.append(Finding(
                iid, "touches-not-anchored",
                f"touches 里 {len(bare)} 条没到 file:symbol:{bare[0][:50]} —— "
                "只写文件名没有信息量,写清是哪个符号"))

    # 冲突必须进 grill，不能记一笔就过去。
    for c in safeyaml.as_list(g.get("conflicts")):
        if not isinstance(c, dict):
            out.append(Finding(iid, "conflict-not-mapping", f"conflicts 有非 mapping 条目:{c!r}"))
            continue
        where = str(c.get("where") or "?")
        for key in ("existing", "tension"):
            if not str(c.get(key) or "").strip():
                out.append(Finding(
                    iid, f"conflict-no-{key}", f"conflicts[{where}] 缺 {key} —— "
                    + ("既有逻辑是怎么做的?" if key == "existing" else "本需求和它在哪一点上相悖?")))
        ref = str(c.get("grill") or "").strip().upper()
        if not ref:
            out.append(Finding(
                iid, "conflict-not-grilled",
                f"conflicts[{where}] 没挂 grill 问句 —— experts.md:"
                "「和已锁契约冲突却不写进问题」是拒过项。"
                "冲突不是记一笔就过去的事,要拷问到明确为止"))
        else:
            q = ref if ref.startswith("Q") else f"Q{ref}"
            if q not in grills:
                where_msg = ("grill.md 还不存在 —— 冲突记了一笔,但拷问从没发生过"
                             if not grills else "在 grill.md 里找不到")
                out.append(Finding(
                    iid, "grill-ref-dangling",
                    f"conflicts[{where}] 挂的 {q} {where_msg}。"
                    "experts.md:「和已锁契约冲突却不写进问题」是拒过项"))

    if not safeyaml.as_list(g.get("boundary")):
        out.append(Finding(iid, "no-boundary",
                           "grounding.boundary 为空 —— **明确不做什么**和做什么同样重要,"
                           "它是后面「为『更好』扩大范围」的那道闸"))

    if not str(g.get("direction") or "").strip():
        out.append(Finding(iid, "no-direction",
                           "grounding.direction 为空 —— 它和产品当前演进方向什么关系?"
                           "和哪条 ADR 一致或无关?"))

    # 竞品对比：差异要有理由，且差异大的要拷问。
    comp = item.get("comparison")
    if isinstance(comp, dict):
        peers = safeyaml.as_list(comp.get("peers"))
        if not peers:
            out.append(Finding(iid, "comparison-no-peers",
                               "有 comparison 块但没有 peers —— 和谁比?"))
        differs = str(comp.get("differs") or "").strip()
        if differs:
            if not str(comp.get("why") or "").strip():
                out.append(Finding(
                    iid, "differs-without-why",
                    f"和竞品有差异「{differs[:40]}」却没写 why —— "
                    "差异要么是有意的(说清理由),要么是没想到(那就是个问题)"))
            ref = str(comp.get("grill") or "").strip().upper()
            if not ref:
                out.append(Finding(
                    iid, "differs-not-grilled",
                    f"和竞品差异「{differs[:40]}」没挂 grill 问句 —— "
                    "与竞品相悖的决定要和人谈到明确,不是单方面记下来"))
            else:
                q = ref if ref.startswith("Q") else f"Q{ref}"
                if q not in grills:
                    where_msg = ("grill.md 还不存在 —— 差异记了一笔,但讨论从没发生过"
                                 if not grills else "在 grill.md 里找不到")
                    out.append(Finding(iid, "grill-ref-dangling",
                                       f"comparison 挂的 {q} {where_msg}"))


def probe(items: list) -> None:
    """What to go read, as commands. Not a substitute for reading it."""
    print("# 把需求落到代码上:先读,再写 grounding")
    print()
    print("每条 item 至少回答:它落在哪些既有符号上 · 和什么冲突 · 边界在哪 · 方向对不对")
    print()
    for item in items:
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id", "?"))
        must = str(item.get("must") or "")[:50]
        g = item.get("grounding") if isinstance(item.get("grounding"), dict) else {}
        touches = [str(t) for t in safeyaml.as_list(g.get("touches"))]
        print(f"## {iid}  {must}")
        if not touches:
            print(f"   codegraph_context \"{must}\"        # 先找落点")
            print("   ↑ 读完把 file:symbol 写进 grounding.touches")
        else:
            for t in touches[:4]:
                sym = t.split(":")[-1]
                print(f"   codegraph_impact {sym} --depth 1    # 谁调它 → grounding.impact")
            print(f"   codegraph_explore \"{' '.join(s.split(':')[-1] for s in touches[:3])}\"")
        print()
    print("读到和需求相悖的既有逻辑 → 写进 grounding.conflicts,并**挂一条 grill 问句**。")
    print("experts.md:「和已锁契约冲突却不写进问题」是拒过项。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--feature")
    parser.add_argument("--probe", action="store_true", help="what to go read")
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()

    if args.schema:
        print(SCHEMA)
        return 0
    if not args.feature:
        parser.error("--feature is required unless --schema")

    repo = args.repo or (Path(os.environ["IDEV_PRODUCT_REPO"])
                         if os.environ.get("IDEV_PRODUCT_REPO") else Path.cwd())
    home = doc_home.homes(repo.resolve(), args.feature)["task"]
    if not home.is_dir():
        print(f"BLOCKED no ticket home at {home}", file=sys.stderr)
        return 2

    baseline = safeyaml.mapping(home / "baseline.yaml")
    if baseline is None:
        print(f"BLOCKED cannot read {home / 'baseline.yaml'}", file=sys.stderr)
        return 2

    items = [i for i in safeyaml.as_list(baseline.get("items")) if isinstance(i, dict)]
    if args.probe:
        probe(items)
        return 0

    grills = grill_questions(home)
    findings: list[Finding] = []
    for item in items:
        check_item(item, grills, findings)

    grounded = sum(1 for i in items if isinstance(i.get("grounding"), dict))
    compared = sum(1 for i in items if isinstance(i.get("comparison"), dict))

    print(f"# req-ground  {args.feature}")
    print(f"# {len(items)} 条 item,{grounded} 条有 grounding,{compared} 条有竞品对比")
    print(f"# grill.md 里有 {len(grills)} 条问句")
    print()

    if findings:
        for f in findings:
            print(f)
        print()
        print(f"req-ground FAIL  {len(findings)} 处")
        print()
        print("**需求不能脱离这个工程谈。** 密封之后基线就是尺,而影响面原本要到 arch")
        print("才评估 —— 那时发现冲突只能 reopen(revision + 1,旧 slice / case 全作废)。")
        print("先读代码再密封:`--probe` 给出要跑的 codegraph 命令。")
        return 1

    print(f"req-ground PASS  {grounded}/{len(items)} 条已落到代码上")
    print()
    print("**落地了 ≠ 读对了。** 这里只查「功课交了没」:落点写了没、冲突挂没挂问句、")
    print("边界和方向写了没。读得对不对、对比公不公平、方向判断成不成立 ——")
    print("那是 grill 的事,要和人谈到所有细节明确无疑。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
