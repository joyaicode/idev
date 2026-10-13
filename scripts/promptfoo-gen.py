#!/usr/bin/env python3
"""Generate a promptfoo config that regression-tests the agent definitions.

    promptfoo-gen.py [--out DIR] [--agent NAME]

What it asserts: **shape and boundary, never quality.**

  - the report carries STATUS / EVIDENCE / CHECKS / SUGGEST
  - BLOCKED is classified (brief / env / logic), so metrics can attribute it
  - FACTS names a first-hand source — not "the document"
  - DOC_DRIFT is declared (even as 无)
  - idev-coder declares coding.md §0 (CHANGE_KIND / CANON_TRIGGER / TABLE_HIT)
  - nothing claims to have written sealed / accepted / aligned / resolved

Why no scoring: verify/references/evolve.md forbids score gates and
LLM-as-judge rubber stamps. A model grading "was this review insightful"
would be exactly that. So every assertion here is a `contains` or a
`not-contains` a person can verify by reading — the same standard the rest
of this layer holds itself to.

This is a **regression harness for prompt edits**: change a definition, run
it, and find out whether the agent still produces a parseable, in-bounds
report. Whether the report is any *good* is answered by a real ticket
(references/agents-todo.md P1), not here.

promptfoo is not required to generate the config — only to run it:

    npx promptfoo@latest eval -c <out>/promptfooconfig.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

SIGNOFF = ("sealed: true", "accepted: true", "aligned: true", "resolved: true")

# One probe per agent: a brief complete enough that a correct agent has no
# excuse to BLOCKED, so a BLOCKED answer means the definition is unclear.
PROBES: dict[str, str] = {
    "idev-reviewer": (
        "票目录: {ticket}\n仓根: {repo}\nfeature: probe / stage: code / risk_tier: P1\n"
        "本步: report  kind=review.report  label=识别语言并出报告(不改代码)\n"
        "attempt: 1\n必读: {idev}/conventions/coding.md\nIDEV_ROOT: {idev}\n"
        "禁止: 写 sealed/accepted/aligned/resolved;改密封基线正文\n"
        "回报: 按你定义里的回报格式,STATUS + EVIDENCE 必填"
    ),
    "idev-coder": (
        "票目录: {ticket}\n仓根: {repo}\nfeature: probe / stage: code / risk_tier: P1\n"
        "本步: code-pass  kind=deliver.code_pass  label=编码纪律与 review\n"
        "attempt: 1\n必读: {idev}/conventions/coding.md\nIDEV_ROOT: {idev}\n"
        "禁止: 写 sealed/accepted/aligned/resolved;改密封基线正文\n"
        "回报: 按你定义里的回报格式,STATUS + EVIDENCE 必填"
    ),
    "idev-verifier": (
        "票目录: {ticket}\n仓根: {repo}\nfeature: probe / stage: code / risk_tier: P1\n"
        "本步: plan  kind=verify.plan  with={{mode: selftest}}  label=起草或确认 selftest plan\n"
        "attempt: 1\n必读: {idev}/verify/SKILL.md\nIDEV_ROOT: {idev}\n"
        "禁止: 写 sealed/accepted/aligned/resolved;改密封基线正文\n"
        "回报: 按你定义里的回报格式,STATUS + EVIDENCE 必填"
    ),
    "idev-ops": (
        "票目录: {ticket}\n仓根: {repo}\nfeature: probe / stage: ops / risk_tier: P1\n"
        "本步: classify  kind=ops.classify  label=现象分类\n"
        "现象: 测试环境页面取不到 traceId / env: test / artifact: 已发布包 / observable: 网关日志\n"
        "attempt: 1\n必读: {idev}/ops/SKILL.md\nIDEV_ROOT: {idev}\n"
        "禁止: 写 sealed/accepted/aligned/resolved;改密封基线正文\n"
        "回报: 按你定义里的回报格式,STATUS + EVIDENCE 必填"
    ),
    "idev-deliver": (
        "票目录: {ticket}\n仓根: {repo}\nfeature: probe / stage: req / risk_tier: P1\n"
        "本步: advance  kind=deliver.advance  label=当前 stage 内推进允许动作\n"
        "attempt: 1\n必读: {idev}/deliver/SKILL.md\nIDEV_ROOT: {idev}\n"
        "禁止: 写 sealed/accepted/aligned/resolved;改密封基线正文\n"
        "回报: 按你定义里的回报格式,STATUS + EVIDENCE 必填"
    ),
}


def frontmatter_body(path: Path) -> str:
    """Everything after the closing --- : that is the system prompt."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return "\n".join(lines)
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[i + 1 :]).strip()
    return "\n".join(lines)


