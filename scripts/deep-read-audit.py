#!/usr/bin/env python3
"""Does a book's deep read reach code, or did it only reach a table?

    deep-read-audit.py --report scripts/docs/notes/重构-精读缺口.md
    deep-read-audit.py --ids C22,C24,P18,T5
    deep-read-audit.py --all-books

Run this after landing a book's gaps, as step 6 of
`scripts/docs/notes/README.md`「读一本书的流程」. It answers one question per
entry: if someone writes code that violates it tomorrow, what stops them?

Four reachability layers, weakest to strongest:

  defined   the number exists in canon.md or coding-tables.md. This is
            bookkeeping. It stops nothing on its own.
  trigger   canon.md §2 signal or §4 thought. Only T# gets this guarantee,
            and `trigger-check.py` enforces it. C# deliberately does not —
            smells are swept, not triggered.
  staged    an agent or stage page names the number or a full family
            range (for example P1–P19), so the executor reading that page
            meets it.
  enforced  a plugin detects the shape. This is the only layer that works
            when nobody remembered to look.

Why the distinction earns its keep: a 2026-11-05 audit found every one of the
六批精读 entries `defined`, and the delegation check still passed a report
declaring `TABLE_HIT: none` against code violating four of them. Landing an
entry and enforcing it are different events, and only the second changes what
ships. Exit 1 when nothing but `defined` is true for every entry asked about.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "plugin"))
from product_sink import kernel_root  # noqa: E402
import canon_smells  # noqa: E402

ID = re.compile(r"\b([TCPRAF]\d{1,2})\b")
RANGE = re.compile(r"\b([TCPRAF])(\d{1,2})\s*[–-]\s*(?:\1)?(\d{1,2})\b")
STAGE_GLOBS = ("agents/*.md", "deliver/**/*.md", "verify/**/*.md", "ops/**/*.md")


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def section(text: str, start: str, end: str = r"\n## ") -> str:
    found = re.search(start, text)
    if not found:
        return ""
    rest = text[found.end():]
    stop = re.search(end, rest)
    return rest[:stop.start()] if stop else rest


def defined_ids(kernel: Path) -> set[str]:
    canon = read(kernel / "conventions" / "canon.md")
    tables = read(kernel / "conventions" / "coding-tables.md")
    out = set(re.findall(r"^### (T\d+)", canon, re.M))
    for fam, start, end in (("A", r"## 5\. 架构出门", r"## 6\."), ("F", r"## 6\. 失败模式", r"## 7\.")):
        out |= {m for m in re.findall(r"\b(%s\d+)\b" % fam, section(canon, start, end))}
    out |= set(re.findall(r"^\|\s*([CPR]\d+)\s*\|", tables, re.M))
    return out


def trigger_ids(kernel: Path) -> set[str]:
    canon = read(kernel / "conventions" / "canon.md")
    reach = section(canon, r"## 2\. 可观察信号") + section(canon, r"## 4\. 念头触发表")
    return set(ID.findall(reach))


def staged_ids(kernel: Path) -> set[str]:
    """Numbers a stage page reaches, including full-family ranges.

    A page that says `A1–A8`, `P1–P19`, `C1–C40`, or `R1–R7` is not naming
    two bookends; it is making every entry in that family part of the sweep.
    Treating only the two literal endpoints as staged made the audit understate
    reachability for exactly the entries the books had just landed.
    """
    out: set[str] = set()
    for pattern in STAGE_GLOBS:
        for path in kernel.glob(pattern):
            text = read(path)
            out |= set(ID.findall(text))
            for m in RANGE.finditer(text):
                family, start, end = m.group(1), int(m.group(2)), int(m.group(3))
                if start <= end:
                    out.update(f"{family}{n}" for n in range(start, end + 1))
    return out


def ids_from_report(path: Path) -> list[str]:
    found = ID.findall(read(path))
    return sorted(set(found), key=lambda s: (s[0], int(s[1:])))


def audit(ids: list[str], kernel: Path) -> tuple[list[tuple], int]:
    defined, trigger, staged = defined_ids(kernel), trigger_ids(kernel), staged_ids(kernel)
    rows = []
    reached = 0
    for num in ids:
        d = num in defined
        t = num in trigger
        s = num in staged
        e = num in canon_smells.COVERED
        if t or s or e:
            reached += 1
        rows.append((num, d, t, s, e))
    return rows, reached


def book_reports(kernel: Path) -> list[Path]:
    """The reports that can be audited: one gap report per finished book.

    DDD's per-chapter notes use local F1-F13 numbering, and The Practice of
    Programming landed without a separate report. Neither is a gap report, so
    --all-books does not guess their meaning from similarly-shaped numbers.
    """
    return sorted((kernel / "scripts" / "docs" / "notes").glob("*-精读缺口.md"))


# A "真缺口" entry is landed when its body carries one of these markers —
# the reports themselves record the landing commit ("已于 12ab1c4 落地",
# "落地状态（已提交）", "已落地"). This is a text shape, not a semantic
# judgement: whether the landing was *good* stays with the proposal review.
# DDD-style reports additionally mark the whole section landed ("均已落地")
# while each item cites its landed proposal — so a per-item citation of a
# landed proposal ("landed") counts too, and so does the section-level note.
LANDED_MARK = re.compile(r"已(?:于\s*[0-9a-f]+\s*)?落地|落地状态|已承载于|已由.*同轮落地")
SECTION_LANDED = re.compile(r"均已落地|均已按最小 diff 落到")
# Gap items come in three shapes across the reports: "### 1. 标题" (the
# EffectiveJava style), "### 缺口 A｜标题" / "### 缺口1｜标题" (代码大全 /
# 微服务设计 style), and AOSA's plain numbered list "1. **标题**".
GAP_ITEM = re.compile(r"^(?:###\s+(?:缺口\s*)?(\d+|[A-Z])[｜.]?\s*(.+)|(\d+)\.\s+\*\*(.+)\*\*)$", re.M)


def pending_gaps(kernel: Path) -> tuple[list[dict], list[str]]:
    """Entries in each report's 「## 三、真缺口」 section, by landing state.

    Complements audit(): that answers "did the landed numbers reach code",
    this answers "did the report's own gaps get landed at all". Returns
    (entries, unparsed) — entries carry report path, item number, title,
    and landed/unlanded; unparsed names reports whose 真缺口 section could
    not be read, because silence would read as "no gaps" (the DECLINED
    trade again: a missed parse must be visible, not tidy).
    """
    entries: list[dict] = []
    unparsed: list[str] = []
    defined = defined_ids(kernel)
    for report in book_reports(kernel):
        text = read(report)
        body = section(text, r"##\s*三、真缺口")
        if not body:
            continue  # a report with no 真缺口 section has nothing pending
        items = [(a or c, (b or d).strip()) for a, b, c, d in GAP_ITEM.findall(body)]
        if not items:
            # The reports that found no gaps say so in prose ("无。本书…已由
            # T1/T3… 承载" / "**零缺口。** …"). That is a stated zero, not a
            # parse failure — but only when the body actually carries the
            # zero; anything else is a shape this parser does not know and
            # must say so.
            if re.search(r"(?:^|\*\*)\s*(?:无|零缺口|没有真缺口)[。，.]", body):
                continue
            unparsed.append(str(report.relative_to(kernel)))
            continue
        # Each item runs to the next item heading or the end of the section.
        heads = [m for m in GAP_ITEM.finditer(body)]
        spans = []
        for i, m in enumerate(heads):
            start = m.start()
            end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
            spans.append((start, end))
        for (num, title), (start, end) in zip(items, spans):
            item_body = body[start:end]
            # Landed = any of three text shapes: the item records its landing
            # commit ("已于 12ab1c4 落地"), the report marks the whole batch
            # landed ("均已落地" / a "landed" proposal citation), or the
            # number the item proposes to ADD now exists in the source tables.
            # The add shape is 建议落点/落点 … 新增 C33 — existing numbers the
            # item merely cites (T3 / T4 / C23 as kin) must not count, or
            # every item that names its neighbours reads as landed. A
            # negation ("不新增 C 编号，改为映射到既有 T4 / T6") is an explicit
            # not-adding, the opposite of a landing — skip those lines whole.
            proposed = {
                n for n in ID.findall(
                    "".join(m.group(0) for m in re.finditer(
                        r"(?:建议落点|落点)[^\n]*?(?<!不)新增([^\n]*)", item_body))
                ) if n in defined
            }
            entries.append({
                "report": str(report.relative_to(kernel)),
                "item": num,
                "title": title.strip(),
                "landed": bool(
                    LANDED_MARK.search(item_body)
                    or SECTION_LANDED.search(text)
                    or re.search(r"landed", item_body)
                    or proposed
                ),
                "evidence": (re.search(r"\*\*书中依据\*\*[:：]?\s*(.+)", item_body) or [None, ""])[1]
                if re.search(r"\*\*书中依据\*\*", item_body) else "",
            })
    return entries, unparsed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kernel", default=str(kernel_root()))
    ap.add_argument("--report", type=Path, help="a notes/*-精读缺口.md to pull numbers from")
    ap.add_argument("--ids", help="comma separated, e.g. C22,P18,T5")
    ap.add_argument("--all-books", action="store_true", help="summarize every notes/*-精读缺口.md")
    ap.add_argument("--pending-gaps", action="store_true",
                    help="inventory every report's 真缺口 entries: landed vs still to propose")
    args = ap.parse_args(argv)
    kernel = Path(args.kernel).expanduser().resolve()

    if args.pending_gaps:
        entries, unparsed = pending_gaps(kernel)
        landed = [e for e in entries if e["landed"]]
        pending = [e for e in entries if not e["landed"]]
        print("# deep-read-audit pending gaps（只清点，不裁定；落地走提案 + 拷问）")
        print()
        print("已落地 %d 条；待提案 %d 条；解析失败 %d 份" % (len(landed), len(pending), len(unparsed)))
        if unparsed:
            print()
            print("UNPARSED（真缺口节有内容但解析不出条目，人工看）:")
            for name in unparsed:
                print("  %s" % name)
        if pending:
            print()
            print("待提案（有真缺口但报告里没有落地标记）:")
            for e in pending:
                print("  %s  %s. %s" % (e["report"], e["item"], e["title"]))
        print()
        if pending:
            print("NEXT 把上面的条目逐条对照真源原文，够格的走 state/proposals/ 提案（硬规则 7）")
            return 1
        print("PASS 没有待提案的真缺口")
        return 0

    if args.all_books:
        reports = book_reports(kernel)
        if not reports:
            print("FAIL no notes/*-精读缺口.md under %s" % kernel)
            return 1
        print("# deep-read-audit all books")
        print("报告  到达  只有记账")
        failed: list[Path] = []
        bookkeeping: set[str] = set()
        undefined: set[str] = set()
        for report in reports:
            ids = ids_from_report(report)
            if not ids:
                print("%s  0/0  no number" % report.relative_to(kernel))
                failed.append(report)
                continue
            rows, reached = audit(ids, kernel)
            local_bookkeeping = {
                num for num, defined, trigger, staged, enforced in rows
                if defined and not (trigger or staged or enforced)
            }
            local_undefined = {num for num, defined, *_ in rows if not defined}
            bookkeeping |= local_bookkeeping
            undefined |= local_undefined
            if not reached:
                failed.append(report)
            print("%s  %d/%d  %s" % (
                report.relative_to(kernel),
                reached,
                len(rows),
                " ".join(sorted(local_bookkeeping)) or "—",
            ))
        print()
        if undefined:
            print("全局未落真源: %s" % " ".join(sorted(undefined)))
        if bookkeeping:
            print("全局只有记账（落了表，但没有信号、没进阶段页、没有插件）: %s" % " ".join(sorted(bookkeeping)))
        if failed:
            print("FAIL 这些报告没有一条能在无人想起时拦住违例: %s" % " ".join(str(x) for x in failed))
            return 1
        print("PASS 每份精读缺口报告至少一条编号可达；只有记账的编号按 README 第 7 步判断要不要重炼化")
        return 0

    if args.ids:
        ids = [x.strip().upper() for x in args.ids.split(",") if x.strip()]
    elif args.report:
        ids = ids_from_report(args.report)
        if not ids:
            print("no T/C/P/R/A/F number found in %s" % args.report)
            return 1
    else:
        ap.error("need --report or --ids")
        return 2

    rows, reached = audit(ids, kernel)
    print("# deep-read-audit %s" % (args.report or args.ids))
    print("%-5s %-8s %-8s %-8s %-8s" % ("编号", "defined", "trigger", "staged", "enforced"))
    for num, d, t, s, e in rows:
        print("%-5s %-8s %-8s %-8s %-8s" % (
            num, "有" if d else "—", "有" if t else "—", "有" if s else "—", "有" if e else "—"))

    bookkeeping = [num for num, d, t, s, e in rows if d and not (t or s or e)]
    undefined = [num for num, d, _t, _s, _e in rows if not d]
    print()
    print("到达代码的 %d/%d" % (reached, len(rows)))
    if undefined:
        print("未落真源: %s" % " ".join(undefined))
    if bookkeeping:
        print("只有记账（落了表，但没有信号、没进阶段页、没有插件）: %s" % " ".join(bookkeeping))
        for num in bookkeeping:
            why = canon_smells.DECLINED.get(num)
            if why:
                print("  %s 不做插件是有意的：%s —— 它归人工扫表，不算缺口" % (num, why))
    if not reached:
        print("FAIL 这一批没有一条能在无人想起时拦住违例 —— 按 README 第 7 步考虑重炼化")
        return 1
    print("PASS 至少一条可达；只有记账的那些，按 README 第 7 步判断要不要重炼化")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
