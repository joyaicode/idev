#!/usr/bin/env python3
"""Size the conductor's cold start and show how often rounds open the other pages.

    cold-start-size.py [--kernel DIR] [--traces DIR ...] [--budget 24000]

The cold start is what agent-brief.md says to read first: itself and
SKILL.md. The pages it loads by scenario are listed with their size and how
many traces opened them; they do not count toward the budget. SKILL.md loads
as the skill body, so traces seldom list it under opened.
Exit 1 when the cold start is over budget.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from product_sink import kernel_root  # noqa: E402
import safeyaml  # noqa: E402

COLD = ("SKILL.md", "references/agent-brief.md")
ON_DEMAND = ("references/invoke.md", "references/chat-confirm-signoff.md", "references/glossary.md",
             "references/skill-details.md", "conventions/SKILL.md")
BUDGET = 24000
LINKED_KERNEL = re.compile(r"^.*?/\.(?:cursor|claude)/skills/idev/")


def chars(kernel: Path, page: str) -> int:
    try:
        return len((kernel / page).read_text(encoding="utf-8"))
    except OSError:
        return 0


def kernel_page(entry: object, kernel: Path) -> str:
    text = str(entry).strip()
    root = f"{kernel}/"
    return text[len(root):] if text.startswith(root) else LINKED_KERNEL.sub("", text)


def opened_per_trace(folders: list[Path], kernel: Path) -> list[set[str]]:
    rounds = []
    for folder in folders:
        for path in sorted(folder.glob("*.yaml")):
            trace = safeyaml.mapping(path)
            if trace and isinstance(trace.get("opened"), list):
                rounds.append({kernel_page(entry, kernel) for entry in trace["opened"]})
    return rounds


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kernel", default=str(kernel_root()))
    ap.add_argument("--traces", action="append", default=[],
                    help="trace folder, repeatable (default: the kernel's state/traces)")
    ap.add_argument("--budget", type=int, default=BUDGET)
    args = ap.parse_args(argv)
    kernel = Path(args.kernel).expanduser().resolve()
    folders = [Path(f).expanduser() for f in args.traces] or [kernel / "state" / "traces"]
    rounds = opened_per_trace(folders, kernel)

    def line(page: str) -> str:
        hits = sum(page in pages for pages in rounds)
        rate = f"opened {hits}/{len(rounds)}" + (f" ({100 * hits // len(rounds)}%)" if rounds else "")
        return f"{chars(kernel, page):8d}  {page:36s} {rate}"

    total = sum(chars(kernel, page) for page in COLD)
    print(f"# {len(rounds)} traces with opened, in {', '.join(map(str, folders))}")
    print("cold start (agent-brief.md: itself and SKILL.md)")
    for page in COLD:
        print(line(page))
    print(f"{total:8d}  total")
    print("on demand (not counted)")
    for page in ON_DEMAND:
        print(line(page))
    if total > args.budget:
        print(f"FAIL cold start {total} > {args.budget}: move tables and detail into pages opened on demand")
        return 1
    print(f"PASS cold start {total} <= {args.budget}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
