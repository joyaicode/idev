#!/usr/bin/env python3
"""Which recorded signoffs stop being valid under the tightened rules.

P0 made `is_human` and `is_confirm` strict. The design's own mitigation was
to grandfather old files with a WARN; this repo chose strict instead, which
is only safe if someone has actually looked at what breaks. That is this
script: read-only, exits 0 whatever it finds, prints the list a person needs
in order to decide between re-signing and relaxing.

    python3 scripts/signoff-audit.py                 # kernel + the registered product
    python3 scripts/signoff-audit.py --repo PATH     # one checkout
    python3 scripts/signoff-audit.py --all           # the raw sweep, nothing folded
    python3 scripts/signoff-audit.py --json

A finding is not automatically a problem. Most `by: agent` rows already
failed before P0 — those are listed as `was-already-failing` so they do not
inflate the number that matters, which is `newly-failing`.

Not every `by` is a signature. The same key records who signed in one place
and who did the work in another, and the true sources say which is which;
judging both by `is_human` made 25 of 27 `newly-failing` rows report the
shape those sources ask for. `--all` still prints the raw sweep, because
triaging the blast radius of a rule change wants it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import roots  # noqa: E402
import safeyaml  # noqa: E402
import workflow_spec as spec  # noqa: E402

# The fields that record who signed and what they said.
BY_KEYS = ("by", "confirmed_by", "signed_by")
QUOTE_KEYS = ("quote", "confirm", "utterance")

# Where a bare `by` names whoever did the work rather than whoever signed.
# trace.md writes `recorded[].by` as "签字人，否则执行者，否则 conductor";
# workflow-schema.md has `record PASS --verified-by <agent>` land in
# `verification.by`; `revisions[]` is a changelog, and the same file carries
# both a person and an agent in it. Holding these to `is_human` reports the
# shape the true source asks for as a failure.
ACTOR_PARENTS = ("verification", "recorded", "delegations", "revisions")

# Where a bare `quote` is a confirmation. `decisions[].quote` is not one:
# workflow-schema.md separates the two — "决策不是签字：它记人对一个问题的
# 回答，不授权写签字字段" — so an answer that reads nothing like 确认 is the
# normal case there, not a signature that stopped being valid.
SIGNOFF_PARENTS = ("signoff", "human_signoff")

# The names this system hands work to. This is not a relaxation of
# `is_human`: an actor field still refuses a word that names nobody at all,
# which is how a placeholder like `by: human` stays visible instead of
# hiding behind the field's own looseness.
ACTORS = frozenset(a.lower() for a in kind_agents.AGENTS) | {"conductor"}

# What the old implementation accepted, so a finding can say whether P0
# changed this row's verdict or merely reported one that already failed.
OLD_AGENT_NAMES = {"agent", "ai", "cursor", "assistant"}
OLD_CONFIRM_WORDS = ("确认", "全签", "同意", "lgtm")


def old_is_human(by: str) -> bool:
    name = str(by or "").strip()
    return bool(name) and name.lower() not in OLD_AGENT_NAMES


def old_is_confirm(quote: str) -> bool:
    low = str(quote or "").strip().strip("。.!！ ").lower()
    return any(low.startswith(w) for w in OLD_CONFIRM_WORDS)


def walk(node, path: str = ""):
    """Every mapping in a parsed yaml document, with a dotted path."""
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk(value, f"{path}[{i}]")


_INDEX_RE = re.compile(r"\[\d+\]$")


def parent_of(where: str) -> str:
    """The mapping key a field hangs off, with any list index dropped.

    `steps[0].verification` -> `verification`, `recorded[3]` -> `recorded`.
    """
    if not where:
        return ""
    return _INDEX_RE.sub("", where.rsplit(".", 1)[-1])


def field_class(where: str, key: str) -> str:
    """`signoff` when the field records who signed, `actor` when it records
    who did the work."""
    parent = parent_of(where)
    if key == "by":
        return "actor" if parent in ACTOR_PARENTS else "signoff"
    if key == "quote":
        return "signoff" if parent in SIGNOFF_PARENTS else "actor"
    # `confirmed_by` / `signed_by` / `confirm` / `utterance` say it in the key.
    return "signoff"


def is_actor(name: str) -> bool:
    """True when the name is one this system hands work to."""
    return str(name or "").strip().lower() in ACTORS


def findings_for(path: Path) -> list:
    data = safeyaml.mapping(path)
    if not data:
        return []
    out = []
    for where, node in walk(data):
        for key in BY_KEYS:
            if key not in node:
                continue
            by = node.get(key)
            if not isinstance(by, (str, int, float)):
                continue
            by = str(by)
            if spec.is_human(by):
                continue
            kind = field_class(where, key)
            if not by.strip():
                # No signature was ever made here, so none stopped being valid.
                why, reportable = "empty", False
            elif kind == "actor":
                reportable = not is_actor(by)
                why = (
                    "names neither a person nor an agent"
                    if reportable
                    else "an agent, which this field is allowed to name"
                )
            else:
                why, reportable = "not a person", True
            out.append(
                {
                    "file": str(path),
                    "at": f"{where}.{key}" if where else key,
                    "field": key,
                    "class": kind,
                    "value": by,
                    "verdict": "newly-failing" if old_is_human(by) else "was-already-failing",
                    "why": why,
                    "reportable": reportable,
                }
            )
        for key in QUOTE_KEYS:
            if key not in node:
                continue
            quote = node.get(key)
            if not isinstance(quote, str):
                continue
            parsed = spec.parse_confirm(quote)
            if parsed.ok:
                continue
            kind = field_class(where, key)
            if not quote.strip():
                why, reportable = "empty", False
            elif kind == "actor":
                why, reportable = "an answer to a question, not a signoff", False
            else:
                why, reportable = parsed.reason, True
            out.append(
                {
                    "file": str(path),
                    "at": f"{where}.{key}" if where else key,
                    "field": key,
                    "class": kind,
                    "value": quote,
                    "verdict": "newly-failing" if old_is_confirm(quote) else "was-already-failing",
                    "why": why,
                    "reportable": reportable,
                }
            )
    return out


def scan(repo: Path) -> list:
    out = []
    for sub in (".idev", "docs", "state", "verify"):
        base = repo / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.yaml")):
            out.extend(findings_for(path))
    return out


def registered_products(kernel: Path) -> list:
    """Product checkouts this machine's install ledger knows about."""
    cfg = kernel / "state" / "outbound-config.json"
    if not cfg.is_file():
        return []
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for key in ("product_root", "joypaas_root"):
        raw = str(data.get(key) or "").strip()
        if raw:
            path = Path(raw).expanduser()
            if path.is_dir() and path not in out:
                out.append(path)
    return out


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=[], help="a checkout to scan")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--all",
        action="store_true",
        help="the raw sweep: actor fields and empty values too",
    )
    args = parser.parse_args(argv)

    kernel = roots.kernel_root()
    targets = [Path(r).expanduser().resolve() for r in args.repo] or (
        [kernel] + registered_products(kernel)
    )

    findings = []
    for repo in targets:
        findings.extend(scan(repo))

    folded = [f for f in findings if not f["reportable"]]
    shown = findings if args.all else [f for f in findings if f["reportable"]]

    if args.json:
        print(json.dumps({"targets": [str(t) for t in targets], "findings": shown},
                         ensure_ascii=False, indent=2))
        return 0

    new = [f for f in shown if f["verdict"] == "newly-failing"]
    old = [f for f in shown if f["verdict"] == "was-already-failing"]

    print(f"scanned {len(targets)} checkout(s):")
    for t in targets:
        print(f"  {t}")
    print()
    if spec.people_warning():
        print(f"WARN {spec.people_warning()}")
        print("     a whitelist would make this stricter; rerun after adding one")
        print()

    print(f"newly-failing      {len(new):4}   <- P0 changed the verdict on these")
    print(f"was-already-failing{len(old):4}   <- broken before P0 too, not a regression")
    if folded and not args.all:
        print(f"not shown          {len(folded):4}   <- actor fields and empty values; --all for those")
    print()

    if new:
        # Two different things need saying. A signature field holding a
        # non-person is someone's signoff that no longer counts. An actor
        # field holding a role word is a changelog written before names were
        # used there — nobody has a signature to re-make.
        sign = [f for f in new if f["class"] == "signoff"]
        actors = [f for f in new if f["class"] == "actor"]
        if sign:
            print("These need a person to re-sign, or the rule relaxed:")
            for f in sign:
                print(f"  {f['file']}")
                print(f"    {f['at']} = {f['value']!r}  ({f['why']})")
            print()
        if actors:
            print("These name nobody where a name belongs. Not lapsed signatures —")
            print("records of work whose `by` is a role word. Re-signing is not the fix:")
            for f in actors:
                print(f"  {f['file']}")
                print(f"    {f['at']} = {f['value']!r}  ({f['why']})")
            print()
    elif old:
        print("No signoff stopped being valid under P0. The rows above failed before it too.")
    else:
        print("PASS  no signoff stopped being valid.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
