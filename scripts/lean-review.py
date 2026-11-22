#!/usr/bin/env python3
"""lean-review: which role lenses a ticket owes before seal / acceptance.

    lean-review.py assess --feature F [--repo DIR] [--stage req-review|arch]
    lean-review.py render  --feature F [--repo DIR] [--stage req-review|arch]

The seal-side challenge round (absorbed from joy-dev's multi-reviewer
re-audit, reshaped for idev): before `sealed` / `arch.accepted`, role
lenses — product, UI design, architect, developer, test, ops/SRE — read
the ticket from the outside and raise findings into the grill round. This
tool does NOT judge, gate, or score: it decides only WHICH lenses this
ticket can actually hit and prints the delegation lines, each naming the
lens's authority pages so the reviewer reads the ruler before raising
anything.

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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import doc_home  # noqa: E402
import safeyaml  # noqa: E402

STAGES = ("req-review", "arch")

# Each lens: what it challenges, and the ruler pages the brief must carry.
# The ruler is the point: a finding that cannot cite its ruler is padding.
LENSES = {
    "product": (
        "目标是否真解决问题、非目标是否藏了义务、验收是否可证伪",
        ("deliver/references/experts.md req-review 行", "deliver/references/req-quality.md"),
    ),
    "ui": (
        "交互完整性（error/loading/空态）、状态所有权、用户可感知边界",
        ("ui 块规则（ui-spec.py --schema）", "产线 vue 技能（--stage req-review）"),
    ),
    "architect": (
        "契约变更、数据真源、回退路径、被拒方案是否真被拒",
        ("conventions/canon.md §5 A1–A8", "conventions/domain-modeling.md"),
    ),
    "dev": (
        "可实现性：include 路径、既有债务（scope_debt）、验证入口存在",
        ("conventions/coding.md 底线", "对应语言规约（java.md / vue.md）"),
    ),
    "test": (
        "验收可证伪、维度表六族能否铺、断言是否用户现象",
        ("verify 维表", "deliver/references/experts.md test 行"),
    ),
    "ops": (
        "配置项语义、降级路径、观测面（指标/日志/告警）、回滚演练",
        ("conventions/canon.md A6", "产线 pack 运维知识（.idev/pack/agent-knowledge/；缺失则尺=A6）"),
    ),
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
    home = ticket(repo, feature)
    baseline = _load(home / "baseline.yaml")
    deliver = _load(home / "deliver.yaml")
    arch = _load(home / "arch.yaml")

    # --- trigger: absent a reason to run, say so and stop ----------------
    tier = str(deliver.get("risk_tier") or "").strip().upper()
    has_conflicts = any(
        isinstance(item, dict) and item.get("grounding", {}).get("conflicts")
        for item in (baseline.get("items") or [])
        if isinstance(item, dict)
    )
    has_assumptions = bool(baseline.get("assumptions"))
    triggered = tier == "P0" or has_conflicts or has_assumptions
    if not triggered:
        return {"decision": "SKIP", "reason": "risk_tier=%s, no grounding conflicts, no assumptions"
                % (tier or "unset(P1)")}

    # --- lens selection: only lenses this ticket can actually hit -------
    picks: list[str] = []
    picks.append("product")  # every ticket has a goal to challenge
    ui_items = any(
        isinstance(item, dict) and item.get("ui")
        for item in (baseline.get("items") or [])
        if isinstance(item, dict)
    )
    if ui_items:
        picks.append("ui")
    if stage == "arch" or (arch.get("impact_candidates")):
        picks.append("architect")
        picks.append("dev")
    if stage == "arch":
        picks.append("test")
    include = arch.get("include") if isinstance(arch.get("include"), list) else []
    config_touched = any(
        isinstance(p, str) and any(tok in p.lower() for tok in
                                   ("config", "deploy", "application", "bootstrap", "helm", "ops"))
        for p in include
    )
    if config_touched or stage == "arch":
        picks.append("ops")

    shards = []
    for lens in picks:
        challenge, rulers = LENSES[lens]
        shards.append({
            "id": lens,
            "scope": (
                "%s 视角再审；只挑疑问不改工件；每条 finding 必须引用领域尺原文"
                "（%s）并写失败场景；零 finding 合法且要明说；"
                "拿不到的事实回 UNPROVEN(事实) 不猜；产出是 grill.md 轮的候选问句"
                "（❓/➡️ 格式 + 来源：lean-review %s）" % (lens, "；".join(rulers), lens)
            ),
            "challenge": challenge,
            "rulers": list(rulers),
        })
    return {"decision": "LENS", "stage": stage, "shards": shards}


def render(result: dict, feature: str) -> str:
    if result["decision"] == "SKIP":
        return "\n".join([
            "SKIP lean-review %s" % result["reason"],
            "DOCK LENS-SKIP 触发条件未命中（P0 / grounding.conflicts / assumptions / 人点名）；"
            "不跑不违规，本工具不是门禁",
        ])
    lines = [
        "LENS lean-review stage=%s %d 视角" % (result["stage"], len(result["shards"])),
        "DOCK LENS-ROUND 密封/accepted 前的独立挑战轮；产出归并进 grill.md 轮次，不另开文件",
    ]
    for shard in result["shards"]:
        lines.append("SHARD %s" % shard["id"])
        lines.append("SCOPE %s" % shard["scope"])
    lines.append(
        "NOTE 三律：引不出尺的问题删；问题必带失败场景；零 finding 合法且要明说。"
        "finding 全部转成 grill 轮问句（带来源行），照常一轮问完，不另请签。"
    )
    return "\n".join(lines)


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
