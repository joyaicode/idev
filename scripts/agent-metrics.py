#!/usr/bin/env python3
"""Where to sharpen next, by count.

Aggregates delegation records across every ticket in a product checkout and
ranks by trouble density, so the next change is chosen from data instead of
from whoever complained last.

    agent-metrics.py --repo <checkout> [--days N] [--by agent|kind|both]
                     [--signal] [--trend] [--unused] [--suggestions]

Trouble density = (blocked + retried + rejected + check_fail) / delegated.

These are counts, not scores: nothing here gates a record or a signoff. A
slow verify.run may simply have more cases, so duration is reported as a
distribution and never as a verdict.

--signal reports whether the nudge conditions in agents-evolve.md
section 6 are met, matching how the kernel's evolve-review.sh reports
signal= — a hard signal is a reason to offer to draft a proposal, nothing
more. The proposal still goes through grill and a person's confirmation.

Reading the table: see the 「读到什么 → 下一刀」 table in agents-evolve.md.
The short version is that the cheapest fix comes first — the brief serves
every agent, the kind table is one line, an agent definition is one of
eight.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import delegation  # noqa: E402
import kind_agents  # noqa: E402
import record_paths  # noqa: E402
import safeyaml  # noqa: E402
import textwidth as tw  # noqa: E402

GLOBS = record_paths.REPO_GLOBS
KERNEL = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r"[A-Za-z0-9_.-]+")


def kernel_things() -> dict[str, str]:
    """Words a SUGGEST can use for a kernel script, agent or kind, mapped to its name.

    A hyphenated script stem ("coding-scan") is distinctive enough without
    its extension; a one-word stem ("workflow") only counts as workflow.py.
    """
    things: dict[str, str] = {}
    for path in sorted((KERNEL / "scripts").iterdir()):
        if path.suffix in (".sh", ".py"):
            things[path.name] = path.name
            if "-" in path.stem:
                things.setdefault(path.stem, path.name)
    for name in (*kind_agents.AGENTS, *kind_agents.KIND_AGENTS):
        things[name] = name
    return things


def subjects(text: str, things: dict[str, str]) -> list[str]:
    named = {things[word] for word in (t.rstrip(".") for t in TOKEN.findall(text)) if word in things}
    return sorted(named)


class Bucket:
    __slots__ = (
        "delegated", "blocked", "blocked_brief", "blocked_env", "retried",
        "rejected", "check_fail", "suggest", "features", "durations",
    )

    def __init__(self) -> None:
        self.delegated = 0
        self.blocked = 0
        self.blocked_brief = 0
        self.blocked_env = 0
        self.retried = 0
        self.rejected = 0
        self.check_fail: defaultdict[str, int] = defaultdict(int)
        self.suggest = 0
        self.features: set[str] = set()
        self.durations: list[int] = []

    @property
    def trouble(self) -> int:
        return self.blocked + self.retried + self.rejected + sum(self.check_fail.values())

    @property
    def density(self) -> float:
        return 0.0 if not self.delegated else round(self.trouble / self.delegated, 2)

    @property
    def p50(self) -> int | None:
        return int(statistics.median(self.durations)) if self.durations else None

    @property
    def worst(self) -> int | None:
        return max(self.durations) if self.durations else None


def human_secs(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m{seconds % 60:02d}s"


def status_of(record: dict) -> str:
    report = record.get("report") or {}
    if report.get("status"):
        return str(report["status"]).upper()
    hit = delegation.STATUS_LINE.search(str(report.get("raw", "")))
    return hit.group(1).upper() if hit else ""


def duration_of(record: dict) -> int | None:
    explicit = record.get("duration_s")
    if explicit not in (None, ""):
        return safeyaml.as_int(explicit, 0) or None
    started, finished = record.get("started_at"), record.get("finished_at")
    if not started or not finished:
        return None
    try:
        a = dt.datetime.fromisoformat(str(started))
        b = dt.datetime.fromisoformat(str(finished))
        return max(0, int((b - a).total_seconds()))
    except (TypeError, ValueError):
        return None


def collect(repo: Path, days: int | None):
    by_agent: defaultdict[str, Bucket] = defaultdict(Bucket)
    by_kind: defaultdict[str, Bucket] = defaultdict(Bucket)
    by_week: defaultdict[str, Bucket] = defaultdict(Bucket)
    severe: list[str] = []
    suggestions: list[dict] = []
    things = kernel_things()
    untimed = untelemetered = 0
    cutoff = None
    if days:
        cutoff = dt.datetime.now().astimezone() - dt.timedelta(days=days)

    loaded = []
    for pattern in GLOBS:
        for path in sorted(repo.glob(pattern)):
            if path.name.endswith(".example.yaml"):
                continue
            # safeyaml also rejects a valid-yaml list, which the old
            # YAMLError guard let through straight into record.get().
            record = safeyaml.mapping(path)
            if record is None:
                print(f"WARN unreadable or not a mapping, skipped: {path}", file=sys.stderr)
                continue
            loaded.append((path, record))

    pairs = record_paths.distinct(loaded)
    kinds = record_paths.attempt_kinds(pairs)
    unscoped = sum(1 for kind in kinds.values() if kind == "unscoped")
    for path, record in pairs:
        when = None
        try:
            when = dt.datetime.fromisoformat(str(record.get("at", "")))
        except (ValueError, TypeError):
            pass
        if cutoff is not None and when is not None and when < cutoff:
            continue

        agent = str(record.get("agent", "?"))
        kind = str(record.get("kind", "?"))
        feature = str(record.get("feature", "?"))
        status = status_of(record)
        outcome = str(record.get("outcome", ""))
        checks = delegation.remeasure(record)
        seconds = duration_of(record)
        if seconds is None:
            untimed += 1
        if not delegation.has_telemetry(record):
            untelemetered += 1
        said = delegation.suggestion_of(record)
        if said:
            suggestions.append({
                "where": f"{feature}/{record.get('step')} #{record.get('attempt', 1)} {agent}",
                "text": said,
                "subjects": subjects(said, things),
            })

        week = when.strftime("%G-W%V") if when is not None else "unknown"
        for bucket, key in ((by_agent, agent), (by_kind, kind), (by_week, week)):
            b = bucket[key]
            b.delegated += 1
            b.features.add(feature)
            if seconds is not None:
                b.durations.append(seconds)
            if status.startswith("BLOCKED"):
                b.blocked += 1
                if "brief" in status:
                    b.blocked_brief += 1
                elif "env" in status:
                    b.blocked_env += 1
            if kinds[path] == "retry":
                b.retried += 1
            if outcome == "rejected":
                b.rejected += 1
            if said:
                b.suggest += 1
            for name, value in checks.items():
                if value.startswith("FAIL"):
                    b.check_fail[name] += 1

        if checks.get("no-signoff-write", "").startswith("FAIL"):
            severe.append(f"{feature}/{record.get('step')} {agent}: no-signoff-write")

    return dict(by_agent), dict(by_kind), dict(by_week), severe, untimed, unscoped, untelemetered, suggestions


def advise(name: str, b: Bucket) -> str:
    """The cheapest change that addresses this row, per agents-evolve.md."""
    if b.check_fail.get("no-signoff-write"):
        return "立刻停,按硬信号走提案(agent 试图越过人签字)"
    if b.check_fail.get("brief-complete") or b.blocked_brief > b.blocked_env:
        return "改委派包格式(agents.md)—— 一处改动影响全部 agent"
    if b.blocked_env:
        return "产品仓缺东西(workflow-defaults 键 / 巡检包),改产线 .idev/"
    if b.check_fail.get("metrics-shape"):
        return "导体填的 metrics 形状错了:扁平 map,只许数字或短字符串"
    if b.check_fail.get("evidence-present"):
        return f"改 {name} 的回报格式:PASS 必须给证据路径"
    if b.retried >= 2:
        return f"改 {name} 定义的步骤表述(prompt-unclear)"
    if b.rejected:
        return "回报被导体打回:核对该 agent 的回报格式"
    if b.check_fail.get("report-parsed"):
        return f"改 {name} 的回报格式:缺可机读的 STATUS 行"
    return "无需动作"


def table(title: str, buckets: dict[str, Bucket], kind_mode: bool) -> None:
    print(f"## {title}")
    print()
    if not buckets:
        print("(没有委派留痕)")
        print()
        return
    rows = sorted(buckets.items(), key=lambda kv: (-kv[1].density, -kv[1].delegated, kv[0]))
    counts = ("派", "阻", "包", "环", "重", "退", "检")
    head = tw.ljust("", 22) + "".join(" " + tw.rjust(c, 4) for c in counts)
    head += " " + tw.rjust("密度", 6) + " " + tw.rjust("p50", 7) + " " + tw.rjust("最慢", 7)
    print(head)
    for name, b in rows:
        vals = (
            b.delegated, b.blocked, b.blocked_brief, b.blocked_env,
            b.retried, b.rejected, sum(b.check_fail.values()),
        )
        line = tw.ljust(name, 22) + "".join(" " + tw.rjust(str(v), 4) for v in vals)
        line += (
            " " + tw.rjust(f"{b.density}", 6)
            + " " + tw.rjust(human_secs(b.p50), 7)
            + " " + tw.rjust(human_secs(b.worst), 7)
        )
        print(line)
    print()
    print("列:派=委派次数 阻=BLOCKED 包=缺委派包 环=环境缺 重=重派 退=被打回 检=检查失败")
    print("    密度=问题/委派 p50=耗时中位数 最慢=单次最长")
    print()
    print("下一刀(按改动面从小到大):")
    for name, b in rows:
        if b.trouble:
            label = ("kind " if kind_mode else "") + name
            print(f"- {label}(密度 {b.density},涉及 {len(b.features)} 张票)→ {advise(name, b)}")
    print()


def trend(by_week: dict[str, Bucket]) -> None:
    print("## 趋势(按 ISO 周)")
    print()
    if not by_week:
        print("(没有委派留痕)")
        print()
        return
    print(
        tw.ljust("周", 12) + " " + tw.rjust("派", 4) + " " + tw.rjust("问题", 5)
        + " " + tw.rjust("密度", 6) + " " + tw.rjust("p50", 7)
    )
    for week in sorted(by_week):
        b = by_week[week]
        print(
            tw.ljust(week, 12) + " " + tw.rjust(str(b.delegated), 4)
            + " " + tw.rjust(str(b.trouble), 5) + " " + tw.rjust(f"{b.density}", 6)
            + " " + tw.rjust(human_secs(b.p50), 7)
        )
    print()
    print("密度在降 = 这一层在变好。单周样本少时不要过度解读。")
    print()


def unused(by_agent: dict[str, Bucket], by_kind: dict[str, Bucket]) -> None:
    """Rows in the registry that nothing ever exercised."""
    print("## 从未使用")
    print()
    cold_agents = [a for a in kind_agents.AGENTS if a not in by_agent]
    delegated_kinds = [k for k, v in kind_agents.KIND_AGENTS.items() if v != kind_agents.CONDUCTOR]
    cold_kinds = [k for k in delegated_kinds if k not in by_kind]

    if cold_agents:
        print(f"agent({len(cold_agents)}/{len(kind_agents.AGENTS)}):" + " ".join(cold_agents))
    else:
        print(f"agent:全部 {len(kind_agents.AGENTS)} 个都被用过")
    if cold_kinds:
        print(f"kind({len(cold_kinds)}/{len(delegated_kinds)}):" + " ".join(cold_kinds))
    else:
        print(f"kind:全部 {len(delegated_kinds)} 个委派 kind 都走过")
    print()
    if cold_agents or cold_kinds:
        print("从未使用意味着两件事,都值得处理:")
        print("- 它**从未被真实验证过** —— 第一次用上时才发现定义有问题,代价最高")
        print("- 或者这一行本来就是多余的 —— 登记表该精简")
        print("不要因为「没出问题」就当它是好的:没跑过的代码路径不算验证过。")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="product checkout (default: cwd)")
    parser.add_argument("--days", type=int, help="only records newer than N days")
    parser.add_argument("--by", choices=["agent", "kind", "both"], default="both")
    parser.add_argument("--signal", action="store_true", help="print signal=yes|no for the nudge rules")
    parser.add_argument("--trend", action="store_true", help="also print the per-week trend")
    parser.add_argument("--unused", action="store_true", help="only print the never-used report")
    parser.add_argument("--suggestions", action="store_true", help="only print the agents' SUGGEST lines")
    args = parser.parse_args()

    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"BLOCKED no such checkout: {repo}", file=sys.stderr)
        return 2

    by_agent, by_kind, by_week, severe, untimed, unscoped, untelemetered, suggestions = collect(repo, args.days)
    total = sum(b.delegated for b in by_agent.values())

    # Nudge rules 5, 6 and 7 from references/agents-evolve.md section 6.
    hits: list[str] = []
    for name, b in by_agent.items():
        failures = sum(b.check_fail.values())
        if failures >= 2:
            hits.append(f"{name}: check_fail {failures} 次(≥2)")
    for name, b in by_kind.items():
        if b.retried + b.rejected >= 2:
            hits.append(f"kind {name}: retried+rejected {b.retried + b.rejected} 次(≥2)")
    named: defaultdict[str, int] = defaultdict(int)
    for item in suggestions:
        for subject in item["subjects"]:
            named[subject] += 1
    hits.extend(f"suggest {subject}: {n} 条(≥2)" for subject, n in sorted(named.items()) if n >= 2)
    hits.extend(severe)

    if args.suggestions:
        print("## agent 的建议")
        print()
        if not suggestions:
            print("(没有)")
        for item in sorted(suggestions, key=lambda i: (i["subjects"] or ["~"], i["where"])):
            tag = ",".join(item["subjects"]) or "未点名内核对象"
            print(f"- [{tag}] {item['where']}: {item['text']}")
        print()
        print("同一对象被点名 ≥ 2 次才算信号;单条建议只列出,不改任何东西。")
        return 0

    if args.signal:
        print(f"signal={'yes' if hits else 'no'}")
        for hit in hits:
            print(f"HIT {hit}")
        if hits:
            print()
            print("有硬信号:按 agents-evolve.md 第六节,一句话问人要不要写提案草稿。")
            print("人说要才写。不自动 land,不打分。")
        return 0

    if args.unused:
        unused(by_agent, by_kind)
        return 0

    print(f"# agent-metrics  {repo}")
    print(f"# 留痕 {total} 条" + (f",近 {args.days} 天" if args.days else "") + f",{len(by_agent)} 个 agent,{len(by_kind)} 个 kind")
    if untimed:
        print(f"# {untimed} 条没有计时,耗时列不完整")
    if untelemetered:
        print(f"# {untelemetered} 条没有 subagentStop 遥测(duration_ms / tool_call_count),"
              "钩子没装或没对上这次委派")
    if unscoped:
        print(f"# {unscoped} 条在旧的扁平目录里且 attempt > 1,分不出是重试还是新一轮 run,不计入 retried;"
              "逐票看 delegation.py eval 列出的 prior_failure")
    print()
    if args.by in ("agent", "both"):
        table("按 agent", by_agent, kind_mode=False)
    if args.by in ("kind", "both"):
        table("按 kind", by_kind, kind_mode=True)
    if args.trend:
        trend(by_week)
    unused(by_agent, by_kind)

    if severe:
        print("## 硬信号")
        print()
        for item in severe:
            print(f"- **{item}** —— 有 agent 试图越过人签字。停下来走提案,不要只改一行 prompt。")
        print()

    print(f"signal={'yes' if hits else 'no'}" + (f"  ({len(hits)} 条)" if hits else ""))
    if not total:
        print()
        print("HINT 还没有委派留痕。导体每次委派后按 agents-evolve.md 落一份:")
        print(f"     python3 {Path(__file__).parent}/delegation.py write --feature <f>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
