#!/usr/bin/env python3
"""Size the conductor's cold start and show how often rounds open the other pages.

    cold-start-size.py [--kernel DIR] [--traces DIR ...] [--budget 24000]
    cold-start-size.py --agents

The cold start is what agent-brief.md says to read first: itself and
SKILL.md. The pages it loads by scenario are listed with their size and how
many traces opened them; they do not count toward the budget. SKILL.md loads
as the skill body, so traces seldom list it under opened.
Exit 1 when the cold start is over budget.

The on-demand list is read out of SKILL.md's own body rather than hardcoded,
so a page the entry names but nobody ever opens cannot hide from this report.
Those pages are still not judged and still do not count toward the budget —
the point is only that the cost of naming a page becomes visible. They print
least-opened first, because that end of the list is the one worth reading.

`--agents` sizes the other cold start nobody was watching: an executor's own
page plus the kernel pages its body names, one hop out. It prints and exits 0
— the spread is being measured before a budget is named, because a budget
guessed before the measurement would only move text out of sight.
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
AGENT_REF = re.compile(r"(?:references|conventions|deliver|verify|ops|docs)/[A-Za-z0-9_-]+\.md")
BODY_REF = re.compile(r"\]\(((?:references|conventions|deliver|verify|ops|docs|agents)/[A-Za-z0-9_.-]+\.md)\)")


def chars(kernel: Path, page: str) -> int:
    try:
        return len((kernel / page).read_text(encoding="utf-8"))
    except OSError:
        return 0


def on_demand_pages(kernel: Path) -> list[str]:
    """The kernel pages SKILL.md's body actually names, minus the cold start itself."""
    try:
        text = (kernel / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return list(ON_DEMAND)
    return sorted(set(BODY_REF.findall(text)) - set(COLD)) or list(ON_DEMAND)


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


def agent_closure(kernel: Path, agent: Path) -> tuple[int, int, list[str]]:
    """The agent's own page, and the kernel pages its body names, one hop out."""
    text = agent.read_text(encoding="utf-8")
    refs = sorted(set(AGENT_REF.findall(text)))
    return len(text), sum(chars(kernel, ref) for ref in refs), refs


def show_agents(kernel: Path) -> int:
    folder = kernel / "agents"
    pages = sorted(folder.glob("*.md"))
    if not pages:
        print(f"no agent pages in {folder}")
        return 0
    print("# agent cold start: the page itself plus the kernel pages it names, one hop")
    print("# printed, not judged — no budget is named until the spread is measured")
    for page in pages:
        own, hop, refs = agent_closure(kernel, page)
        print(f"{own + hop:8d}  {page.name:22s} self {own:6d}  one hop {len(refs):2d} pages {hop:6d}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kernel", default=str(kernel_root()))
    ap.add_argument("--traces", action="append", default=[],
                    help="trace folder, repeatable (default: the kernel's state/traces)")
    ap.add_argument("--budget", type=int, default=BUDGET)
    ap.add_argument("--agents", action="store_true",
                    help="size each executor's one-hop closure instead of the conductor's")
    args = ap.parse_args(argv)
    kernel = Path(args.kernel).expanduser().resolve()
    if args.agents:
        return show_agents(kernel)
    folders = [Path(f).expanduser() for f in args.traces] or [kernel / "state" / "traces"]
    rounds = opened_per_trace(folders, kernel)

    def hits(page: str) -> int:
        return sum(page in pages for pages in rounds)

    def line(page: str) -> str:
        n = hits(page)
        rate = f"opened {n}/{len(rounds)}" + (f" ({100 * n // len(rounds)}%)" if rounds else "")
        return f"{chars(kernel, page):8d}  {page:36s} {rate}"

    total = sum(chars(kernel, page) for page in COLD)
    print(f"# {len(rounds)} traces with opened, in {', '.join(map(str, folders))}")
    print("cold start (agent-brief.md: itself and SKILL.md)")
    for page in COLD:
        print(line(page))
    print(f"{total:8d}  total")

    on_demand = on_demand_pages(kernel)
    on_demand.sort(key=lambda page: (hits(page), -chars(kernel, page)))
    never = [page for page in on_demand if hits(page) == 0]
    print(f"on demand (not counted, named by SKILL.md, least-opened first) {len(on_demand)} pages")
    for page in on_demand:
        print(line(page))
    if never and rounds:
        print(f"# {len(never)} of {len(on_demand)} named pages were opened in none of the "
              f"{len(rounds)} rounds, {sum(chars(kernel, p) for p in never)} chars: "
              "a pointer nobody follows still costs attention every round")
        print("# not a gate — see references/self-evolution.md 「删除预算」/「自建期退出条件」")

    if total > args.budget:
        print(f"FAIL cold start {total} > {args.budget}: move tables and detail into pages opened on demand")
        return 1
    print(f"PASS cold start {total} <= {args.budget}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
