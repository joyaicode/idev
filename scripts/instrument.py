#!/usr/bin/env python3
"""The instrument ledger for bounded runtime forensics.

Cursor's debug mode gets its root causes from runtime evidence: add temporary
log statements, reproduce, read what the code actually did, then remove every
instrument before landing. idev had no such channel — idev-ops may not touch
product code (hard rule), so runtime evidence was limited to whatever logs
already existed. This ledger opens a *bounded* channel: idev-coder adds the
logs, but every instrument must be registered here, and the run is not over
until the ledger is empty.

Why a separate file instead of a field on each hypothesis: a disproven
hypothesis stays in the ledger forever (a ruled-out path is evidence), while
an instrument must be gone by the end. Opposite lifecycles — one keeps, one
must clear — do not belong in the same item.

The tag every instrument must carry in code:

    IDEV-DBG <I#>

That is what makes `sweep` possible: `git grep` finds the tag, and the two
directions of the reconciliation catch both ways of cheating — an
unregistered log line someone added, and a registered instrument that
quietly disappeared (moved, edited away, never written).

    instrument.py add   --feature F --hypothesis H1 --file path:line --stub "..."
    instrument.py set   --feature F --id I1 [--status removed] [--note ...]
    instrument.py list  --feature F
    instrument.py sweep --feature F --repo DIR
    instrument.py check --feature F

The ledger is <ticket home>/instruments.yaml. check exits 1 on a finding —
`instrument-residue` is what the cleanup gate (debug-repro gate-cleanup) and
check-feature's ops stage consume: an active instrument blocks PASS until it
is removed and marked so.

Adding an instrument requires the hypothesis to exist in hypotheses.yaml:
forensics serve a named suspicion, they are not a fishing licence.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import safeyaml  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import doc_home  # noqa: E402
    import hypothesis  # noqa: E402
except ImportError:
    print("BLOCKED cannot import doc_home/hypothesis from scripts/; run from the idev repo",
          file=sys.stderr)
    raise SystemExit(2) from None

# The tag that makes an instrument greppable. Registered in the ledger as
# I1, I2, ... and written into the log statement itself, so sweep can
# reconcile both directions.
TAG = "IDEV-DBG"
TAG_RE = re.compile(rf"{TAG}\s+(I\d+)\b")
CODE_REF = re.compile(r"^([\w./-]+\.\w+):(\d+)$")
STATUS = ("active", "removed")


def ledger_path(feature: str, repo: Path | None) -> Path:
    base = (repo or Path.cwd()).resolve()
    return doc_home.intermediate(base, feature, "instruments.yaml")


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
    while f"I{n}" in used:
        n += 1
    return f"I{n}"


def find(items: list[dict], iid: str) -> dict | None:
    for item in items:
        if str(item.get("id")) == iid:
            return item
    return None


def _merge_item(fresh: dict, item: dict) -> dict:
    """Put `item` back into whatever the ledger looks like right now.

    A set started from a copy read before the lock. Writing that whole copy
    back would erase anything another process added meanwhile; merging only
    the one entry keeps both. Same pattern as hypothesis.py.
    """
    fresh.setdefault("items", [])
    for n, existing in enumerate(fresh["items"]):
        if isinstance(existing, dict) and str(existing.get("id")) == str(item.get("id")):
            fresh["items"][n] = item
            return fresh
    fresh["items"].append(item)
    return fresh


def cmd_add(args: argparse.Namespace) -> int:
    m = CODE_REF.match(args.file)
    if not m:
        print(f"BLOCKED --file must be path:line (code-ref), got: {args.file}", file=sys.stderr)
        return 2
    # 加桩先有假设. Cross-load hypotheses.yaml: forensics serve a named
    # suspicion registered in the sibling ledger, they are not a fishing
    # licence. Unreadable sibling ledger is a WARN, not a stop — the two
    # files are written by different hands at different times.
    hyp_path = hypothesis.ledger_path(args.feature, args.repo)
    if not hyp_path.is_file():
        print(f"BLOCKED no hypothesis ledger at {hyp_path}; add a hypothesis first", file=sys.stderr)
        return 2
    hyp_data = hypothesis.load(hyp_path, args.feature)
    if hypothesis.find(safeyaml.as_list(hyp_data.get("items")), args.hypothesis) is None:
        print(f"BLOCKED no such hypothesis: {args.hypothesis}; add it with hypothesis.py add first",
              file=sys.stderr)
        return 2

    path = ledger_path(args.feature, args.repo)
    holder: dict = {}

    def build(data: dict) -> dict:
        data.setdefault("schema_version", 1)
        data.setdefault("feature", args.feature)
        data.setdefault("items", [])
        item = {
            "id": next_id(data["items"]),
            "hypothesis": args.hypothesis,
            "file": m.group(1),
            "line": int(m.group(2)),
            "stub": args.stub,
            "status": "active",
            "added_at": now(),
            "removed_at": "",
            "note": "",
        }
        data["items"].append(item)
        holder["item"] = item
        return data

    safeyaml.save_locked(path, build)
    item = holder["item"]
    print(f"OK   {item['id']} -> {path}")
    print(f"     日志里带上标记: {TAG} {item['id']}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    path = ledger_path(args.feature, args.repo)
    data = load(path, args.feature)
    item = find(safeyaml.as_list(data.get("items")), args.id)
    if item is None:
        print(f"BLOCKED no such instrument: {args.id}", file=sys.stderr)
        return 2
    if args.status:
        if args.status not in STATUS:
            print(f"BLOCKED status must be one of {STATUS}", file=sys.stderr)
            return 2
        item["status"] = args.status
        if args.status == "removed":
            item["removed_at"] = now()
    if args.note:
        item["note"] = args.note
    item["at"] = now()
    safeyaml.save_locked(path, lambda fresh: _merge_item(fresh, item))
    print(f"OK   {args.id} updated -> {path}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    path = ledger_path(args.feature, args.repo)
    data = load(path, args.feature)
    items = [i for i in safeyaml.as_list(data.get("items")) if isinstance(i, dict)]
    if not items:
        print("(没有登记的插桩)")
        return 0
    by_status: dict[str, list[dict]] = {}
    for i in items:
        by_status.setdefault(str(i.get("status", "active")), []).append(i)
    print(f"# 插桩台账  {args.feature}   共 {len(items)} 条")
    print()
    for status, label in (("active", "在桩"), ("removed", "已移除")):
        group = by_status.get(status, [])
        if not group:
            continue
        print(f"## {label}  ({len(group)})")
        for i in group:
            loc = f"{i.get('file')}:{i.get('line')}"
            print(f"  {i.get('id')}  [{i.get('hypothesis')}]  {loc}  {i.get('stub','')}")
        print()
    if by_status.get("active"):
        print("**收尾前必须全部移除**(cleanup gate 吃 instrument.py check 的退出码)。")
    return 0


def grep_tags(repo: Path) -> dict[str, str]:
    """Working-tree tags: I# -> file:line. One direction of the reconciliation."""
    try:
        p = subprocess.run(
            ["git", "grep", "-n", "-E", TAG, "--", "."],
            capture_output=True, text=True, timeout=30, cwd=str(repo),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"WARN git grep failed: {exc}", file=sys.stderr)
        return {}
    if p.returncode not in (0, 1):  # 1 = no match, that is fine
        print(f"WARN git grep rc={p.returncode}: {p.stderr.strip()}", file=sys.stderr)
        return {}
    out: dict[str, str] = {}
    for line in (p.stdout or "").splitlines():
        m = TAG_RE.search(line)
        if not m:
            continue
        # git grep -n output: path:line:content — keep the first I# per hit.
        location, _, _ = line.partition(":")
        out.setdefault(m.group(1), location)
    return out


