#!/usr/bin/env python3
"""kind -> agent table (the "委派给" column).

references/agents.md is the prose. This module is the same contract for
tools: workflow.py prints the DELEGATE line with it.

It does not execute anything and it does not pick an agent at runtime: the
table is fixed, so the same step always names the same agent. The conductor
reads the line and delegates; "-" means the conductor keeps the step.

Kept out of workflow_spec.py so the kernel stays untouched while this layer
is on trial. check_table() keeps the two in step: a kind added to the kernel
without a row here fails, the same way selfcheck keeps the prose kind table
equal to KINDS.
"""
from __future__ import annotations

import os
from pathlib import Path

# The conductor (the session talking to the person) keeps these steps.
CONDUCTOR = "-"

# Agents that reach a judgement and therefore must declare where the facts
# came from (references/boost.md 第零节). idev-deliver is out: its output is
# the document, so "the document says" is not circular there.
FACTS_AGENTS: tuple[str, ...] = (
    "idev-ops",
    "idev-coder",
    "idev-reviewer",
    "idev-verifier",
)

# The agent that declares coding.md §0 (CHANGE_KIND / CANON_TRIGGER /
# TABLE_HIT). delegation.py runs the §0 checks against this name only, so
# keeping it here means a rename stays visible: agents-check verifies the
# name is really on the roster, instead of the checks silently going quiet.
S0_AGENT = "idev-coder"

AGENTS: tuple[str, ...] = (
    "idev-deliver",
    "idev-coder",
    "idev-reviewer",
    "idev-verifier",
    "idev-ops",
)

# Agents that run this repo's boost scripts (failure_signature, hypothesis)
# and refer to the repo root as $AGENT in their definitions. A brief without
# agent_root sends them to an empty path, so delegation.py requires it for
# these and agents-check.py requires the definitions to name $AGENT.
# Single source: both scripts import this, they do not keep their own copy.
BOOST_AGENTS: tuple[str, ...] = (
    "idev-coder",
    "idev-verifier",
    "idev-ops",
)

# Why no agent sets Cursor's readonly: true. Cursor's readonly blocks every
# write AND every state-changing shell command, so it breaks each of these
# for the reason given. agents-check.py refuses readonly: true against this
# table.
READONLY_BREAKS: dict[str, str] = {
    "idev-deliver": "写票 YAML、规格与产线文档",
    "idev-coder": "改代码、跑构建与 git commit",
    "idev-reviewer": "写 review.md",
    "idev-verifier": "写 plan.yaml、report.md,启停本地服务",
    "idev-ops": "写 ops.yaml、假设台账与 lessons",
}

# kind -> the agent that executes it. CONDUCTOR = never delegate.
#
# Grouped by the kernel's own lifecycle stages and modules rather than by
# individual action, so one agent owns one phase end to end:
#   deliver  = req-review/req/arch + the product docs that go with them
#   coder    = the code stage, plus building and committing what it wrote
#   reviewer = review only, deliberately separate from whoever writes code
#   verifier = the verify module, plus the environment its cases need
#   ops      = the ops module, plus S4 reasoning (both run evidence.md)
#
# human.gate is CONDUCTOR by necessity, not by choice: workflow_spec.is_human()
# rejects {agent, ai, cursor, assistant} as a signoff name, so a subagent
# cannot sign. preflight.inputs is a probe, shell.confirmed is a single
# pre-approved command, and ui.clean_pass_loop is the outer loop — all
# cheaper for the conductor to run than to brief an agent for.
KIND_AGENTS: dict[str, str] = {
    "preflight.inputs": CONDUCTOR,
    "route.s4": "idev-ops",
    "deliver.advance": "idev-deliver",
    "deliver.code_pass": "idev-coder",
    "review.report": "idev-reviewer",
    "review.fix": "idev-coder",
    "verify.plan": "idev-verifier",
    "verify.run": "idev-verifier",
    "docs.backfill": "idev-deliver",
    "docs.changelog": "idev-deliver",
    "ops.classify": "idev-ops",
    "human.gate": CONDUCTOR,
    "shell.confirmed": CONDUCTOR,
    "localdev.start": "idev-verifier",
    "localdev.approval_off": "idev-verifier",
    "localdev.stop": "idev-verifier",
    "ui.lifecycle_run": "idev-verifier",
    "ui.surface_scan": "idev-verifier",
    "ui.playbook_sync": "idev-coder",
    "ui.coverage_lock": "idev-verifier",
    "ui.fix_deposit": "idev-ops",
    "ui.clean_pass_loop": CONDUCTOR,
    "ui.product_batch": CONDUCTOR,
    "git.replace_check": "idev-coder",
    "frontend.lint_fix": "idev-coder",
    "java.build": "idev-coder",
    "git.sensitive_shield": "idev-coder",
    "git.sensitive_restore": "idev-coder",
    "git.commit_push": "idev-coder",
}


