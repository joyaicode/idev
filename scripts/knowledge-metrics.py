#!/usr/bin/env python3
"""The 93 canon/coding-tables numbers, at runtime — not just on paper.

deep-read-audit answers a static question: for each number, if someone
violates it tomorrow, what stops them (defined / trigger / staged /
enforced)? This script adds the runtime half: how often the numbers actually
fired while work was happening — §0 declarations in coder delegation
records (CANON_TRIGGER / TABLE_HIT), reviewer citations in review.md, and
the hit-applied check that says a declared hit reached the code. Static
reachability crossed with runtime hits, one row per number.

    knowledge-metrics.py [--repo <checkout>] [--kernel <root>] [--days N]
                         [--ids C22,P15] [--signal]

Zero runtime hits is not a verdict. A number enforced by the plugin never
needs a human to remember it (that is the point of enforced), and the §0
table sweep reaches every C#/P# by construction. So the classification
follows deep-read-audit's own layers: numbers with trigger but no runtime
hit are wording candidates (listed, never changed here); numbers that are
only defined are miss-candidates; the rest need no hit. Any per-number
verdict waits for ≥ MIN_SAMPLE coder records that actually carry §0
declarations — three records do not convict a rule.

Counts, not scores. Nothing here gates anything, and changing a trigger
line still goes through a proposal, a grill, and a person.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import delegation  # noqa: E402
import kind_agents  # noqa: E402
import record_paths  # noqa: E402
import safeyaml  # noqa: E402
import textwidth as tw  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
KERNEL = SCRIPTS.parent
MIN_SAMPLE = 20

REVIEW_KIND = "review.report"


def _load_module(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_audit():
    """deep-read-audit.py has a hyphen; load it the way the tests do."""
    try:
        import deep_read_audit  # noqa: F401  (only if someone pre-imported)
        return sys.modules["deep_read_audit"]
    except ImportError:
        return _load_module("deep_read_audit", "deep-read-audit.py")


# Families swept whole by coding.md §0 step 5 (every new function scans the
# full C# and P# tables), so a runtime hit for any single member is not the
# only evidence the family reaches executors.
SWEPT_FAMILIES = ("C", "P")

RANGE = re.compile(r"\b([TCPRAF])(\d{1,2})\s*[–-]\s*(?:\1)?(\d{1,2})\b")
NUMBER = re.compile(r"\b([TCPRAF]\d{1,2})\b")


def hit_numbers(text: str) -> set[str]:
    """Numbers a TABLE_HIT value actually claims as hits.

    The value is free text by contract. Two shapes need care: a declared
    non-hit range ("P1–P14 不命中" — the numbers exist only to say they did
    NOT hit) and bookend ranges meaning the whole family ("P1–P14"). Both
    are excluded: only numbers outside any range expression count, so a
    report saying "P15（…）。P1–P14 不命中" charges P15 alone.
    """
    claimed: set[str] = set()
    skip = [(m.start(), m.end()) for m in RANGE.finditer(text)]
    for m in NUMBER.finditer(text):
        if any(a <= m.start() < b for a, b in skip):
            continue
        claimed.add(m.group(1))
    return claimed


def coder_facts(record: dict) -> dict | None:
    raw = str((record.get("report") or {}).get("raw", ""))
    if not (delegation.S0_CHANGE_KIND.search(raw)
            or delegation.S0_CANON_TRIGGER.search(raw)
            or delegation.S0_TABLE_HIT.search(raw)):
        return None
    trigger = delegation.S0_CANON_TRIGGER.search(raw)
    table = delegation.S0_TABLE_HIT.search(raw)
    # TABLE_HIT values are free text by contract ("P15（说明）", "C5、C7",
    # "P1–P14 不命中"); numbers count only when the hit is real — a 无/零命中
    # line mentions no numbers anyway, so findall on the value is enough.
    return {
        "canon_trigger": trigger.group(1).strip() if trigger else "",
        "table_hit": table.group(1).strip() if table else "",
        "hits": sorted(set(delegation.T_NUMBER.findall(raw))),
    }


def reviewer_citations(records, repo: Path | None) -> Counter:
    """Number citations in the evidence files of review.report records.

    review.md itself plus its review/shards/*.md, matching what the
    reviewer is allowed to write (delegation._review_write's two places).
    """
    counter: Counter = Counter()
    audit = load_audit()
    base = (repo or Path.cwd()).resolve()
    for _path, record in records:
        if str(record.get("kind", "")) != REVIEW_KIND:
            continue
        evidence = delegation.read_evidence(record, repo)
        if evidence is None:
            continue
        # read_evidence returns text, not a path; find the file again for the
        # shards directory beside it. "review.md" resolves inside the ticket
        # directory (docs/task/<f>/review.md), so its shards are
        # <ticket>/review/shards/ — the reviewer's second write place.
        texts = [evidence]
        rel = delegation.report_evidence(record)
        if rel and rel != "-":
            target = Path(rel) if Path(rel).is_absolute() else base / rel
            ticket = target.parent if target.stem == "review" else target.parent.parent
            home = ticket / "review" / "shards"
            if home.is_dir():
                for shard in sorted(home.glob("*.md")):
                    try:
                        texts.append(shard.read_text(encoding="utf-8", errors="replace"))
                    except OSError:
                        pass
        for text in texts:
            for num in set(audit.ID.findall(text)):
                counter[num] += 1
    return counter


def collect(repo: Path, days: int | None):
    """Coder records and reviewer records from a checkout's delegations."""
    loaded = []
    cutoff = None
    if days:
        cutoff = dt.datetime.now().astimezone() - dt.timedelta(days=days)
    for pattern in record_paths.REPO_GLOBS:
        for path in sorted(repo.glob(pattern)):
            if path.name.endswith(".example.yaml"):
                continue
            record = safeyaml.mapping(path)
            if record is None:
                continue
            if cutoff is not None:
                try:
                    when = dt.datetime.fromisoformat(str(record.get("at", "")))
                except (ValueError, TypeError):
                    when = None
                if when is not None and when < cutoff:
                    continue
            loaded.append((path, record))
    pairs = record_paths.distinct(loaded)
    coder = [(p, r) for p, r in pairs if str(r.get("agent")) == kind_agents.S0_AGENT]
    reviewer = [(p, r) for p, r in pairs if str(r.get("kind")) == REVIEW_KIND]
    return coder, reviewer


def matrix(kernel: Path, coder, review_cites: Counter):
    audit = load_audit()
    defined = audit.defined_ids(kernel)
    trigger = audit.trigger_ids(kernel)
    staged = audit.staged_ids(kernel)
    import canon_smells  # noqa: E402  (plugin/, already on sys.path)

    s0 = [coder_facts(r) for _p, r in coder]
    s0 = [f for f in s0 if f]
    trigger_declared: Counter = Counter()
    table_hits: Counter = Counter()
    for fact in s0:
        if fact["canon_trigger"] and fact["canon_trigger"] not in ("无", "none", "-"):
            trigger_declared[fact["canon_trigger"]] += 1
        for num in hit_numbers(fact["table_hit"]):
            table_hits[num] += 1
        # T-numbers named in HITS lines count as runtime trigger hits too.
        for num in fact["hits"]:
            trigger_declared[num] += 1
    hit_fail: Counter = Counter()
    for _p, record in coder:
        checks = delegation.remeasure(record)
        if str(checks.get("hit-applied", "")).startswith("FAIL"):
            # The check names the TABLE_HIT entry that never reached the code;
            # charge the FAIL to that entry, not to every T# in the report.
            target = delegation.S0_TABLE_HIT.search(str((record.get("report") or {}).get("raw", "")))
            for num in (hit_numbers(target.group(1)) if target else []):
                hit_fail[num] += 1

    rows = []
    for num in sorted(defined, key=lambda s: (s[0], int(s[1:]))):
        rows.append({
            "id": num,
            "defined": True,
            "trigger": num in trigger,
            "staged": num in staged,
            "enforced": num in canon_smells.COVERED,
            "hits": table_hits.get(num, 0) + (trigger_declared.get(num, 0) if num.startswith("T") else 0),
            "cites": review_cites.get(num, 0),
            "hit_fail": hit_fail.get(num, 0),
        })
    return rows, len(s0)


def classify(row: dict) -> str:
    """Which bucket a zero-hit row lands in — deep-read-audit's layers."""
    if row["hits"] or row["cites"] or row["hit_fail"]:
        return "hit"
    if row["enforced"]:
        return "no-hit-needed"
    if row["staged"] and row["id"][0] in SWEPT_FAMILIES:
        return "no-hit-needed"
    if row["trigger"]:
        return "wording-candidate"
    return "defined-only"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout with delegation records")
    parser.add_argument("--kernel", type=Path, default=KERNEL, help="kernel root (default: this checkout)")
    parser.add_argument("--days", type=int, help="only delegation records newer than N days")
    parser.add_argument("--ids", help="only these numbers, e.g. C22,P15")
    parser.add_argument("--signal", action="store_true", help="print signal=yes|no (hit-applied FAIL >= 2 only)")
    args = parser.parse_args()

    kernel = args.kernel.resolve()
    repo = args.repo.resolve() if args.repo else None
    coder: list = []
    review_cites: Counter = Counter()
    if repo:
        if not repo.is_dir():
            print(f"BLOCKED no such checkout: {repo}", file=sys.stderr)
            return 2
        coder, reviewer = collect(repo, args.days)
        review_cites = reviewer_citations(reviewer, repo)

    rows, s0_total = matrix(kernel, coder, review_cites)
    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",") if s.strip()}
        rows = [r for r in rows if r["id"] in wanted]

    fail_ge2 = sorted(r["id"] for r in rows if r["hit_fail"] >= 2)
    if args.signal:
        print(f"signal={'yes' if fail_ge2 else 'no'}")
        for num in fail_ge2:
            print(f"HIT {num}: hit-applied FAIL >= 2 次(措辞外的真信号:声明命中没落到代码)")
        return 0

    coder_total = len(coder)
    print(f"# knowledge-metrics  {repo or kernel}")
    print(f"# 真源 {len(rows)} 条;coder 留痕 {coder_total} 份,其中含 §0 交代 {s0_total} 份")
    if repo and s0_total < MIN_SAMPLE:
        print(f"# (§0 交代样本 {s0_total} < {MIN_SAMPLE},零命中的单条不下结论,只列事实)")
    print()
    print("编号  定义 触发 点名 机检 | §0命中 | 引用 | hitFAIL")
    for r in rows:
        print(
            tw.ljust(r["id"], 6)
            + tw.ljust("有" if r["defined"] else "-", 4)
            + tw.ljust("有" if r["trigger"] else "-", 4)
            + tw.ljust("有" if r["staged"] else "-", 4)
            + tw.ljust("有" if r["enforced"] else "-", 4)
            + "| " + tw.rjust(str(r["hits"]), 5) + " "
            + "| " + tw.rjust(str(r["cites"]), 4) + " "
            + "| " + tw.rjust(str(r["hit_fail"]), 6)
        )
    print()

    buckets: dict[str, list[str]] = {}
    for r in rows:
        buckets.setdefault(classify(r), []).append(r["id"])
    print("## 分层归因(对齐 deep-read-audit 的口径)")
    print()
    print(f"- 无需命中(机检或 §0 全表扫一族): {len(buckets.get('no-hit-needed', []))} 条")
    for label, key in (("运行时已命中", "hit"),
                       ("触发层在、运行时零命中(措辞候选,只列不改)", "wording-candidate"),
                       ("只有记账且零命中(该命中没命中候选)", "defined-only")):
        ids = buckets.get(key, [])
        if ids:
            joined = " ".join(ids)
            if len(joined) > 200:
                joined = " ".join(ids[:40]) + f" …共 {len(ids)} 条"
            print(f"- {label}: {joined}")
    print()
    if fail_ge2:
        print(f"- hit-applied FAIL ≥2:{' '.join(fail_ge2)} —— 声明命中没落到代码,走 nudge 候选")
    print()
    print("口径:§0命中=TABLE_HIT 编号 + T# 触发交代;引用=review.md(含 shards)里的编号;"
          "静态四层来自 deep-read-audit。零命中不是分数,样本不足时先修交代率。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
