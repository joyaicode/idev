#!/usr/bin/env python3
"""lean-review: which role lenses a ticket owes at each stage gate.

    lean-review.py assess --feature F [--repo DIR] --stage S
    lean-review.py render  --feature F [--repo DIR] --stage S

The challenge round (absorbed from joy-dev's multi-reviewer re-audit,
reshaped for idev): role lenses — product, UI design, architect,
developer, test, ops/SRE — read the ticket from the outside and raise
findings. This tool does NOT judge, gate, or score: it decides only WHICH
lenses this ticket can actually hit at THIS stage, and where the findings
merge — each stage has its own carrier:

    req-review / arch  -> grill.md questions (the person answers)
    code               -> review.md I*/P# (review.fix, no person asked)
    test               -> dimension-table UNPROVEN or missing cases
    ops                -> hypothesis ledger entries (falsifiable actions)

Stages with an existing delegation wave (code/test/ops) merge the lenses
INTO that wave's brief — no second dispatch. Only req-review / arch
(which have no reviewer wave) dispatch independent sub-agents. The
trigger stays the same three conditions plus the stage's natural gate;
no new stops, no machine checks.

Trigger (any): risk_tier P0, or the ticket admits its own premise risk
(grounding.conflicts / assumptions non-empty), or the person names the
round. Absent those, skipping lean-review is legal — this is an
amplifier, not a gate, and check-feature never asks for it.

Three anti-padding rules live in the prompt pages, not here: a finding
must cite the ruler it violates, must name the failure scenario, and zero
findings is a legal verdict that must be said aloud.

Exit: 0 printed the roster (possibly "no lenses: <reason>").
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import termview  # noqa: E402
import doc_home  # noqa: E402
import safeyaml  # noqa: E402

STAGES = ("req-review", "arch", "code", "test", "ops")

# Each lens: what it challenges per stage, the ruler pages the brief must
# carry, and where findings merge at that stage. The ruler is the point: a
# finding that cannot cite its ruler is padding. The merge target is the
# point too: a finding routed to the wrong carrier either wakes the person
# for something review.fix would have fixed, or vice versa.
LENSES = {
    "product": {
        "req-review": (
            "目标是否真解决问题、非目标是否藏了义务、验收是否可证伪",
            ("deliver/references/experts.md req-review 行", "deliver/references/req-quality.md"),
            "grill",
        ),
        "ops": (
            "现象是否涉用户可感知行为、修复是否改变对外承诺",
            ("deliver/references/experts.md req-review 行", "baseline（尺仍是密封基线）"),
            "hypothesis",
        ),
        "arch": (
            "方案是否真解决密封目标、范围是否越过基线、验收是否被方案悄悄改写",
            ("deliver/references/experts.md arch 行", "密封 baseline（尺）"),
            "grill",
        ),
    },
    "ui": {
        "req-review": (
            "交互完整性（error/loading/空态）、状态所有权、用户可感知边界",
            ("ui 块规则（ui-spec.py --schema）", "产线 vue 技能（--stage req-review）"),
            "grill",
        ),
        "test": (
            "ui-prototype/ui 族断言是否落在用户可感知行为上",
            ("verify/references/plan-schema.md 维表六族", "产线 vue 技能（--stage test）"),
            "dimension-table",
        ),
    },
    "architect": {
        "arch": (
            "契约变更、数据真源、回退路径、被拒方案是否真被拒",
            ("conventions/canon.md §5 A1–A8", "conventions/domain-modeling.md"),
            "grill",
        ),
    },
    "dev": {
        "arch": (
            "可实现性：include 路径、既有债务（scope_debt）、验证入口存在",
            ("conventions/coding.md 底线", "对应语言规约（java.md / vue.md）"),
            "grill",
        ),
        "code": (
            "异常处理与降级、无依据代码、只有 get/set 的哑对象、关键路径质量",
            ("conventions/coding.md 文首底线与 §0/§2", "conventions/coding-tables.md §2", "conventions/canon.md §6 F1–F7"),
            "review-md",
        ),
        "ops": (
            "修复是否落在产生现象的那一层、是否在错误修复上叠补丁",
            ("conventions/evidence.md 闭环 5/6", "scripts/failure_signature.py 有界修复红线"),
            "hypothesis",
        ),
    },
    "test": {
        "arch": (
            "验收可证伪、维度表六族能否铺、断言是否用户现象",
            ("verify 维表", "deliver/references/experts.md test 行"),
            "grill",
        ),
        "code": (
            "自测是否覆盖影响面、断言是否用户现象而非进程没挂",
            ("verify/references/plan-schema.md", "conventions/evidence.md 红绿判据"),
            "review-md",
        ),
        "test": (
            "六族覆盖缺口、UNPROVEN 是否被沉默、弱断言",
            ("verify/references/unproven-gate.md", "deliver/references/experts.md test 行"),
            "dimension-table",
        ),
    },
    "ops": {
        "arch": (
            "配置项语义、降级路径、观测面（指标/日志/告警）、回滚演练",
            ("conventions/canon.md A6", "产线 pack 运维知识（.idev/pack/agent-knowledge/；缺失则尺=A6）"),
            "grill",
        ),
        "code": (
            "关键路径异常处理、回退是否可执行、观测面是否随行为变更",
            ("conventions/canon.md A6", "conventions/coding.md 关键路径底线"),
            "review-md",
        ),
        "test": (
            "UNPROVEN 的部署现实性、回滚演练是否在提测包里",
            ("conventions/canon.md A6", "verify/references/unproven-gate.md"),
            "dimension-table",
        ),
        "ops": (
            "假设是否可证伪、证据链断点、变更记录是否查过、可观察物过没过质量线（日志定位到层/告警带行动项/指标对时间窗）",
            ("conventions/evidence.md 闭环与排查递进", "ops/references/classify.md 可观察物质量线", "产线 pack 运维知识（缺失则尺=evidence.md）"),
            "hypothesis",
        ),
    },
}

# What each merge target means for the brief text.
MERGE_HINTS = {
    "grill": "产出是 grill.md 轮的候选问句（❓/➡️ 格式 + 来源：lean-review <视角>）",
    "review-md": "产出是 review.md 的 I*/P# 条目（走既有 review.fix，accept_all_findings，不问人）",
    "dimension-table": "产出是维表 UNPROVEN 修正或补 case（unproven.md），不是新文件",
    "hypothesis": "产出是 hypothesis.py 新假设条目（可证伪动作 + 证据路径），不进 grill",
}


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        doc = safeyaml.mapping_from_text(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return doc if isinstance(doc, dict) else {}


def ticket(repo: Path, feature: str) -> Path:
    return doc_home.homes(repo, feature)["task"]


def assess(repo: Path, feature: str, stage: str) -> dict:
    if stage not in STAGES:
        raise ValueError(stage)
    home = ticket(repo, feature)
    baseline = _load(home / "baseline.yaml")
    deliver = _load(home / "deliver.yaml")
    arch = _load(home / "arch.yaml")
    ops_doc = _load(home / "ops.yaml")

    # --- trigger: absent a reason to run, say so and stop ----------------
    # Same three conditions at every stage; the stage's natural gate is the
    # timing, not the trigger.
    tier = str(deliver.get("risk_tier") or "").strip().upper()
    has_conflicts = any(
        isinstance(item, dict) and item.get("grounding", {}).get("conflicts")
        for item in (baseline.get("items") or [])
        if isinstance(item, dict)
    )
    has_assumptions = bool(baseline.get("assumptions"))
    if stage == "ops":
        # An ops ticket exists because something went wrong; the challenge
        # round is the closed loop's own step, not an extra.
        triggered = True
    else:
        triggered = tier == "P0" or has_conflicts or has_assumptions
    if not triggered:
        return {"decision": "SKIP", "reason": "risk_tier=%s, no grounding conflicts, no assumptions"
                % (tier or "unset(P1)")}

    # --- candidates: lenses defined for this stage, narrowed by content --
    candidates = sorted(LENSES)
    ui_items = any(
        isinstance(item, dict) and item.get("ui")
        for item in (baseline.get("items") or [])
        if isinstance(item, dict)
    )
    include = arch.get("include") if isinstance(arch.get("include"), list) else []
    config_touched = any(
        isinstance(p, str) and any(tok in p.lower() for tok in
                                   ("config", "deploy", "application", "bootstrap", "helm", "ops"))
        for p in include
    )
    phenomenon = str(ops_doc.get("phenomenon") or "")
    user_visible = any(w in phenomenon for w in ("用户", "页面", "接口", "console", "控制台", "user"))

    picks: list[str] = []
    for lens in candidates:
        if stage not in LENSES[lens]:
            continue
        if lens == "ui" and stage in ("req-review", "test") and not ui_items:
            continue
        if lens == "product" and stage == "ops" and not user_visible:
            continue
        picks.append(lens)
    # Stage floor: the gate a stage owns implies its own lenses.
    if stage == "arch":
        for must in ("architect", "dev", "test", "ops"):
            if must not in picks:
                picks.append(must)
    if stage == "code":
        for must in ("dev", "test", "ops"):
            if must not in picks:
                picks.append(must)
    if stage == "test":
        for must in ("test", "ops"):
            if must not in picks:
                picks.append(must)
        if ui_items and "ui" not in picks:
            picks.append("ui")
    if stage == "ops":
        for must in ("ops", "dev"):
            if must not in picks:
                picks.append(must)

    shards = []
    for lens in picks:
        challenge, rulers, merge = LENSES[lens][stage]
        hint = MERGE_HINTS[merge]
        shards.append({
            "id": lens,
            "scope": (
                "%s 视角再审（%s 阶段）；只挑疑问不改工件；每条 finding 必须引用领域尺原文"
                "（%s）的具体条款出处并写失败场景，且标注【阻塞】或【建议】；"
                "零 finding 合法且要明说；拿不到的事实回 UNPROVEN(事实) 不猜；"
                "旧 finding 不推定本轮仍成立，参与过修复的镜头本轮更换；%s"
                % (lens, stage, "；".join(rulers), hint)
            ),
            "challenge": challenge,
            "rulers": list(rulers),
            "merge": merge,
        })
    order = {"product": 0, "ui": 1, "architect": 2, "dev": 3, "test": 4, "ops": 5}
    shards.sort(key=lambda s: order[s["id"]])
    return {"decision": "LENS", "stage": stage, "shards": shards}


# Per-stage dispatch notes: stages with an existing delegation wave merge
# the lenses into that wave's brief (one dispatch, not two); only
# req-review / arch dispatch independent sub-agents. This is the line
# between "multi-role" and "double dispatch".
WAVE_MERGE = {
    "req-review": "独立子代理（本阶段无既有审查波）；finding 转 grill.md 问句",
    "arch": "独立子代理（本阶段无既有审查波）；finding 转 grill.md ## arch 轮问句",
    "code": "并入既有 idev-reviewer 波（同一波四件之一）：镜头清单附进 reviewer 委派包，同一上下文按镜头过，不另派子代理；finding 写 review.md I*/P#。五轴分片（单模块 FANOUT）时镜头清单附进 lens-correctness 片的委派包",
    "test": "并入既有 idev-verifier 波：镜头附进 verifier 委派包；finding 修维表 UNPROVEN 或补 case",
    "ops": "并入既有 idev-ops 委派：镜头附进 ops 委派包；finding 进假设台账",
}


def render(result: dict, feature: str) -> str:
    if result["decision"] == "SKIP":
        return "\n".join([
            "SKIP lean-review %s" % result["reason"],
            "DOCK LENS-SKIP 触发条件未命中（P0 / grounding.conflicts / assumptions / 人点名）；"
            "不跑不违规，本工具不是门禁",
        ])
    stage = result["stage"]
    lines = [
        termview.paint("LENS lean-review stage=%s %d 视角" % (stage, len(result["shards"])), "HEAD"),
        "DOCK LENS-ROUND %s" % WAVE_MERGE[stage],
    ]
    for shard in result["shards"]:
        lines.append(termview.paint("SHARD %s" % shard["id"], "HINT") + "  " + shard["challenge"])
        lines.append("SCOPE %s" % _linkify(shard["scope"]))
    lines.append(
        "NOTE 五律：引不出尺的问题删；问题必带失败场景与条款出处；标注【阻塞】或【建议】；"
        "零 finding 合法且要明说；旧 finding 不推定本轮仍成立，参与过修复的镜头更换。"
        "finding 按 %s 归并，不另开文件、不另请签、不新停点。" % _merge_note(result["shards"])
    )
    return "\n".join(lines)


_RULER_PATH = re.compile(r"(?<![\w/.])((?:deliver|references|conventions|verify|ops|agents)/[\w./-]+)")


def _linkify(text: str) -> str:
    """Make ruler paths clickable in a terminal; pipes keep plain text."""
    def repl(m: re.Match) -> str:
        rel = m.group(1).rstrip("。，；）")
        tail = m.group(1)[len(rel):]
        # Ruler mentions name a kernel page; only real files link.
        cand = Path(__file__).resolve().parents[1] / rel
        if not cand.is_file():
            return m.group(1)
        return termview.link(rel, str(cand)) + tail
    return _RULER_PATH.sub(repl, text)


def _merge_note(shards: list[dict]) -> str:
    merges = []
    for shard in shards:
        hint = MERGE_HINTS[shard["merge"]]
        if hint not in merges:
            merges.append(hint)
    return "；".join(merges)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cmd", choices=["assess", "render"])
    parser.add_argument("--feature", required=True)
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--stage", choices=STAGES, default="req-review")
    args = parser.parse_args(argv)
    repo = (args.repo or Path.cwd()).resolve()
    result = assess(repo, args.feature, args.stage)
    print(render(result, args.feature))
    return 0


if __name__ == "__main__":
    sys.exit(main())