def kernel_root() -> Path:
    """The idev root. This file lives inside it, so it is self-evident.

    Before the agent layer merged into idev this had to probe a list of
    aliases and verify each one, because the layer sat in its own repo and
    took over the ~/.cursor/skills/idev name — so $IDEV could silently
    resolve to the agent layer and every convention reference would dangle.
    Merging deleted that entire problem: scripts/lib/ is two levels under
    the root, and the conventions and the 44 scripts are right here.

    IDEV_ROOT still overrides, for driving one checkout's agents against
    another checkout's kernel.
    """
    env = os.environ.get("IDEV_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


# Files only the kernel has — used to verify an explicit IDEV_ROOT.
KERNEL_MARKERS = ("scripts/lib/workflow_spec.py", "conventions/SKILL.md")


def is_kernel(path: Path) -> bool:
    base = path.expanduser()
    return all((base / marker).is_file() for marker in KERNEL_MARKERS)


def agent_for(kind: str) -> str:
    """The agent for this kind. An unknown kind stays with the conductor.

    An unknown kind is not an error here: workflow_spec.check_recipe already
    refuses it at start, so a run never reaches a step this table cannot name.
    """
    return KIND_AGENTS.get(kind, CONDUCTOR)


def delegate_line(kind: str) -> str:
    """The DELEGATE line workflow.py prints under OPEN."""
    agent = agent_for(kind)
    if agent == CONDUCTOR:
        return "DELEGATE none; the conductor does this step"
    return f"DELEGATE {agent}"


def check_table(kinds: dict[str, str], errors: list[str]) -> None:
    """Every kernel kind has a row, every row names a known agent."""
    for kind in sorted(set(kinds) - set(KIND_AGENTS)):
        errors.append(f"kind_agents: {kind} has no row; add one (or {CONDUCTOR})")
    for kind in sorted(set(KIND_AGENTS) - set(kinds)):
        errors.append(f"kind_agents: {kind} is not a kernel kind; drop the row")
    for kind, agent in sorted(KIND_AGENTS.items()):
        if agent != CONDUCTOR and agent not in AGENTS:
            errors.append(f"kind_agents: {kind} names unknown agent {agent}")


def main() -> int:
    """Print the table, or check it against the kernel with --check."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare with the kernel KINDS table")
    parser.add_argument("--kind", help="print the DELEGATE line for one kind")
    parser.add_argument("--kernel", action="store_true", help="print the resolved idev root")
    args = parser.parse_args()

    if args.kernel:
        root = kernel_root()
        if not is_kernel(root):
            print(
                f"BLOCKED {root} does not look like an idev root\n"
                f"HINT    looked for {', '.join(KERNEL_MARKERS)}\n"
                f"HINT    unset IDEV_ROOT to use this checkout, or point it at a real one",
                file=sys.stderr,
            )
            return 2
        print(root)
        return 0

    if args.kind:
        print(delegate_line(args.kind))
        return 0

    if args.check:
        sys.path.insert(0, str(kernel_root() / "scripts"))
        try:
            from lib import workflow_spec  # noqa: PLC0415
        except ImportError:
            print(f"BLOCKED cannot import the kernel from {kernel_root()}; set IDEV_ROOT", file=sys.stderr)
            return 2
        errors: list[str] = []
        check_table(workflow_spec.KINDS, errors)
        if errors:
            for err in errors:
                print("FAIL " + err, file=sys.stderr)
            return 1
        print(f"kind_agents PASS {len(KIND_AGENTS)} kinds, {len(AGENTS)} agents")
        return 0

    for kind, agent in KIND_AGENTS.items():
        print(f"{kind}\t{agent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