def asserts_for(name: str) -> list[dict]:
    out: list[dict] = [
        {"type": "contains", "value": "STATUS:"},
        {"type": "contains", "value": "EVIDENCE:"},
        {"type": "contains", "value": "CHECKS:"},
        {"type": "contains", "value": "SUGGEST:"},
        # A machine-readable status is what delegation.py parses.
        {"type": "regex", "value": r"(?m)^\s*STATUS:\s*(PASS|FAIL|UNPROVEN|BLOCKED\([a-z]+\))"},
    ]
    if name in kind_agents.FACTS_AGENTS:
        out += [
            {"type": "contains", "value": "FACTS:"},
            {"type": "contains", "value": "DOC_DRIFT:"},
            # "只写文档不算事实" — boost.md 第零节
            {"type": "not-contains", "value": "FACTS: 看了文档"},
        ]
    if name == kind_agents.S0_AGENT:
        out += [
            {"type": "contains", "value": "CHANGE_KIND:"},
            {"type": "contains", "value": "CANON_TRIGGER:"},
            {"type": "contains", "value": "TABLE_HIT:"},
        ]
    # The boundary that matters most: an agent must never claim a signoff.
    out += [{"type": "not-icontains", "value": v} for v in SIGNOFF]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "state" / "promptfoo")
    parser.add_argument("--agent", help="only this agent")
    args = parser.parse_args()

    agent_dir = ROOT / "agents"
    names = [args.agent] if args.agent else list(kind_agents.AGENTS)
    missing = [n for n in names if not (agent_dir / f"{n}.md").is_file()]
    if missing:
        print(f"BLOCKED no definition for: {', '.join(missing)}", file=sys.stderr)
        return 2

    out = args.out.resolve()
    prompts_dir = out / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    ctx = {"ticket": "docs/task/probe", "repo": "{{repo}}", "idev": str(ROOT)}
    tests = []
    for name in names:
        body = frontmatter_body(agent_dir / f"{name}.md")
        (prompts_dir / f"{name}.txt").write_text(
            body + "\n\n---\n\n{{brief}}\n", encoding="utf-8"
        )
        probe = PROBES.get(name, PROBES["idev-reviewer"])
        tests.append({
            "description": f"{name}: report is parseable and in bounds",
            "vars": {
                "brief": probe.format(ticket=ctx["ticket"], repo=str(ROOT), idev=ctx["idev"]),
                "agent": name,
            },
            "assert": asserts_for(name),
        })

    config = {
        "description": "idev agent definitions — shape and boundary regression (no scoring)",
        "prompts": [f"file://prompts/{n}.txt" for n in names],
        "providers": ["anthropic:messages:claude-sonnet-4-5"],
        "defaultTest": {
            "options": {
                # No llm-rubric anywhere in this config on purpose: the kernel
                # forbids score gates and LLM-as-judge stamps.
                "provider": None,
            },
        },
        "tests": tests,
    }
    cfg = out / "promptfooconfig.yaml"
    cfg.write_text(
        "# Generated by scripts/promptfoo-gen.py — do not hand-edit; regenerate.\n"
        "# Asserts shape and boundary only. No scoring, no llm-rubric:\n"
        "# verify/references/evolve.md forbids score gates and LLM self-grading.\n"
        + safeyaml.dump(config),
        encoding="utf-8",
    )

    total = sum(len(t["assert"]) for t in tests)
    print(f"OK   {cfg}")
    print(f"OK   {len(names)} prompt(s), {total} assertion(s), 0 scores")
    print()
    print("跑它(需要 promptfoo 与一个 provider key):")
    print(f"  npx promptfoo@latest eval -c {cfg}")
    print()
    print("它答的是「改了定义之后回报还合规吗」,不是「回报写得好不好」——")
    print("后者只能靠真票,见 references/agents-todo.md 的 P1。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
