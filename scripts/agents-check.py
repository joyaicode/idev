#!/usr/bin/env python3
"""Check the agent layer: definitions, the kind table, and the kernel.

    agents-check.py [--agents-dir DIR]

Exit 0 = PASS, 1 = findings, 2 = cannot read the kernel (set IDEV_ROOT).

What it checks:
  1. every agent in kind_agents.AGENTS has agents/<name>.md, and back
  2. each file's frontmatter name == AGENTS entry == file stem
  3. description is present (Claude Code skips a file that has none)
  4. no file sets readonly: true (it breaks every one of these in Cursor,
     see kind_agents.READONLY_BREAKS)
  5. the report format still has the lines delegation.py parses, and the
     BLOCKED(...) split metrics needs to attribute a blocker
  6. tool sets: the narrowing each agent promises is actually in `tools`,
     and the boost agents keep the Bash they need to run the scripts
  7. KIND_AGENTS covers exactly the kernel's KINDS (via check_table)

--agents-dir points the file checks at another directory, which is how
smoke.sh feeds it deliberately broken definitions: a checker that is never
itself tested is a checker nobody should trust. The roster check (1) only
runs against this repo's own agents/, since another directory is not
expected to hold all eight.

Frontmatter is read line by line on purpose: no YAML dependency. It does
handle a block sequence (`tools:` then `  - Read`), because Claude Code
accepts both that and the comma form, and treating a list as "no tools
field" would report a narrowing as missing when it is right there.

AGENTS, BOOST_AGENTS and READONLY_BREAKS all live in kind_agents: this
script imports them rather than keeping a second copy that would drift.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import kind_agents  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DEFAULT_AGENT_DIR = REPO / "agents"

# The report contract delegation.py parses. A definition that drifts away
# from these lines breaks the honesty checks silently, which is the failure
# mode this whole layer exists to avoid.
REPORT_MARKERS = ("STATUS:", "EVIDENCE:", "CHECKS:", "SUGGEST:")

# Tools an agent must NOT have, because its role forbids the action. Cursor
# ignores `tools`, so each agent restates the boundary in its hard rules —
# but on the Claude Code side this is enforceable, so enforce it.
#
# Note what is NOT here: idev-coder now owns git.commit_push as well as the
# code stage, so it needs Write/Edit and cannot be narrowed. That is the
# price of folding the old command-runner agent into the stage that produces
# the commit; the boundary survives only as a prompt rule plus the conductor
# checking the report.
TOOL_BANS: dict[str, tuple[str, ...]] = {
    "idev-reviewer": ("Edit",),   # writes review.md, never changes code
    "idev-ops": ("Edit",),        # writes the ledger and lessons, never changes code
}

# Tools an agent must have to do its job at all.
TOOL_NEEDS: dict[str, tuple[str, ...]] = {name: ("Read", "Bash") for name in kind_agents.BOOST_AGENTS}


def read_definition(path: Path, errors: list[str]) -> str | None:
    """A definition's text. None when it cannot be decoded.

    errors="replace" rather than raising: a hand-edited file with one stray
    byte should produce a finding naming that file, not a traceback with no
    filename in it.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        errors.append(f"{path.name}: cannot be read ({exc.strerror})")
        return None


def frontmatter(path: Path, errors: list[str]) -> dict[str, str]:
    """The `key: value` lines between the opening and closing `---`.

    A key whose value is empty absorbs the indented lines under it, so both
    `tools: Read, Bash` and a `- Read` block sequence come back as one
    comma-joined string.
    """
    text = read_definition(path, errors)
    if text is None:
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        errors.append(f"{path.name}: first line must be ---, or the whole file is treated as prose")
        return {}
    fields: dict[str, str] = {}
    pending: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        indented = line.startswith((" ", "\t"))
        stripped = line.strip()

        if indented and pending and stripped:
            item = stripped[2:].strip() if stripped.startswith("- ") else stripped
            item = item.strip("\"'")
            fields[pending] = f"{fields[pending]}, {item}" if fields[pending] else item
            continue
        if indented or ":" not in line:
            continue  # a folded scalar under a key that already had a value

        key, _, value = line.partition(":")
        key = key.strip()
        fields[key] = value.strip()
        # Only an empty value can take indented continuation lines.
        pending = key if not value.strip() else None
    errors.append(f"{path.name}: frontmatter is never closed")
    return fields


