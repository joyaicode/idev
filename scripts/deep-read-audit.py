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

    A page that says `A1–A8`, `P1–P19`, `C1–C31`, or `R1–R7` is not naming
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kernel", default=str(kernel_root()))
    ap.add_argument("--report", type=Path, help="a notes/*-精读缺口.md to pull numbers from")
    ap.add_argument("--ids", help="comma separated, e.g. C22,P18,T5")
    ap.add_argument("--all-books", action="store_true", help="summarize every notes/*-精读缺口.md")
    args = ap.parse_args(argv)
    kernel = Path(args.kernel).expanduser().resolve()

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
