#!/usr/bin/env python3
"""The finding ledger, read straight out of review.md.

Bugbot tracks each finding's resolution (resolved / unresolved) and reports
an acceptance rate per rule. idev's review.md carried only two states —
待签收 when the report landed, 已签收 once a person nodded — and then the
I* simply vanished into review.fix. Nothing answered "how many findings did
the reviewer raise, how many were fixed, how many were dismissed as noise"
— which is exactly the number that says whether a reviewer is finding real
problems or writing fiction.

The four states (deliver/references/review.example.md):

    ### I1 待签收   the report landed
    ### I1 已签收   a person nodded
    ### I1 已解决   review.fix cleared it and verify is green
    ### I1 已驳回   a person ruled it out — with a why on the next line

The checks, in the spirit of hypothesis.py (a ruled-out path needs its
reason recorded, or the next round walks it again):

    finding-needs-anchor   an I* with no file:method anchor — the conductor
                           cannot re-dispatch what cannot be located
    dismissed-needs-why    已驳回 without a reason line — the same finding
                           gets re-reported next round, and nobody learns
                           why it was not worth fixing
    finding-recurred       the same anchor was marked 已解决 in an earlier
                           round and is back — a regression signal (WARN)

    review-findings.py check --feature F [--repo DIR]
    review-findings.py stats --feature F [--repo DIR]

check exits 1 on a finding. stats prints one line, for ticket-metrics and
for the close-out report.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import safeyaml  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import doc_home  # noqa: E402
except ImportError:
    print("BLOCKED cannot import doc_home from scripts/; run from the idev repo",
          file=sys.stderr)
    raise SystemExit(2) from None

# The four states, one regex so the parsers can never disagree.
STATES = ("待签收", "已签收", "已解决", "已驳回")
FINDING_RE = re.compile(r"(?m)^### (I\d+) (待签收|已签收|已解决|已驳回)\s*$")
# file:method — the anchor granularity idev-reviewer.md hard rule 6 demands.
ANCHOR = re.compile(r"[\w./-]+\.\w+:[\w.$<>-]+")
# The reason a dismissal must carry — a marker (驳回/理由/why) followed by a
# colon, anywhere in a line of its own section. Leading prose before the
# marker reads as a sentence anyway; what matters is the reason is written.
WHY_RE = re.compile(r"(?:驳回|理由|why)\s*[:：]\s*([^\n]+)")


def review_path(feature: str, repo: Path | None) -> Path:
    base = (repo or Path.cwd()).resolve()
    return doc_home.homes(base, feature)["work"] / "review.md"


def parse(text: str) -> list[dict]:
    """Every I* heading with its section body, in document order."""
    out: list[dict] = []
    hits = list(FINDING_RE.finditer(text))
    for n, hit in enumerate(hits):
        end = hits[n + 1].start() if n + 1 < len(hits) else len(text)
        body = text[hit.end():end]
        out.append({
            "id": hit.group(1),
            "status": hit.group(2),
            "body": body,
            "anchor": (ANCHOR.search(body) or [None])[0]
            if ANCHOR.search(body) else "",
            "why": (WHY_RE.search(body).group(1).strip()
                    if WHY_RE.search(body) else ""),
        })
    return out


def anchors_of(items: list[dict]) -> set[str]:
    """Every anchor a finding named, for the recurrence check."""
    out: set[str] = set()
    for item in items:
        for hit in ANCHOR.finditer(item["body"]):
            out.add(hit.group(0))
    return out


def check(items: list[dict], resolved_before: set[str] | None = None) -> int:
    errors: list[str] = []
    warns: list[str] = []
    resolved_before = resolved_before or set()

    for item in items:
        fid, status = item["id"], item["status"]
        # finding-needs-anchor: reviewer.md hard rule 6, enforced. An I* the
        # conductor cannot locate cannot be re-dispatched to the coder.
        if not item["anchor"]:
            errors.append(
                f"{fid}: finding-needs-anchor — I* 必须给 file:方法名 锚点。"
                "没有锚点的发现没法重派给生成者,也不知道改的是不是那一处")
        # dismissed-needs-why: the same shape as disproven-needs-proof. A
        # dismissal without a reason is re-reported next round — the record
        # exists to stop exactly that.
        if status == "已驳回" and not item["why"]:
            errors.append(
                f"{fid}: dismissed-needs-why — 已驳回必须写一行理由"
                "(驳回: <为什么不修>)。没有理由的驳回,下一轮会重报同一条,"
                "而且没人知道它为什么不值得修")

    # finding-recurred: an anchor marked resolved in an earlier round that
    # is back on the board. A regression signal, not a failure of this
    # round — WARN, the person decides what it means.
    for item in items:
        if item["status"] in ("待签收", "已签收") and item["anchor"] \
                and item["anchor"] in resolved_before:
            warns.append(
                f"{item['id']}: finding-recurred — {item['anchor']} 在既往轮次"
                "标过已解决,现在又出现在待修清单里。回归信号:要么上次的修复"
                "没盖住这个面,要么这条 finding 是误报(那它的驳回理由更该写)")

    for warn in warns:
        print("WARN " + warn, file=sys.stderr)
    if errors:
        for err in errors:
            print("FAIL " + err, file=sys.stderr)
        return 1
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    path = review_path(args.feature, args.repo)
    if not path.is_file():
        print("review-findings PASS (no review.md; nothing was reviewed)")
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    items = parse(text)
    # Earlier rounds: sections kept below a "## 既往轮次" heading, or prior
    # review backups (review.<n>.md) in the same directory.
    resolved_before = _resolved_before(path, text)
    rc = check(items, resolved_before)
    if rc == 0:
        by = _count_by(items)
        print("review-findings PASS %d findings (%s)"
              % (len(items), ", ".join(f"{k} {v}" for k, v in by.items())))
    return rc


def _resolved_before(path: Path, text: str) -> set[str]:
    """Anchors marked 已解决 in earlier rounds of the same ticket."""
    resolved: set[str] = set()
    # Old rounds are archived as review.<n>.md beside the live review.md.
    for old in sorted(path.parent.glob("review.[0-9]*.md")):
        for item in parse(old.read_text(encoding="utf-8", errors="replace")):
            if item["status"] == "已解决":
                resolved |= set(ANCHOR.findall(item["body"]))
    # A "## 既往轮次" section inside the live file carries the same signal.
    m = re.search(r"(?m)^## 既往轮次\s*$", text)
    if m:
        for item in parse(text[m.end():]):
            if item["status"] == "已解决":
                resolved |= set(ANCHOR.findall(item["body"]))
    return resolved


def _count_by(items: list[dict]) -> dict[str, int]:
    by: dict[str, int] = {}
    for item in items:
        by[item["status"]] = by.get(item["status"], 0) + 1
    return by


def cmd_stats(args: argparse.Namespace) -> int:
    path = review_path(args.feature, args.repo)
    if not path.is_file():
        print("findings: 0")
        return 0
    items = parse(path.read_text(encoding="utf-8", errors="replace"))
    by = _count_by(items)
    open_now = by.get("待签收", 0) + by.get("已签收", 0)
    print("findings: %d 签收 %d 解决 %d 驳回 %d open %d"
          % (len(items), by.get("已签收", 0), by.get("已解决", 0),
             by.get("已驳回", 0), open_now))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="exit 1 on a finding")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("stats", help="one line: raised / signed / resolved / dismissed / open")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_stats)

    args = parser.parse_args()
    if args.repo is None and os.environ.get("IDEV_PRODUCT_REPO"):
        args.repo = Path(os.environ["IDEV_PRODUCT_REPO"])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