def sweep(data: dict, repo: Path, errors: list[str]) -> None:
    """Reconcile the ledger against the working tree, both directions."""
    items = [i for i in safeyaml.as_list(data.get("items")) if isinstance(i, dict)]
    tagged = grep_tags(repo)
    active_ids = {str(i.get("id")) for i in items if str(i.get("status")) == "active"}
    # Direction 1: a tag in the tree the ledger never heard of. Someone
    # added a debug log without registering it — the exact hole the
    # bounded channel exists to close.
    for iid, location in sorted(tagged.items()):
        if iid not in {str(i.get("id")) for i in items}:
            errors.append(
                f"{iid}: unregistered-instrument — 工作区里有 {TAG} 标记但台账没登记:"
                f"{location}。要么 instrument.py add 补登记,要么删掉这行日志")
    # Direction 2: registered active, but the tag is gone from the tree.
    # The log moved, was edited away, or was never written — the ledger
    # says one thing, the code says another.
    for i in items:
        iid = str(i.get("id"))
        if str(i.get("status")) == "active" and iid not in tagged:
            errors.append(
                f"{iid}: stale-instrument — 台账是 active 但工作区里找不到 {TAG} {iid} "
                f"(登记在 {i.get('file')}:{i.get('line')})。行挪了或日志没写上:"
                "改行号,或确认已删干净后 set --status removed")


