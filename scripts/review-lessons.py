#!/usr/bin/env python3
"""Digest resolved review findings into lessons candidates.

Bugbot learns rules from PR activity automatically and applies them to
future reviews. idev's lessons ledger already has the stricter half of that
— six questions, human promote, recall with CONFLICT — but nothing fed it
from the review side: a finding the reviewer raised, the coder fixed and
verify proved green is exactly the six-question shape, and it was being
written into review.md and then forgotten.

    review-lessons.py digest --feature F [--repo DIR] [--dry-run]

Reads the 已解决 findings in review.md and turns each into a lessons
candidate through lessons.py add (its gates untouched):

    scope      the top-level module of the anchor file
    symptom    the finding's first line (what was wrong, where)
    evidence   review.md + the anchor itself
    action     the fix line from the section (修复: ...)
    outcome    verify result (结果: ... — from the section or the report)
    not_when   "单次出现且无复现" by default — a single occurrence with no
               recurrence is the boundary, and saying so is mandatory

Six answers or no candidate: a finding missing its fix line is printed and
skipped, never guessed at (宁缺勿滥 — an auto-promoted rule is exactly the
"one local error becomes a class of errors" path rootcause-guards.md
exists to block). --dry-run prints what would land, writes nothing.
Re-running on the same review.md does not duplicate: a candidate with the
same scope+symptom already in the ledger is left alone.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import safeyaml  # noqa: E402

HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import doc_home  # noqa: E402
    import lessons  # noqa: E402
except ImportError:
    print("BLOCKED cannot import doc_home/lessons from scripts/; "
          "run from the idev repo", file=sys.stderr)
    raise SystemExit(2) from None

# review-findings.py has a hyphen in its name: not importable the normal
# way. Load it by path, the same trick suspect-changes.py uses for
# artifact-match.py.
def _load_review_findings():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "review_findings", HERE / "review-findings.py")
    if spec is None or spec.loader is None:
        print("BLOCKED cannot load review-findings.py", file=sys.stderr)
        raise SystemExit(2)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


review_findings = _load_review_findings()

HERE = Path(__file__).resolve().parent

# The fix and outcome lines inside a resolved finding's section.
FIX_RE = re.compile(r"(?m)(?:修复|fix)\s*[:：]\s*([^\n]+)")
OUTCOME_RE = re.compile(r"(?m)(?:结果|outcome|验证)\s*[:：]\s*([^\n]+)")

DEFAULT_NOT_WHEN = "单次出现且无复现"


def review_path(feature: str, repo: Path | None) -> Path:
    base = (repo or Path.cwd()).resolve()
    return doc_home.homes(base, feature)["work"] / "review.md"


def top_module(anchor: str) -> str:
    """The anchor file's top-level source module, or the file itself."""
    path = anchor.split(":")[0]
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return path


def candidates(review: Path) -> list[dict]:
    """Resolved findings with the six answers, or [] — never a guess."""
    if not review.is_file():
        return []
    items = review_findings.parse(review.read_text(encoding="utf-8", errors="replace"))
    out: list[dict] = []
    for item in items:
        if item["status"] != "已解决" or not item["anchor"]:
            continue
        fix = FIX_RE.search(item["body"])
        outcome = OUTCOME_RE.search(item["body"])
        first_line = ""
        for line in item["body"].strip().splitlines():
            # The symptom line is the first line that is not the fix/outcome
            # marker pair — the finding's own sentence.
            if FIX_RE.search(line) or OUTCOME_RE.search(line):
                continue
            # The anchor often leads the sentence; the sentence without it
            # is the symptom (the anchor is recorded on its own line above).
            stripped = line.strip()
            if stripped.startswith(item["anchor"]):
                stripped = stripped[len(item["anchor"]):].lstrip("—-– \t")
            if stripped:
                first_line = stripped
                break
        if not first_line:
            continue
        out.append({
            "scope": top_module(item["anchor"]),
            "symptom": "%s — %s" % (item["anchor"], first_line[:80]),
            "evidence": "%s#%s" % (review, item["id"]),
            "action": fix.group(1).strip() if fix else "",
            "outcome": outcome.group(1).strip() if outcome else "",
            "not_when": DEFAULT_NOT_WHEN,
            "id": item["id"],
        })
    return out


def existing_pairs(ledger: Path) -> set[tuple[str, str]]:
    """(scope, symptom) already in the lessons ledger, for idempotence."""
    if not ledger.is_file():
        return set()
    data = safeyaml.mapping(ledger) or {}
    # The ledger key is `lessons` (see lessons.py SCHEMA), not `items`.
    rows = safeyaml.as_list(data.get("lessons")) or safeyaml.as_list(data.get("items"))
    out: set[tuple[str, str]] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        out.add((str(item.get("scope") or ""), str(item.get("symptom") or "")))
    return out


def ledger_path(feature: str, repo: Path | None) -> Path:
    base = (repo or Path.cwd()).resolve()
    return doc_home.intermediate(base, feature, "lessons.yaml")


def cmd_digest(args: argparse.Namespace) -> int:
    review = review_path(args.feature, args.repo)
    cands = candidates(review)
    if not cands:
        print("(no digestible findings — 没有「已解决」且带锚点的 I*)")
        return 0
    have = existing_pairs(ledger_path(args.feature, args.repo))
    landed = 0
    for cand in cands:
        # 六问齐才落: a finding with no recorded fix cannot teach a rule —
        # the action is the part the next review would use.
        if not cand["action"]:
            print("SKIP %s 六问缺「action」(section 里没有 修复: 行),不落候选 —— "
                  "宁缺勿滥,猜出来的修复方式会变成下轮的错误尺" % cand["id"])
            continue
        if (cand["scope"], cand["symptom"]) in have:
            print("SKIP %s 已有同 scope+symptom 候选,不重复落" % cand["id"])
            continue
        line = ("lessons.py add --scope %s --symptom %s --action %s "
                "--not_when %s" % (cand["scope"], cand["symptom"],
                                   cand["action"], cand["not_when"]))
        if args.dry_run:
            print("DRY  %s %s" % (cand["id"], line))
            continue
        done = subprocess.run(
            [sys.executable, str(HERE / "lessons.py"),
             "--repo", str(args.repo.resolve() if args.repo else Path.cwd()),
             "--feature", args.feature, "add",
             "--scope", cand["scope"], "--symptom", cand["symptom"],
             "--evidence", cand["evidence"], "--action", cand["action"],
             "--outcome", cand["outcome"] or "verify 绿(见 review.md)",
             "--not-when", cand["not_when"], "--event", "verified"],
            capture_output=True, text=True, timeout=60)
        if done.returncode != 0:
            print("WARN  %s lessons add rc=%d: %s"
                  % (cand["id"], done.returncode, (done.stdout + done.stderr).strip()))
            continue
        have.add((cand["scope"], cand["symptom"]))
        landed += 1
        print("OK   %s -> lessons candidate (scope=%s)" % (cand["id"], cand["scope"]))
    if not args.dry_run:
        print("digest landed %d candidate(s);promote 仍须人 + 旁路复现(lessons.py promote)"
              % landed)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("digest", help="resolved findings -> lessons candidates")
    p.add_argument("--feature", required=True)
    p.add_argument("--dry-run", action="store_true", help="print what would land, write nothing")
    p.set_defaults(fn=cmd_digest)

    args = parser.parse_args()
    if args.repo is None and os.environ.get("IDEV_PRODUCT_REPO"):
        args.repo = Path(os.environ["IDEV_PRODUCT_REPO"])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
