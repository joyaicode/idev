#!/usr/bin/env python3
"""Stage gates: the experts.md reject-lists, made machine-checkable.

    stage-gate.py --feature F --stage STAGE [--repo DIR]
    stage-gate.py --feature F --all
    stage-gate.py --list

deliver/references/experts.md has carried a good reject-list per stage for a
long time, but nothing executed it: "过清单后才能请人签字" was enforced by
whoever remembered to look. check-feature.py checks *structure* (is the
field there, does the text match the baseline) — not whether the content
meets the professional standard of that role.

This closes that gap for the parts a machine can honestly judge.

## What it can and cannot decide

It checks **the mechanical half** of each reject-list:

  - 验收含主观词(合理/友好/流畅)不可测        — a word list decides this
  - goal 无可量化指标                          — look for a number with a unit
  - slice 故事 > 8 点未拆                      — read the number
  - 影响面只有 hop 0                           — count the hops
  - PASS 却没有证据路径                        — check the path exists
  - 根因未复现就下结论                         — read repro/status

It cannot decide **the judgement half** — whether a decomposition is
faithful, whether an architecture is sound, whether a test is meaningful.
Those stay with the专家拒过清单 for the person and the grill. A finding
here is "this cannot be right"; silence here is NOT "this is right".

That distinction is the whole point. A gate that claimed to judge quality
would be the score-gate the kernel forbids (verify/references/evolve.md),
and worse, it would make people stop looking.

Exit: 0 clean, 1 findings, 2 cannot read the inputs.
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
import ticketless  # noqa: E402

sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
try:
    import doc_home  # noqa: E402
except ImportError:
    print(f"BLOCKED cannot import doc_home from {kind_agents.kernel_root()}", file=sys.stderr)
    raise SystemExit(2) from None

STAGES = ("req-review", "req", "arch", "code", "test", "ops")

# experts.md req-review: 「验收含主观词(合理/友好/流畅)不可测」. These are the
# words that make an acceptance criterion untestable — two people reading it
# disagree about whether it was met, and neither can prove the other wrong.
VAGUE = (
    "合理", "友好", "流畅", "优雅", "简洁明了", "良好", "完善", "健壮",
    "高效", "快速", "稳定", "可靠", "方便", "易用", "清晰", "美观",
    "尽量", "尽可能", "适当", "适度", "必要时", "酌情",
)
# A measurable criterion carries a number with a unit, or an explicit
# comparison. Not proof of quality — just evidence someone tried.
MEASURABLE = re.compile(
    r"\d+\s*(?:ms|s|秒|分钟|min|%|％|次|条|个|人|QPS|TPS|MB|GB|KB|px|倍)"
    r"|[<>≤≥]=?\s*\d|不超过\s*\d|至少\s*\d|不少于\s*\d|等于\s*\d"
)
# experts.md arch: 「与现有 SPI / 路由契约重复发明」— a solution word in a
# requirement is the 「用解决方案冒充需求」 smell.
SOLUTION_WORDS = ("用 Redis", "用 Kafka", "加缓存", "加一层", "改成微服务", "引入消息队列")


class Finding:
    __slots__ = ("stage", "rule", "where", "detail")

    def __init__(self, stage: str, rule: str, where: str, detail: str) -> None:
        self.stage, self.rule, self.where, self.detail = stage, rule, where, detail

    def __str__(self) -> str:
        return f"FAIL [{self.stage}] {self.rule}  {self.where}\n       {self.detail}"


def text_of(value: object) -> str:
    """Flatten a yaml value to searchable text."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(text_of(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(text_of(v) for v in value)
    return str(value or "")


def vague_hits(text: str) -> list[str]:
    return [w for w in VAGUE if w in text]


# --- req-review: 资深产品 / 领域评审 ---------------------------------------