def check(data: dict, repo: Path | None, verbose: bool = True) -> int:
    items = safeyaml.as_list(data.get("items"))
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            errors.append(f"items 里有非 mapping 条目,无法检查: {item!r}")
            continue
        iid = item.get("id", "?")
        if not str(item.get("hypothesis", "")).strip():
            errors.append(f"{iid}: instrument-needs-hypothesis — 插桩必须挂在一条假设上")
        if not str(item.get("stub", "")).strip():
            errors.append(f"{iid}: instrument-needs-stub — 写上这条临时日志长什么样,清理时才找得到")
        if not CODE_REF.match(f"{item.get('file','')}:{item.get('line','')}"):
            errors.append(f"{iid}: instrument-needs-code-ref — 位置必须是 file:line")
    active = [str(i.get("id")) for i in items
              if isinstance(i, dict) and str(i.get("status")) == "active"]
    if active:
        # instrument-residue is what the cleanup gate consumes. An active
        # instrument blocks PASS: the bounded channel is only bounded if the
        # end of the run proves the tree is clean.
        errors.append(
            f"instrument-residue — 还有 {len(active)} 条在桩未移除: {','.join(active)}。"
            "移除日志后 instrument.py set --status removed;"
            "全 removed 才许收尾(gate-cleanup 机检会拦)")
    if repo is not None:
        sweep(data, repo, errors)
    if errors:
        for err in errors:
            print("FAIL " + err, file=sys.stderr)
        return 1
    if verbose:
        total = len([i for i in items if isinstance(i, dict)])
        removed = total - len(active)
        print(f"instrument PASS {total} items ({removed} removed, 0 active)")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    path = ledger_path(args.feature, args.repo)
    if not path.is_file():
        # No ledger means nothing was ever instrumented. That is a pass —
        # the run closed without needing runtime forensics.
        print("instrument PASS (no ledger; nothing was instrumented)")
        return 0
    return check(load(path, args.feature), args.repo)


def cmd_sweep(args: argparse.Namespace) -> int:
    path = ledger_path(args.feature, args.repo)
    data = load(path, args.feature)
    errors: list[str] = []
    sweep(data, args.repo, errors)
    if errors:
        for err in errors:
            print("FAIL " + err, file=sys.stderr)
        return 1
    print("sweep PASS (ledger and working tree agree)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="register an instrument before adding the log line")
    p.add_argument("--feature", required=True)
    p.add_argument("--hypothesis", required=True, help="the H# this instrument serves")
    p.add_argument("--file", required=True, help="path:line where the log goes")
    p.add_argument("--stub", required=True, help="what the temporary log looks like")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("set", help="update an instrument")
    p.add_argument("--feature", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--status", choices=STATUS)
    p.add_argument("--note")
    p.set_defaults(fn=cmd_set)

    p = sub.add_parser("list", help="active / removed, side by side")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("sweep", help="reconcile the ledger against the working tree")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_sweep)

    p = sub.add_parser("check", help="exit 1 on a finding (cleanup gate consumes this)")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_check)

    args = parser.parse_args()
    if args.repo is None and os.environ.get("IDEV_PRODUCT_REPO"):
        args.repo = Path(os.environ["IDEV_PRODUCT_REPO"])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
