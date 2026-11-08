#!/usr/bin/env python3
"""What counts as a capability, derived — never registered.

The inventory is computed from the single sources of truth on every run:
workflows/*.yaml, kind_agents (itself generated from registry/kinds.yaml),
agents/*.md via kind_agents, the module SKILL.md pages, and scripts/*. No
second registry is kept, because a capability table nothing syncs against is
exactly the second ledger the kernel forbids. Adding a kind or a recipe
updates this inventory for free; nothing to remember, nothing to drift.

Cost is a glob plus a regex per source (<10ms), so there is no staleness
problem for a generated copy to solve. If a future consumer needs the list
hot, the escape hatch is the gen-kinds pattern — say so in a proposal first.
"""
from __future__ import annotations

import re
from pathlib import Path

try:
    import roots
except ImportError:  # loaded as lib.capability_inventory
    from lib import roots  # type: ignore[no-redef]

try:
    import kind_agents
except ImportError:  # loaded as lib.capability_inventory
    from lib import kind_agents  # type: ignore[no-redef]

# Capability types, in report order. "rule" lives here only as a type label;
# the 93 canon/coding-tables numbers are knowledge-metrics' column to keep
# (they come from deep-read-audit.defined_ids, not from a rewrite here).
CAPABILITY_TYPES = ("workflow", "kind", "agent", "module", "script")

WORKFLOW_ID = re.compile(r"(?m)^id:\s*(\S+)\s*$")


def workflow_ids(kernel: Path) -> list[str]:
    """Recipe ids from workflows/*.yaml — the alias, not the file name."""
    out: list[str] = []
    for path in sorted((kernel / "workflows").glob("*.yaml")):
        found = WORKFLOW_ID.search(path.read_text(encoding="utf-8", errors="replace"))
        if found:
            out.append(found.group(1))
    return out


def module_skills(kernel: Path) -> list[str]:
    """Top-level module skills: the directories holding a SKILL.md."""
    return sorted(p.parent.name for p in kernel.glob("*/SKILL.md"))


def script_names(kernel: Path) -> dict[str, str]:
    """Kernel scripts by the token a trace or report would name.

    A hyphenated stem ("agent-metrics") is distinctive enough without its
    extension; a one-word stem ("workflow") only counts as workflow.py.
    """
    things: dict[str, str] = {}
    for path in sorted((kernel / "scripts").iterdir()):
        if path.suffix in (".sh", ".py"):
            things[path.name] = path.name
            if "-" in path.stem:
                things.setdefault(path.stem, path.name)
    return things


def inventory(kernel: Path | None = None) -> dict[str, str]:
    """capability name -> type. Kinds carry their agent as KIND_AGENTS[name].

    A name can be two things at once (path-view is a recipe and path-view.sh
    is a script); the more specific type wins, in CAPABILITY_TYPES order, so
    the hit counts merge under one row instead of splitting.
    """
    kernel = kernel or roots.kernel_root()
    out: dict[str, str] = {}
    for source, kind in (
        (workflow_ids(kernel), "workflow"),
        (list(kind_agents.KIND_AGENTS), "kind"),
        (list(kind_agents.AGENTS), "agent"),
        (module_skills(kernel), "module"),
        (list(script_names(kernel)), "script"),
    ):
        for name in source:
            out.setdefault(name, kind)
    return out


def delegated_kinds() -> list[str]:
    """Kinds that go to an agent (not conductor-kept) — the unused-report set."""
    return sorted(k for k, a in kind_agents.KIND_AGENTS.items() if a != kind_agents.CONDUCTOR)
