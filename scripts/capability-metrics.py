#!/usr/bin/env python3
"""Which capability got exercised, and what the record says about it.

One table across every kind of capability the kernel ships: recipes, kinds,
agents, module skills, scripts. The other metrics scripts each own one
dimension — agent-metrics the delegation hop, audit-traces the trace
discipline, outcome/ticket-metrics the ticket. This script owns the
capability dimension and owns no numbers of its own: agent/kind quality
facts are imported from agent-metrics' collect(), so the same number always
has exactly one calculator.

    capability-metrics.py [--repo <checkout>] [--traces <dir>] [--days N]
                          [--by <type>] [--unused]

Counts, not scores: nothing here gates a record or a signoff, and a cold row
is a fact to read, not a verdict. Workflow hits come only from run.yaml's
workflow_id (invoke.matched is free text; fuzzy-matching it is deliberately
out of scope). Scripts are reported as a coverage ratio plus the top names,
not a row each — a 224-row cold list buries the five rows a person can act
on. The never-used report for workflows/kinds/agents/modules follows
agent-metrics.unused's reading: never exercised means never really
verified, or the row is redundant — both worth handling, neither a score.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import capability_inventory as ci  # noqa: E402
import kind_agents  # noqa: E402
import record_paths  # noqa: E402
import safeyaml  # noqa: E402
import textwidth as tw  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
KERNEL = SCRIPTS.parent


def _load_module(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def trace_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


CALL_ITEM = re.compile(r"^\s+- kind:\s*(\S+)")
CALL_NAME = re.compile(r"^\s+name:\s*(\S+)")


def call_names(text: str) -> list[tuple[str, str]]:
    """(kind, name) pairs from a trace's calls[] block, indentation-sliced.

    The block is read as text the way audit_traces_lib reads trace files:
    parse-free, tolerant of v1/v2 field drift, and only used for counting.
    """
    block = re.search(r"(?m)^calls:\s*\n((?:[ \t].*\n?)*)", text)
    if not block:
        return []
    out: list[tuple[str, str]] = []
    kind = name = None
    for line in block.group(1).splitlines():
        hit = CALL_ITEM.match(line)
        if hit:
            if kind and name:
                out.append((kind, name))
            kind, name = hit.group(1), None
            continue
        hit = CALL_NAME.match(line)
        if hit and kind is not None:
            name = hit.group(1)
    if kind and name:
        out.append((kind, name))
    return out


def capability_name(name: str) -> str:
    """The inventory token, whether a trace writes a path or a stem."""
    return name.rsplit("/", 1)[-1]


def invoked_skills(text: str) -> list[str]:
    # invoke.skills: items are "- name: <skill>" mappings (v2), so slice the
    # invoke block first; a bare "- <skill>" list (v1) still matches below.
    invoke = re.search(r"(?m)^invoke:\s*\n((?:[ \t].*\n?)*)", text)
    block = re.search(r"(?m)^\s+skills:\s*\n((?:[ \t]+-.*\n?)*)",
                      invoke.group(1)) if invoke else None
    if not block:
        return []
    out: list[str] = []
    for line in block.group(1).splitlines():
        hit = re.match(r"\s+- (?:name:\s*)?(\S+)", line)
        if hit:
            out.append(hit.group(1))
    return out


def collect_traces(traces_dir: Path, days: int | None):
    """Hits by capability name: one trace file can charge a name only once."""
    counts: dict[str, set[str]] = {}
    total = 0
    cutoff = None
    if days:
        cutoff = dt.datetime.now().astimezone() - dt.timedelta(days=days)
    if not traces_dir.is_dir():
        return counts, total
    for path in sorted(traces_dir.glob("*.yaml")):
        text = trace_text(path)
        if not text:
            continue
        if cutoff is not None:
            at = re.search(r"(?m)^at:\s*(\S+)", text)
            try:
                when = dt.datetime.fromisoformat(at.group(1)) if at else None
            except ValueError:
                when = None
            if when is not None and when < cutoff:
                continue
        total += 1
        for skill in invoked_skills(text):
            counts.setdefault(skill, set()).add(path.name)
        for _kind, name in call_names(text):
            counts.setdefault(capability_name(name), set()).add(path.name)
    return counts, total


def collect_runs(repo: Path, days: int | None):
    """Workflow hits from run.yaml — the structured source for recipes."""
    counts: dict[str, int] = {}
    cutoff = None
    if days:
        cutoff = dt.datetime.now().astimezone() - dt.timedelta(days=days)
    for pattern in ("docs/task/*/workflow/run.yaml", ".idev/task/*/workflow/run.yaml"):
        for path in sorted(repo.glob(pattern)):
            data = safeyaml.mapping(path)
            if not data:
                continue
            if cutoff is not None:
                try:
                    when = dt.datetime.fromisoformat(str(data.get("at", "")))
                except (ValueError, TypeError):
                    when = None
                if when is not None and when < cutoff:
                    continue
            for step in data.get("steps") or []:
                wid = step.get("workflow_id") if isinstance(step, dict) else None
                if wid:
                    counts[str(wid)] = counts.get(str(wid), 0) + 1
            wid = data.get("workflow_id")
            if wid:
                counts[str(wid)] = counts.get(str(wid), 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout: run.yaml workflow hits + agent-metrics facts")
    parser.add_argument("--traces", type=Path, help="trace directory (default: kernel state/traces)")
    parser.add_argument("--days", type=int, help="only traces/runs newer than N days")
    parser.add_argument("--by", choices=list(ci.CAPABILITY_TYPES) + ["all"], default="all")
    parser.add_argument("--unused", action="store_true", help="only print the never-used report")
    args = parser.parse_args()

    agent_metrics = _load_module("agent_metrics_reuse", "agent-metrics.py")
    kernel = KERNEL
    inv = ci.inventory(kernel)

    traces_dir = (args.traces or (kernel / "state" / "traces")).resolve()
    trace_counts, trace_total = collect_traces(traces_dir, args.days)

    run_counts: dict[str, int] = {}
    buckets = {}
    if args.repo:
        repo = args.repo.resolve()
        if not repo.is_dir():
            print(f"BLOCKED no such checkout: {repo}", file=sys.stderr)
            return 2
        run_counts = collect_runs(repo, args.days)
        by_agent, by_kind, *_ = agent_metrics.collect(repo, args.days)
        buckets = {**by_agent, **by_kind}

    def hits(name: str) -> int:
        return len(trace_counts.get(name, ())) + run_counts.get(name, 0)

    def quality(name: str) -> str:
        b = buckets.get(name)
        if not b:
            return "—"
        return (f"派{b.delegated} 阻{b.blocked} 重{b.retried} 退{b.rejected} "
                f"检{sum(b.check_fail.values())} 密度{b.density}")

    if args.unused:
        unused_report(inv, hits, trace_total)
        return 0

    print(f"# capability-metrics  {traces_dir}" + (f"  + {args.repo}" if args.repo else ""))
    print(f"# 能力 {len(inv)} 个(按类型),窗口内 trace {trace_total} 条"
          + (f",近 {args.days} 天" if args.days else ""))
    print()
    print("## 按 capability")
    print()
    print(tw.ljust("能力", 26) + tw.ljust("类型", 10) + tw.rjust("命中", 5) + "  质量事实(引自 agent-metrics)")
    rows = sorted(inv.items(), key=lambda kv: (-hits(kv[0]), kv[0]))
    for name, kind in rows:
        if args.by != "all" and kind != args.by:
            continue
        print(tw.ljust(name, 26) + tw.ljust(kind, 10) + tw.rjust(str(hits(name)), 5)
              + "  " + quality(name))
    # External rows: only names a person could look up again. A trace's
    # skills[] carries exactly one real entry (the "idev" entry, already in
    # the inventory); the rest of invoke is free text that matches nothing.
    for name in sorted(trace_counts):
        if name not in inv and not name.startswith(("~", "/", '"')) and "." not in name:
            print(tw.ljust(name, 26) + tw.ljust("skill", 10) + tw.rjust(str(hits(name)), 5) + "  —")
    print()
    print("命中=出现该能力的 trace 文件数 + run.yaml 计数;质量列只有委派类能力有(agent-metrics 记账)。")
    print()
    unused_report(inv, hits, trace_total)
    return 0


def unused_report(inv: dict, hits, trace_total: int) -> None:
    print("## 从未使用")
    print()
    any_cold = False
    by_type: dict[str, list[str]] = {}
    for name, kind in inv.items():
        by_type.setdefault(kind, []).append(name)
    for kind in ci.CAPABILITY_TYPES:
        names = by_type.get(kind, [])
        if kind == "script":
            used = sum(1 for n in names if hits(n))
            print(f"script 覆盖率:{used}/{len(names)}(只报覆盖,不逐列——冷脚本列表太长会淹没可行动的行)")
            top = sorted((n for n in names if hits(n)), key=lambda n: -hits(n))[:5]
            if top:
                print(f"  最常命中:{' '.join(top)}")
            any_cold = any_cold or used < len(names)
            continue
        cold = [n for n in names if not hits(n)]
        if cold:
            any_cold = True
            print(f"{kind}({len(cold)}/{len(names)}):{' '.join(cold)}")
        else:
            print(f"{kind}:全部 {len(names)} 个都被用过")
    print()
    if any_cold:
        print("从未使用 = 从未被真实验证过,或这一行本来就多余。两种都值得处理,都不是分数。")
        if trace_total < 20:
            print(f"(窗口内只有 {trace_total} 条 trace,样本不足,不下结论)")
    print()


if __name__ == "__main__":
    raise SystemExit(main())