def gate_req_review(home: Path, out: list[Finding]) -> None:
    baseline = safeyaml.mapping(home / "baseline.yaml")
    if baseline is None:
        out.append(Finding("req-review", "inputs", "baseline.yaml", "缺失或不是 mapping —— 这一格还没开始,或文件写坏了。`check-feature.sh <f> req-review` 看结构"))
        return

    items = safeyaml.as_list(baseline.get("items"))
    if not items:
        out.append(Finding("req-review", "no-items", "baseline.yaml", "没有 items,无法评审 —— 每条义务一个 item,带 must 与可证伪的 acceptance"))

    for item in items:
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id", "?"))
        # Only the documented key. Accepting an undocumented Chinese alias
        # means two people writing from two sources produce different
        # tickets — and whichever key a check forgets, it silently passes.
        accept = text_of(item.get("acceptance") or "")
        must = text_of(item.get("must") or "")

        # 拒过:验收含主观词不可测
        if accept:
            hits = vague_hits(accept)
            if hits:
                out.append(Finding(
                    "req-review", "untestable-acceptance", f"items[{iid}].acceptance",
                    f"含主观词 {'/'.join(hits)} —— 两个人读它会得出不同结论。"
                    f"改成可证伪的说法(谁在什么条件下观察到什么)"))
            elif not MEASURABLE.search(accept):
                out.append(Finding(
                    "req-review", "unmeasurable-acceptance", f"items[{iid}].acceptance",
                    "没有带单位的数字或显式比较 —— 怎么判断它达到了?"))
        else:
            out.append(Finding(
                "req-review", "no-acceptance", f"items[{iid}]",
                "没有验收标准 —— 这条 item 无法证伪"))

        # must 同样不能含主观词。原本只查 acceptance —— 但「要给出友好的提示」
        # 写在 must 里一样不可测,而且它会被原文锁带进 slice,一路传到下游。
        if must:
            hits = vague_hits(must)
            if hits:
                out.append(Finding(
                    "req-review", "untestable-must", f"items[{iid}].must",
                    f"含主观词 {'/'.join(hits)} —— must 会被原文锁带进 slice 一路传到下游,"
                    "含糊的义务在每一格都会被重新解释一遍"))

        # 拒过:用解决方案冒充需求
        for w in SOLUTION_WORDS:
            if w in must:
                out.append(Finding(
                    "req-review", "solution-as-requirement", f"items[{iid}].must",
                    f"「{w}」是解决方案不是需求。需求说要达成什么,方案在 arch 阶段定"))
                break

    # 拒过:objections 未清空
    objections = safeyaml.as_list(baseline.get("objections"))
    if objections:
        out.append(Finding("req-review", "open-objections", "baseline.yaml",
                           f"还有 {len(objections)} 条未清空的 objections"))

    # 需求脱离工程谈 = 影响面要到 arch 才发现，那时只能 reopen。
    # 只在已密封或准备密封时要求：起草中的基线还在收集阶段。
    if baseline.get("sealed"):
        ungrounded = [str(i.get("id", "?")) for i in items
                      if isinstance(i, dict) and not isinstance(i.get("grounding"), dict)]
        if ungrounded:
            out.append(Finding(
                "req-review", "not-grounded", f"items[{', '.join(ungrounded[:4])}]",
                f"{len(ungrounded)} 条 item 没有 grounding 块 —— 需求没落到既有代码上就密封了。"
                "影响面原本要到 arch 才评估,那时发现冲突只能 reopen。"
                "`scripts/req-ground.py --probe` 给出要读什么"))

    # 界面类需求没有 ui 规则 = 交互留给实现阶段各自发挥，测试阶段没有尺可量。
    # 只对看起来涉及界面的 item 要求，避免纯后端票被迫编一个 ui 块。
    for item in items:
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id", "?"))
        blob = text_of(item.get("must")) + " " + text_of(item.get("acceptance"))
        looks_ui = re.search(
            r"页面|界面|按钮|表单|弹窗|列表|输入|点击|提示|展示|跳转|下拉|勾选|UI|前端", blob)
        if looks_ui and not isinstance(item.get("ui"), dict):
            out.append(Finding(
                "req-review", "ui-not-specified", f"items[{iid}]",
                "看起来是界面需求但没有 ui 块 —— 交互细到字段校验/动作结果/加载失败状态,"
                "评审时才看得见分歧。`scripts/ui-spec.py --schema` 看格式"))

    goal = text_of(baseline.get("goal"))
    if goal:
        hits = vague_hits(goal)
        if hits:
            out.append(Finding("req-review", "vague-goal", "baseline.goal",
                               f"含主观词 {'/'.join(hits)}"))