def tool_set(fields: dict[str, str]) -> set[str] | None:
    """`tools: Read, Grep, Bash` -> {Read, Grep, Bash}. None = inherit all."""
    raw = fields.get("tools", "").strip()
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def check_files(agent_dir: Path, strict_roster: bool, errors: list[str], warns: list[str]) -> None:
    found = sorted(p.stem for p in agent_dir.glob("*.md"))

    if strict_roster:
        for name in sorted(set(kind_agents.AGENTS) - set(found)):
            errors.append(f"agents: {name} is in AGENTS but agents/{name}.md is missing")
        for stem in sorted(set(found) - set(kind_agents.AGENTS)):
            errors.append(f"agents: agents/{stem}.md is not in AGENTS; add it or drop the file")

    for path in sorted(agent_dir.glob("*.md")):
        fields = frontmatter(path, errors)
        if not fields:
            continue

        # 2 + 3: identity
        name = fields.get("name", "")
        if not name:
            errors.append(f"{path.name}: no name field; Claude Code skips the file silently")
        elif name != path.stem:
            errors.append(f"{path.name}: name {name} does not match the file stem {path.stem}")
        if not fields.get("description"):
            errors.append(f"{path.name}: no description; Claude Code skips a named file without one")

        # 4: readonly
        readonly = fields.get("readonly", "")
        if readonly == "true":
            why = kind_agents.READONLY_BREAKS.get(name, "这一步不是纯读的")
            errors.append(f"{path.name}: readonly: true but this agent has to {why}")
        elif not readonly:
            warns.append(f"{path.name}: no readonly field; write it as false so the choice is on the record")

        # 5: the report contract
        body = read_definition(path, errors) or ""
        for marker in REPORT_MARKERS:
            if marker not in body:
                errors.append(f"{path.name}: report format has no {marker} line; delegation.py parses it")
        if "BLOCKED(" not in body:
            errors.append(f"{path.name}: no BLOCKED(brief|env|logic) split; metrics cannot attribute the blocker")
        if name in kind_agents.BOOST_AGENTS and "$AGENT" not in body:
            errors.append(f"{path.name}: runs the boost scripts but never names $AGENT (the idev-agent root)")

        # 6: tool sets
        tools = tool_set(fields)
        if tools is None:
            # Omitting tools inherits everything, which silently voids any ban.
            if name in TOOL_BANS:
                banned = "/".join(TOOL_BANS[name])
                errors.append(
                    f"{path.name}: must list tools — omitting it inherits every tool, "
                    f"including {banned}, which this agent's role forbids"
                )
            else:
                warns.append(f"{path.name}: no tools field; it inherits every tool, so no narrowing applies")
        else:
            for banned_tool in TOOL_BANS.get(name, ()):
                if banned_tool in tools:
                    errors.append(f"{path.name}: has {banned_tool}, but its role forbids it (see TOOL_BANS)")
            for needed in TOOL_NEEDS.get(name, ()):
                if needed not in tools:
                    errors.append(f"{path.name}: needs {needed} to run the boost scripts, but tools omits it")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--agents-dir",
        type=Path,
        default=DEFAULT_AGENT_DIR,
        help="definitions to check (default: this repo's agents/)",
    )
    args = parser.parse_args()

    agent_dir = args.agents_dir.resolve()
    strict_roster = agent_dir == DEFAULT_AGENT_DIR.resolve()

    errors: list[str] = []
    warns: list[str] = []

    # 1 + 7: the kind table against the kernel
    sys.path.insert(0, str(kind_agents.kernel_root() / "scripts"))
    try:
        from lib import workflow_spec
    except ImportError:
        print(f"BLOCKED cannot import the kernel from {kind_agents.kernel_root()}; set IDEV_ROOT", file=sys.stderr)
        return 2
    kind_agents.check_table(workflow_spec.KINDS, errors)

    # The derived tables must only name agents that exist.
    for name in kind_agents.BOOST_AGENTS:
        if name not in kind_agents.AGENTS:
            errors.append(f"kind_agents.BOOST_AGENTS names unknown agent {name}")
    for name in kind_agents.READONLY_BREAKS:
        if name not in kind_agents.AGENTS:
            errors.append(f"kind_agents.READONLY_BREAKS names unknown agent {name}")
    if kind_agents.S0_AGENT not in kind_agents.AGENTS:
        errors.append(
            f"kind_agents.S0_AGENT names unknown agent {kind_agents.S0_AGENT}; "
            "the §0 checks in delegation.py would go silently quiet"
        )
    for name in kind_agents.AGENTS:
        if name not in kind_agents.READONLY_BREAKS:
            warns.append(f"kind_agents.READONLY_BREAKS has no row for {name}; readonly: true would go unchecked")

    # Append rather than return early: returning here would throw away the
    # table findings already collected above.
    if not agent_dir.is_dir():
        errors.append(f"no agents directory at {agent_dir}")
    else:
        check_files(agent_dir, strict_roster, errors, warns)

    for warn in warns:
        print("WARN " + warn, file=sys.stderr)
    if errors:
        for err in errors:
            print("FAIL " + err, file=sys.stderr)
        return 1

    kinds = len(kind_agents.KIND_AGENTS)
    delegated = sum(1 for v in kind_agents.KIND_AGENTS.values() if v != kind_agents.CONDUCTOR)
    scope = "" if strict_roster else f" ({agent_dir})"
    print(
        f"agents-check PASS {len(kind_agents.AGENTS)} agents, {kinds} kinds "
        f"({delegated} delegated, {kinds - delegated} kept by the conductor){scope}"
        + (f", {len(warns)} warn" if warns else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
