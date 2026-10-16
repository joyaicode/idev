#!/usr/bin/env python3
"""Generate every copy of the kind table from registry/kinds.yaml.

    python3 scripts/gen-kinds.py            # write the generated files
    python3 scripts/gen-kinds.py --check    # CI: fail if they are stale
    python3 scripts/gen-kinds.py --diff-legacy
        # compare the registry against the hand-written tables it replaces.
        # Run this first: a refactor that quietly changes the contract is
        # worse than the five copies it removes.

Outputs
    scripts/lib/_generated_kinds.py      KINDS / KIND_AGENTS / KIND_COMMANDS / …
    api/schemas/kinds.schema.json        the kind and agent enums
    references/workflow-schema.md        between <!-- kinds:begin|end -->
    references/agents.md                 between <!-- agents-table:begin|end -->
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import roots  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("BLOCKED pyyaml is required (the idev contracts are all yaml)")

ROOT = roots.kernel_root()
REGISTRY = ROOT / "registry" / "kinds.yaml"
CONDUCTOR = "-"

BANNER = "# Generated from registry/kinds.yaml by scripts/gen-kinds.py. Do not edit."


def load() -> dict:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "kinds" not in data:
        raise SystemExit(f"BLOCKED {REGISTRY} is not a kind registry")
    return data


def agent_of(spec: dict) -> str:
    return CONDUCTOR if spec.get("executor") == "conductor" else str(spec["agent"])


# --- generated artefacts ---------------------------------------------------


def gen_python(data: dict) -> str:
    kinds = data["kinds"]
    lines = [
        "#!/usr/bin/env python3",
        '"""The kind table, generated. Edit registry/kinds.yaml instead.',
        "",
        "Kept as Python so the migration-era scripts keep one import shape while",
        "the Go side reads the same registry/kinds.yaml directly.",
        '"""',
        "from __future__ import annotations",
        "",
        BANNER,
        "",
        "KINDS: dict[str, str] = {",
    ]
    for kind, spec in kinds.items():
        lines.append(f'    "{kind}": "{spec["page"]}",')
    lines += ["}", "", "KIND_AGENTS: dict[str, str] = {"]
    for kind, spec in kinds.items():
        lines.append(f'    "{kind}": "{agent_of(spec)}",')
    lines += ["}", "", "KIND_COMMANDS: dict[str, str] = {"]
    for kind, spec in kinds.items():
        if spec.get("command_key"):
            lines.append(f'    "{kind}": "{spec["command_key"]}",')
    lines += ["}", ""]

    lines.append("# Leases: write touches product code, verify only ticket artefacts.")
    lines.append("KIND_LEASE: dict[str, str] = {")
    for kind, spec in kinds.items():
        lines.append(f'    "{kind}": "{spec.get("lease", "none")}",')
    lines += ["}", ""]

    independent = {k: s for k, s in kinds.items() if s.get("verify") == "independent"}
    lines.append("# A PASS here needs a second agent's confirmation (design I-2).")
    lines.append("KIND_VERIFIER: dict[str, str] = {")
    for kind, spec in independent.items():
        lines.append(f'    "{kind}": "{spec["verifier"]}",')
    lines += ["}", ""]

    forbidden = sorted(data.get("forbidden") or [])
    legacy = sorted(k for k, s in kinds.items() if s.get("legacy"))
    gates = sorted(k for k, s in kinds.items() if s.get("gate"))
    gate_before = sorted(k for k, s in kinds.items() if s.get("requires_gate_before"))
    lines += [
        f"FORBIDDEN: set[str] = {{{', '.join(repr(x) for x in forbidden)}}}",
        f"LEGACY_KINDS: set[str] = {{{', '.join(repr(x) for x in legacy)}}}",
        f"GATE_KINDS: set[str] = {{{', '.join(repr(x) for x in gates)}}}",
        f"REQUIRES_GATE_BEFORE: set[str] = {{{', '.join(repr(x) for x in gate_before)}}}",
        "",
        "AGENTS: tuple = (",
    ]
    for name in data["agents"]:
        lines.append(f'    "{name}",')
    lines += [")", ""]
    facts = tuple(n for n, a in data["agents"].items() if a.get("facts"))
    boost = tuple(n for n, a in data["agents"].items() if a.get("boost"))
    s0 = tuple(n for n, a in data["agents"].items() if a.get("s0"))
    lines += [
        f"FACTS_AGENTS: tuple = {facts!r}",
        f"BOOST_AGENTS: tuple = {boost!r}",
        f"S0_AGENTS: tuple = {s0!r}",
        "",
        "# coding.md §0 is written for one agent. Kept singular because four",
        "# call sites compare against a name, not a membership.",
        f"S0_AGENT = {s0[0]!r}" if len(s0) == 1 else "S0_AGENT = None",
        "",
        "READONLY_BREAKS: dict[str, str] = {",
    ]
    for name, spec in data["agents"].items():
        lines.append(f'    "{name}": "{spec["readonly_breaks"]}",')
    lines += ["}", ""]
    return "\n".join(lines)