# --- req: 资深分析 ----------------------------------------------------------

def gate_req(home: Path, out: list[Finding]) -> None:
    req = safeyaml.mapping(home / "req.yaml")
    if req is None:
        out.append(Finding("req", "inputs", "req.yaml", "缺失或不是 mapping —— 拆解还没做,或文件写坏了"))
        return
    baseline = safeyaml.mapping(home / "baseline.yaml") or {}

    slices = safeyaml.as_list(req.get("slices"))
    if not slices:
        out.append(Finding("req", "no-slices", "req.yaml", "没有 slices —— 把每条基线 item 译成可执行的 slice,挂 baseline_item_id"))

    for s in slices:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id", "?"))
        # 拒过:故事 > 8 点未拆
        pts = s.get("points") or s.get("story_points")
        if pts is not None:
            n = safeyaml.as_int(pts, 0)
            if n > 8:
                out.append(Finding("req", "story-too-big", f"slices[{sid}].points",
                                   f"{n} 点 > 8,INVEST 的 Small 不过,先拆"))
        # 拒过:新增基线没有的义务（原文锁由 check-feature 管，这里只查挂钩）
        if not str(s.get("baseline_item_id") or "").strip():
            out.append(Finding("req", "unanchored-slice", f"slices[{sid}]",
                               "没挂 baseline_item_id —— 它从哪条基线来的?"))

    # 拒过:丢掉基线一条 item
    covered = {str(s.get("baseline_item_id")) for s in slices if isinstance(s, dict)}
    for item in safeyaml.as_list(baseline.get("items")):
        if isinstance(item, dict):
            iid = str(item.get("id", ""))
            if iid and iid not in covered:
                out.append(Finding("req", "dropped-baseline-item", f"baseline.items[{iid}]",
                                   "没有任何 slice 覆盖它 —— 丢了还是故意不做?"))


# --- arch: 资深架构 ---------------------------------------------------------

def gate_arch(home: Path, out: list[Finding]) -> None:
    arch = safeyaml.mapping(home / "arch.yaml")
    if arch is None:
        out.append(Finding("arch", "inputs", "arch.yaml", "缺失或不是 mapping —— 架构方案还没写,或文件写坏了"))
        return

    intents = safeyaml.as_list(arch.get("case_intents"))
    for ci in intents:
        if isinstance(ci, dict) and not str(ci.get("baseline_item_id") or "").strip():
            out.append(Finding("arch", "unanchored-intent",
                               f"case_intents[{ci.get('id', '?')}]",
                               "没挂 baseline_item_id"))

    # 拒过:影响面诚实 —— 只写 hop 0 等于没评估影响面
    inc = [p for p in safeyaml.as_list(arch.get("include")) if p]
    if inc and not safeyaml.as_list(arch.get("impact_candidates")):
        out.append(Finding("arch", "no-impact", "arch.yaml",
                           f"要改 {len(inc)} 处却没有 impact_candidates —— "
                           "用 codegraph_impact --depth 1 提名调用方"))

    # A changed-behaviour plan with no rollback thought is the one thing an
    # architecture review should never let through silently.
    body = text_of(arch)
    if not re.search(r"回退|rollback|灰度|开关|feature flag|降级", body):
        out.append(Finding("arch", "no-rollback", "arch.yaml",
                           "没提回退 / 灰度 / 开关 —— 上线后出问题怎么退?"))


# --- code: 资深开发 + Review ------------------------------------------------

def gate_code(home: Path, out: list[Finding]) -> None:
    review = home / "review.md"
    if not review.is_file():
        out.append(Finding("code", "inputs", "review.md", "缺失 —— 编码阶段要留 review.md,写明 §1 扫表结果与五轴"))
        return
    text = review.read_text(encoding="utf-8", errors="replace")

    # 拒过:review 仍是 P? / C?（check-feature 也查，这里给出可操作的说明）
    if re.search(r"\bP\?|\bC\?", text):
        out.append(Finding("code", "placeholder-codes", "review.md",
                           "还有 P? / C? 占位 —— 要么写出命中的编号,要么写零命中"))
    # 拒过:气味命中只记账未改
    for m in re.finditer(r"(?m)^.*\b([PC]\d+)\b.*$", text):
        line = m.group(0)
        if re.search(r"待改|稍后|下轮|TODO|暂不", line):
            out.append(Finding("code", "hit-not-applied", f"review.md: {m.group(1)}",
                               f"命中标成待改:{line.strip()[:60]} —— 命中必须当轮改掉"))


