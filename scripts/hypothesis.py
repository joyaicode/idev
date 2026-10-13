#!/usr/bin/env python3
"""The hypothesis ledger for root-cause work.

conventions/evidence.md requires that every step designs a case and proves
it before the next step is decided, and that a root cause is only written
once the original symptom has gone red at least once. Hypotheses used to
live in the conversation, where they cannot be counted or revisited.

    hypothesis.py add   --feature F --claim "..." [--case "..."]
    hypothesis.py list  --feature F
    hypothesis.py set   --feature F --id H1 [--case ...] [--evidence P]
                        [--repro yes|no|pending] [--status open|proven|disproven]
    hypothesis.py check --feature F

The ledger is <ticket home>/hypotheses.yaml. check exits 1 on a finding.

Disproven hypotheses are kept, never deleted: a ruled-out path is part of
the evidence chain and keeps the next round from walking it again.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402

sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
try:
    import doc_home  # noqa: E402
except ImportError:
    print(f"BLOCKED cannot import doc_home from {kind_agents.kernel_root()}; set IDEV_ROOT", file=sys.stderr)
    raise SystemExit(2) from None

REPRO = ("pending", "yes", "no")
STATUS = ("open", "proven", "disproven")


def ledger_path(feature: str, repo: Path | None) -> Path:
    base = (repo or Path.cwd()).resolve()
    return doc_home.homes(base, feature)["task"] / "hypotheses.yaml"


def load(path: Path, feature: str) -> dict:
    """The ledger, or a fresh one. A broken file starts over rather than crashing."""
    if path.is_file():
        data = safeyaml.mapping(path)
        if data is None:
            print(f"WARN unreadable ledger, starting a fresh one: {path}", file=sys.stderr)
        else:
            data.setdefault("items", [])
            if not isinstance(data["items"], list):
                print(f"WARN items is not a list, reset: {path}", file=sys.stderr)
                data["items"] = []
            return data
    return {"schema_version": 1, "feature": feature, "items": []}


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safeyaml.dump(data), encoding="utf-8")


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def next_id(items: list[dict]) -> str:
    used = {str(i.get("id", "")) for i in items}
    n = 1
    while f"H{n}" in used:
        n += 1
    return f"H{n}"


def find(items: list[dict], hid: str) -> dict | None:
    for item in items:
        if str(item.get("id")) == hid:
            return item
    return None


def cmd_add(args: argparse.Namespace) -> int:
    path = ledger_path(args.feature, args.repo)
    data = load(path, args.feature)
    item = {
        "id": next_id(data["items"]),
        "claim": args.claim,
        "case": args.case or "",
        "evidence": [],
        "repro": "pending",
        "status": "open",
        "at": now(),
    }
    data["items"].append(item)
    save(path, data)
    print(f"OK   {item['id']} -> {path}")
    if not args.case:
        print("HINT no case yet; evidence.md wants a runnable case before the next hypothesis")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    path = ledger_path(args.feature, args.repo)
    data = load(path, args.feature)
    item = find(data["items"], args.id)
    if item is None:
        print(f"BLOCKED no such hypothesis: {args.id}", file=sys.stderr)
        return 2
    if args.case:
        item["case"] = args.case
    if args.evidence:
        item.setdefault("evidence", []).extend(args.evidence)
    if args.repro:
        item["repro"] = args.repro
    if args.status:
        item["status"] = args.status
    item["at"] = now()
    save(path, data)
    rc = check(data, verbose=False)
    if rc == 0:
        print(f"OK   {args.id} updated -> {path}")
    else:
        # Saved deliberately: the ledger records the process, including a
        # state whose evidence is still being assembled. The finding printed
        # above says what is missing before it counts as proven.
        print(f"SAVED {args.id} -> {path}(已写入,但未通过检查,见上)", file=sys.stderr)
    return rc


def cmd_list(args: argparse.Namespace) -> int:
    data = load(ledger_path(args.feature, args.repo), args.feature)
    if not data["items"]:
        print("(no hypotheses)")
        return 0
    for item in safeyaml.as_list(data.get("items")):
        if not isinstance(item, dict):
            print(f"(非 mapping 条目,跳过: {item!r})")
            continue
        ev = len(safeyaml.as_list(item.get("evidence")))
        print(f"{item.get('id')}  {item.get('status','?'):10} repro={item.get('repro','?'):7} evidence={ev}  {item.get('claim','')}")
        if item.get("case"):
            print(f"      case: {item['case']}")
    return 0


def check(data: dict, verbose: bool = True) -> int:
    items = safeyaml.as_list(data.get("items"))
    errors: list[str] = []
    warns: list[str] = []

    for item in items:
        if not isinstance(item, dict):
            errors.append(f"items 里有非 mapping 条目,无法检查: {item!r}")
            continue
        hid = item.get("id", "?")
        status = str(item.get("status", "open"))
        raw_evidence = item.get("evidence")
        evidence = safeyaml.as_list(raw_evidence)
        if raw_evidence and not evidence:
            # A bare string would otherwise iterate character by character
            # and report every letter as a missing path.
            warns.append(f"{hid}: evidence 应是列表,已忽略: {raw_evidence!r}")

        if status == "proven":
            if str(item.get("repro")) != "yes":
                errors.append(f"{hid}: proven-needs-repro — status proven but repro={item.get('repro')}")
            if not evidence:
                errors.append(f"{hid}: proven-needs-evidence — status proven with no evidence path")
        for path in evidence:
            if not Path(str(path)).exists():
                warns.append(f"{hid}: evidence path not found: {path}")

    # case-before-next: an open hypothesis with no case, while later ones exist.
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if str(item.get("status", "open")) == "open" and not str(item.get("case", "")).strip():
            if i < len(items) - 1:
                errors.append(
                    f"{item.get('id','?')}: case-before-next — still open with no case, "
                    f"but {len(items) - i - 1} later hypothesis(es) were added"
                )

    for warn in warns:
        print("WARN " + warn, file=sys.stderr)
    if errors:
        for err in errors:
            print("FAIL " + err, file=sys.stderr)
        return 1
    if verbose:
        proven = sum(1 for i in items if i.get("status") == "proven")
        disproven = sum(1 for i in items if i.get("status") == "disproven")
        print(f"hypothesis PASS {len(items)} items ({proven} proven, {disproven} disproven)")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    return check(load(ledger_path(args.feature, args.repo), args.feature))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="add a hypothesis")
    p.add_argument("--feature", required=True)
    p.add_argument("--claim", required=True)
    p.add_argument("--case", help="the runnable case that would prove or disprove it")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("set", help="update a hypothesis")
    p.add_argument("--feature", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--case")
    p.add_argument("--evidence", action="append", help="repeatable")
    p.add_argument("--repro", choices=REPRO)
    p.add_argument("--status", choices=STATUS)
    p.set_defaults(fn=cmd_set)

    p = sub.add_parser("list", help="list hypotheses")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("check", help="exit 1 on a finding")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_check)

    args = parser.parse_args()
    if args.repo is None and os.environ.get("IDEV_PRODUCT_REPO"):
        args.repo = Path(os.environ["IDEV_PRODUCT_REPO"])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