def gen_schema(data: dict) -> str:
    body = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://idev.dev/schemas/kinds.schema.json",
        "title": "idev kind registry",
        "description": BANNER.lstrip("# "),
        "type": "object",
        "$defs": {
            "kind": {"type": "string", "enum": list(data["kinds"])},
            "agent": {"type": "string", "enum": list(data["agents"])},
            "executor": {
                "type": "string",
                "enum": [CONDUCTOR, *data["agents"]],
            },
            "lease": {"type": "string", "enum": ["none", "write", "verify"]},
            "forbiddenKind": {"type": "string", "enum": sorted(data.get("forbidden") or [])},
        },
    }
    return json.dumps(body, ensure_ascii=False, indent=2) + "\n"


def gen_schema_prose(data: dict) -> str:
    """The workflow-schema.md table, with its own columns.

    `lands` is a deliberately short human label ("—", "conventions"), not the
    `page` path: this table is read while deciding which kind to use, and a
    column of full paths makes it unreadable. Both live in the registry so
    neither has to be re-derived by hand.
    """
    rows = ["| kind | 落到 | 说明 |", "|------|------|------|"]
    for kind, spec in data["kinds"].items():
        rows.append(f"| `{kind}` | {spec['lands']} | {spec['note']} |")
    forbidden = " / ".join(f"`{k}`" for k in (data.get("forbidden") or []))
    rows += ["", f"禁止 kind：{forbidden}。"]
    return "\n".join(rows)


def gen_agents_prose(data: dict) -> str:
    """The agents.md table, grouped by agent rather than by kind."""
    by_agent: dict = {name: [] for name in data["agents"]}
    kept: list = []
    for kind, spec in data["kinds"].items():
        agent = agent_of(spec)
        if agent == CONDUCTOR:
            kept.append(kind)
        else:
            by_agent[agent].append(kind)

    rows = ["| agent | 对应阶段 / 模块 | 角色 | 承接 kind |", "|---|---|---|---|"]
    for name, spec in data["agents"].items():
        kinds = " · ".join(f"`{k}`" for k in by_agent[name])
        rows.append(f"| `{name}` | {spec['stage']} | {spec['role_label']} | {kinds} |")
    cond = data.get("conductor") or {}
    rows.append(
        f"| **导体** | {cond.get('stage', '—')} | {cond.get('role_label', '持签字权')} | "
        + " · ".join(f"`{k}`" for k in kept)
        + " |"
    )
    total = len(data["kinds"])
    rows += [
        "",
        f"{total} 个 kind:{total - len(kept)} 个委派,{len(kept)} 个导体保留。"
        "每个 kind 的**落点页**见 `registry/kinds.yaml` 的 `page`,本页不复制那一列。",
        "",
        "这张表由 `scripts/gen-kinds.py` 从 `registry/kinds.yaml` 生成。加一个 kind 只改那一个文件。",
    ]
    return "\n".join(rows)


def splice(path: Path, marker: str, body: str) -> str:
    """Replace what is between <!-- marker:begin --> and <!-- marker:end -->."""
    text = path.read_text(encoding="utf-8")
    begin, end = f"<!-- {marker}:begin -->", f"<!-- {marker}:end -->"
    if begin not in text or end not in text:
        raise SystemExit(f"BLOCKED {path} has no {begin} … {end} markers")
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    return f"{head}{begin}\n{body}\n{end}{tail}"


# --- legacy comparison -----------------------------------------------------