# --- test: 资深测试 ---------------------------------------------------------

def gate_test(home: Path, out: list[Finding]) -> None:
    plan = safeyaml.mapping(home / "verify" / "plan.yaml")
    if plan is None:
        out.append(Finding("test", "inputs", "verify/plan.yaml", "缺失或不是 mapping —— 用例计划还没起草。`verify` 模块的 plan 骨架先铺维度表"))
        return

    cases = safeyaml.as_list(plan.get("cases"))
    if not cases:
        out.append(Finding("test", "no-cases", "plan.yaml", "没有 cases —— 先按维度表铺满骨架,再逐条填断言"))

    for c in cases:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id", "?"))
        status = str(c.get("status", ""))
        # 拒过:未确认环境/产物却写 PASS（证据路径是最低限度的确认）
        if status.upper() == "PASS" and not str(c.get("evidence") or "").strip():
            out.append(Finding("test", "pass-without-evidence", f"cases[{cid}]",
                               "PASS 却没有 evidence 路径"))
        # 拒过:对基线 item 无 case —— 反向：case 不挂 item。
        # needs_ticket:false 且没有 baseline.yaml 时，case 不挂基线条目。
        if not ticketless.skips_baseline(home) and not str(c.get("baseline_item_id") or "").strip():
            out.append(Finding("test", "unanchored-case", f"cases[{cid}]",
                               "没挂 baseline_item_id —— 它在证明哪条基线?"))
        # 断言是「进程没挂」这类无效断言
        assertion = text_of(c.get("assert") or "")
        if assertion and re.search(r"不报错|没有异常|进程还在|返回\s*200\s*$|能启动", assertion):
            out.append(Finding("test", "weak-assertion", f"cases[{cid}].assert",
                               f"「{assertion[:40]}」断言的是「没崩」,不是用户那条现象"))


# --- ops: 资深排障 ----------------------------------------------------------

def gate_ops(home: Path, out: list[Finding]) -> None:
    ops = safeyaml.mapping(home / "ops.yaml")
    if ops is None:
        out.append(Finding("ops", "inputs", "ops.yaml", "缺失或不是 mapping —— 还没做现象分类"))
        return

    # 拒过:现场四件齐
    for field, label in (("phenomenon", "现象"), ("env", "环境"),
                         ("artifact", "产物"), ("observable", "可观察物")):
        if not str(ops.get(field) or "").strip():
            out.append(Finding("ops", "scene-incomplete", f"ops.{field}",
                               f"缺{label} —— 现场四件不齐不能下结论"))

    kind = str(ops.get("kind") or "unknown")
    if kind == "unknown" and str(ops.get("root_cause") or "").strip():
        out.append(Finding("ops", "conclusion-before-classify", "ops.yaml",
                           "kind 还是 unknown 却已经写了根因 —— 先分类再取证"))

    # 拒过:猜根因未复现
    if str(ops.get("root_cause") or "").strip():
        repro = str(ops.get("repro") or ops.get("reproduced") or "").lower()
        if repro not in ("yes", "true", "1", "已复现"):
            out.append(Finding("ops", "rootcause-without-repro", "ops.root_cause",
                               f"写了根因但 repro={repro or '未填'} —— "
                               "未在用户同一现象上红过一次,不写根因"))

    # 拒过:自动做生产写
    body = text_of(ops)
    for danger in ("kubectl patch", "重启生产", "failover", "告警屏蔽", "直接改线上"):
        if danger in body:
            out.append(Finding("ops", "production-write", "ops.yaml",
                               f"提到「{danger}」—— 生产写操作须人判定,预案只写出来"))
            break


