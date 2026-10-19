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

try:
    import roots
except ImportError:  # loaded as lib.kind_agents, with scripts/ on the path
    from lib import roots  # type: ignore[no-redef]

# The conductor (the session talking to the person) keeps these steps.
CONDUCTOR = "-"

try:
    import _generated_kinds as _gen
except ImportError:  # loaded as lib.kind_agents, with scripts/ on the path
    from lib import _generated_kinds as _gen  # type: ignore[no-redef]

# Generated from registry/kinds.yaml. FACTS_AGENTS are the agents that reach a
# judgement and so must say where the facts came from (references/boost.md 第
# 零节); idev-deliver is out because its output *is* the document, so "the
# document says" would be circular there.
FACTS_AGENTS: tuple = _gen.FACTS_AGENTS
AGENTS: tuple = _gen.AGENTS
BOOST_AGENTS: tuple = _gen.BOOST_AGENTS
S0_AGENT = _gen.S0_AGENT
READONLY_BREAKS: dict[str, str] = _gen.READONLY_BREAKS

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
# rejects agent, model and role names (AGENT_WORDS, whole or by token) as a
# signoff name, so a subagent cannot sign under its own name.
# preflight.inputs is a probe, shell.confirmed is a single pre-approved
# command, and ui.clean_pass_loop is the outer loop — all cheaper for the
# conductor to run than to brief an agent for.
KIND_AGENTS: dict[str, str] = _gen.KIND_AGENTS
# kind -> the agent that must confirm a PASS (registry verify: independent).
KIND_VERIFIER: dict[str, str] = _gen.KIND_VERIFIER
# kind -> none | write | verify (registry lease).
KIND_LEASE: dict[str, str] = _gen.KIND_LEASE


# Root resolution moved to roots.py once it became clear this file was the
# only one of five callers that honoured IDEV_ROOT. Re-exported so the names
# stay importable from here.
KERNEL_MARKERS = roots.KERNEL_MARKERS
is_kernel = roots.is_kernel
kernel_root = roots.kernel_root


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
        found = roots.resolve()
        # roots.resolve() falls back rather than exploding, so a bad override
        # no longer reaches here as a non-kernel path. Say so anyway: silently
        # ignoring IDEV_ROOT is how someone audits the wrong checkout for an
        # afternoon. The exit code stays 0 because the root is usable.
        if found.note:
            print(f"WARN    {found.note}", file=sys.stderr)
            print(f"HINT    looked for {', '.join(KERNEL_MARKERS)}", file=sys.stderr)
        if not is_kernel(found.path):
            print(
                f"BLOCKED {found.path} does not look like an idev root\n"
                f"HINT    looked for {', '.join(KERNEL_MARKERS)}\n"
                f"HINT    this checkout is incomplete, not misconfigured",
                file=sys.stderr,
            )
            return 2
        print(found.path)
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
