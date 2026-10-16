#!/usr/bin/env python3
"""Which recorded signoffs stop being valid under the tightened rules.

P0 made `is_human` and `is_confirm` strict. The design's own mitigation was
to grandfather old files with a WARN; this repo chose strict instead, which
is only safe if someone has actually looked at what breaks. That is this
script: read-only, exits 0 whatever it finds, prints the list a person needs
in order to decide between re-signing and relaxing.

    python3 scripts/signoff-audit.py                 # kernel + the registered product
    python3 scripts/signoff-audit.py --repo PATH     # one checkout
    python3 scripts/signoff-audit.py --json

A finding is not automatically a problem. Most `by: agent` rows already
failed before P0 — those are listed as `was-already-failing` so they do not
inflate the number that matters, which is `newly-failing`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import roots  # noqa: E402
import safeyaml  # noqa: E402
import workflow_spec as spec  # noqa: E402

# The fields that record who signed and what they said.
BY_KEYS = ("by", "confirmed_by", "signed_by")
QUOTE_KEYS = ("quote", "confirm", "utterance")

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
            now_ok = spec.is_human(by)
            if now_ok:
                continue
            out.append(
                {
                    "file": str(path),
                    "at": f"{where}.{key}" if where else key,
                    "field": key,
                    "value": by,
                    "verdict": "newly-failing" if old_is_human(by) else "was-already-failing",
                    "why": "not a person" if by.strip() else "empty",
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
            out.append(
                {
                    "file": str(path),
                    "at": f"{where}.{key}" if where else key,
                    "field": key,
                    "value": quote,
                    "verdict": "newly-failing" if old_is_confirm(quote) else "was-already-failing",
                    "why": parsed.reason,
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
    args = parser.parse_args(argv)

    kernel = roots.kernel_root()
    targets = [Path(r).expanduser().resolve() for r in args.repo] or (
        [kernel] + registered_products(kernel)
    )

    findings = []
    for repo in targets:
        findings.extend(scan(repo))

    if args.json:
        print(json.dumps({"targets": [str(t) for t in targets], "findings": findings},
                         ensure_ascii=False, indent=2))
        return 0

    new = [f for f in findings if f["verdict"] == "newly-failing"]
    old = [f for f in findings if f["verdict"] == "was-already-failing"]

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
    print()

    if new:
        print("These need a person to re-sign, or the rule relaxed:")
        for f in new:
            print(f"  {f['file']}")
            print(f"    {f['at']} = {f['value']!r}  ({f['why']})")
        print()
    else:
        print("Nothing newly breaks. Strict mode is safe to keep.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