GATES = {
    "req-review": gate_req_review,
    "req": gate_req,
    "arch": gate_arch,
    "code": gate_code,
    "test": gate_test,
    "ops": gate_ops,
}


def gate_check() -> list[str]:
    """STAGES 与 GATES 必须一一对应。

    A stage listed but not wired silently checks nothing; a gate not listed
    never runs under --all. Either way the gap is invisible at the call site.
    """
    out = []
    for s in STAGES:
        if s not in GATES:
            out.append(f"{s} 在 STAGES 里但没有 gate 函数 —— 它什么都不查")
    for s in GATES:
        if s not in STAGES:
            out.append(f"{s} 有 gate 函数但不在 STAGES 里 —— --all 不会跑它")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout (default: cwd)")
    parser.add_argument("--feature")
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--all", action="store_true", help="run every stage whose inputs exist")
    parser.add_argument("--list", action="store_true", help="list the stages and what each checks")
    args = parser.parse_args()

    if args.list:
        print("stage-gate — experts.md 拒过清单里可机检的那一半\n")
        for s in STAGES:
            print(f"  {s}")
        print("\n不可机检的那一半(拆解是否忠实、架构是否合理、用例是否有意义)")
        print("仍在 deliver/references/experts.md,交人与 grill。")
        print("\n**有发现 = 这里一定有问题;没发现 ≠ 这里没问题。**")
        return 0

    if not args.feature:
        parser.error("--feature is required unless --list")
    if not args.stage and not args.all:
        parser.error("pass --stage or --all")

    repo = args.repo or (Path(os.environ["IDEV_PRODUCT_REPO"])
                         if os.environ.get("IDEV_PRODUCT_REPO") else Path.cwd())
    home = doc_home.homes(repo.resolve(), args.feature)["task"]
    if not home.is_dir():
        print(f"BLOCKED no ticket home at {home}", file=sys.stderr)
        return 2

    stages = [args.stage] if args.stage else list(STAGES)
    findings: list[Finding] = [
        Finding("stage-gate", "internal-inconsistency", "stage-gate.py", p)
        for p in gate_check()
    ]
    ran: list[str] = []
    for s in stages:
        if args.all:
            # --all only runs a gate whose primary input exists, so an early
            # ticket does not drown in "not written yet".
            probe = {"req-review": "baseline.yaml", "req": "req.yaml", "arch": "arch.yaml",
                     "code": "review.md", "test": "verify/plan.yaml", "ops": "ops.yaml"}[s]
            if not (home / probe).exists():
                continue
        ran.append(s)
        GATES[s](home, findings)

    # A corrected baseline needs realign as well: stage-gate reads each
    # stage's own file, so it cannot see that a PASS case is still anchored
    # to an item the correction removed. Running only this one leaves the
    # most dangerous drift invisible.
    deliver = safeyaml.mapping(home / "deliver.yaml") or {}
    baseline_now = safeyaml.mapping(home / "baseline.yaml") or {}
    corrected = bool(deliver.get("reopen_baseline") or deliver.get("last_rewind")
                     or safeyaml.as_int(baseline_now.get("revision"), 1) > 1)

    print(f"# stage-gate  {args.feature}")
    print(f"# {home}")
    print(f"# stages: {', '.join(ran) or '(none)'}")
    print()
    if corrected:
        print("NOTE 这张票的基线被订正过(reopen / 回退 / revision > 1)。")
        print("     **本工具按阶段各查各的文件,看不出「一条 PASS 还挂在已删除的 item 上」。**")
        print(f"     那类漂移要跑:python3 scripts/realign.py --feature {args.feature}")
        print()
    if findings:
        for f in findings:
            print(f)
        print()
        print(f"stage-gate FAIL  {len(findings)} finding(s)")
        print("这些是**可机检的那一半**。专业判断(拆解是否忠实 / 架构是否合理 /")
        print("用例是否有意义)仍要人按 deliver/references/experts.md 过一遍。")
        return 1

    print(f"stage-gate PASS  {len(ran)} stage(s), 0 findings")
    print()
    print("**没发现 ≠ 没问题。** 这里只查机器能判的那一半;拒过清单的另一半")
    print("(专业判断)仍要人过 —— experts.md,以及 grill。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