def diff_legacy(data: dict) -> int:
    """Compare the registry against the tables it replaced.

    This was the migration check: it ran before workflow_spec, kind_agents and
    workflow_defaults were switched over, and proved the registry reproduced
    all five hand-written tables byte for byte. Now that those modules import
    from the generated file, the comparison is circular — so it says so rather
    than reporting a reassuring OK that means nothing.
    """
    sys.path.insert(0, str(ROOT / "scripts" / "lib"))
    import kind_agents as ka  # noqa: PLC0415
    import workflow_defaults as wd  # noqa: PLC0415
    import workflow_spec as ws  # noqa: PLC0415

    generated = ROOT / "scripts" / "lib" / "_generated_kinds.py"
    if generated.is_file() and ws.KINDS is not None:
        import _generated_kinds as gen  # noqa: PLC0415

        if ws.KINDS is gen.KINDS:
            print(
                "SKIP workflow_spec/kind_agents/workflow_defaults now import the\n"
                "     generated table, so comparing them to the registry compares it\n"
                "     to itself. The migration check this performed is recorded in\n"
                "     selfcheck's 'one kind source' lock; use --check for staleness.",
                file=sys.stderr,
            )
            return 0

    kinds = data["kinds"]
    problems: list = []

    def compare(label: str, want: dict, got: dict) -> None:
        for key in sorted(set(want) | set(got)):
            if want.get(key) != got.get(key):
                problems.append(f"{label}: {key}: registry={got.get(key)!r} legacy={want.get(key)!r}")

    compare("KINDS", dict(ws.KINDS), {k: v["page"] for k, v in kinds.items()})
    compare("KIND_AGENTS", dict(ka.KIND_AGENTS), {k: agent_of(v) for k, v in kinds.items()})
    compare(
        "KIND_COMMANDS",
        dict(wd.KIND_COMMANDS),
        {k: v["command_key"] for k, v in kinds.items() if v.get("command_key")},
    )
    if set(ws.FORBIDDEN) != set(data.get("forbidden") or []):
        problems.append(f"FORBIDDEN: registry={sorted(data['forbidden'])} legacy={sorted(ws.FORBIDDEN)}")
    if set(getattr(ws, "LEGACY_KINDS", set())) != {k for k, v in kinds.items() if v.get("legacy")}:
        problems.append("LEGACY_KINDS differs")
    if tuple(data["agents"]) != tuple(ka.AGENTS):
        problems.append(f"AGENTS: registry={tuple(data['agents'])} legacy={ka.AGENTS}")
    for name, label in (("FACTS_AGENTS", "facts"), ("BOOST_AGENTS", "boost")):
        want = set(getattr(ka, name))
        got = {n for n, a in data["agents"].items() if a.get(label)}
        if want != got:
            problems.append(f"{name}: registry={sorted(got)} legacy={sorted(want)}")
    if dict(ka.READONLY_BREAKS) != {n: a["readonly_breaks"] for n, a in data["agents"].items()}:
        problems.append("READONLY_BREAKS differs")

    if problems:
        for p in problems:
            print("FAIL " + p, file=sys.stderr)
        print(f"{len(problems)} difference(s): the registry is not the current contract", file=sys.stderr)
        return 1
    print(f"OK   registry reproduces all five legacy tables ({len(kinds)} kinds, {len(data['agents'])} agents)")
    return 0


# --- main ------------------------------------------------------------------


def targets(data: dict) -> list:
    return [
        (ROOT / "scripts" / "lib" / "_generated_kinds.py", gen_python(data)),
        (ROOT / "api" / "schemas" / "kinds.schema.json", gen_schema(data)),
        # The Go side embeds the registry, and go:embed cannot reach a parent
        # directory. A hand-made copy would be a second source of truth, so
        # the copy is generated and --check keeps it in step.
        (
            ROOT / "internal" / "adapters" / "kindreg" / "kinds.yaml",
            "# Generated from registry/kinds.yaml by scripts/gen-kinds.py. Do not edit.\n"
            "# Present only because go:embed cannot reach a parent directory.\n"
            + REGISTRY.read_text(encoding="utf-8"),
        ),
        (
            ROOT / "references" / "workflow-schema.md",
            splice(ROOT / "references" / "workflow-schema.md", "kinds", gen_schema_prose(data)),
        ),
        (
            ROOT / "references" / "agents.md",
            splice(ROOT / "references" / "agents.md", "agents-table", gen_agents_prose(data)),
        ),
    ]


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated files are stale")
    parser.add_argument("--diff-legacy", action="store_true", help="compare against the hand-written tables")
    args = parser.parse_args(argv)

    data = load()
    if args.diff_legacy:
        return diff_legacy(data)

    stale = []
    for path, body in targets(data):
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == body:
            continue
        if args.check:
            stale.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")

    if args.check:
        if stale:
            for path in stale:
                print(f"FAIL stale: {path.relative_to(ROOT)}", file=sys.stderr)
            print("HINT run python3 scripts/gen-kinds.py", file=sys.stderr)
            return 1
        print(f"OK   kind generated files are current ({len(data['kinds'])} kinds)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
