#!/usr/bin/env python3
"""Audit idev traces. Print markdown report; print HARD_COUNT=<n> on last line."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


def _trace_module():
    """scripts/trace.py, loaded by path: `import trace` can reach the stdlib's."""
    spec = importlib.util.spec_from_file_location("idev_trace", Path(__file__).resolve().parent / "trace.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _marked_product_traces(trace_dir: Path) -> bool:
    """True when this directory is <repo>/.idev/traces and the repo opted in."""
    parent = trace_dir.parent
    if parent.name != ".idev":
        return False
    marker = parent / "marker.yaml"
    if not marker.is_file():
        return False
    try:
        text = marker.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(re.search(r"(?m)^marker:\s*idev\s*$", text))


def _kernel_traces(trace_dir: Path) -> bool:
    """Conductor sessions accept by chat-confirm and never bind a ticket."""
    kernel = Path(__file__).resolve().parent.parent / "state" / "traces"
    try:
        return trace_dir.resolve() == kernel.resolve()
    except OSError:
        return False


def _open_joint_fails(trace_dir: Path) -> int:
    inbox = trace_dir.parent / "inbox"
    if not inbox.is_dir():
        return 0
    closed = {"consumed", "archived", "resolved"}
    count = 0
    for path in sorted(inbox.glob("*.yaml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "react-tool-fail" not in text and "react-exhausted" not in text:
            continue
        match = re.search(r"(?m)^status:\s*(\S+)", text)
        status = (match.group(1) if match else "pending").strip().strip("\"'").lower()
        if status not in closed:
            count += 1
    return count


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: audit_traces_lib.py <trace_dir> <n>", file=sys.stderr)
        return 2
    trace_dir = Path(sys.argv[1])
    n = int(sys.argv[2])
    files = sorted(trace_dir.glob("*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    trace = _trace_module()
    exec_mods = ("deliver", "verify", "ops")

    stats = {
        "n": 0,
        "missing_scenario": 0,
        "multi_opened_info": 0,
        "multi_exec_calls": 0,
        "weak_calls": 0,
        "seal_write_no_signoff": 0,
        "unbound_feature": 0,
        "extensions_not_opened": 0,
        "extensions_missing": 0,
        "grill_not_opened": 0,
        "obs_skill": 0,
        "obs_delegate": 0,
        "obs_delegations": 0,
        "obs_model": 0,
        "obs_hop": 0,
        "obs_tool_hop": 0,
    }
    weak_files: list[str] = []
    unbound_files: list[str] = []
    grill_files: list[str] = []
    flagged: list[tuple[str, list[str], str]] = []
    marked_traces = _marked_product_traces(trace_dir)
    kernel_traces = _kernel_traces(trace_dir)

    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        stats["n"] += 1
        flags: list[str] = []

        sc = re.search(r"(?m)^\s*scenario:\s*[\"']?(S[1-8])\b", text)
        scenario = sc.group(1) if sc else None
        if not scenario:
            stats["missing_scenario"] += 1
            flags.append("no-scenario")

        opened_block = ""
        m = re.search(r"(?m)^opened:\s*\n((?:[ \t].*\n)*)", text)
        if m:
            opened_block = m.group(1)
        opened_hits = {
            mod
            for mod in exec_mods
            if re.search(rf"{mod}/SKILL\.md|{mod}/references", opened_block)
        }

        calls_block = ""
        cm = re.search(r"(?m)^calls:\s*\n((?:[ \t].*\n)*)", text)
        if cm:
            calls_block = cm.group(1)
        call_hits = set()
        for mod in exec_mods:
            if re.search(rf"name:\s*[\"']?{mod}/", calls_block) or re.search(
                rf"name:\s*[\"']?{mod}\.", calls_block
            ):
                call_hits.add(mod)

        weak = True
        if cm and re.search(r"(?m)^[ \t]+-\s+", calls_block):
            weak = False
        if weak:
            stats["weak_calls"] += 1
            flags.append("weak-calls")
            weak_files.append(path.name)

        fm = re.search(r"(?m)^feature:\s*(.*?)\s*$", text)
        fval = (fm.group(1).strip().strip("\"'") if fm else "")
        if fval in ("", "-") and not kernel_traces:
            stats["unbound_feature"] += 1
            unbound_files.append(path.name)

        if len(call_hits) >= 2:
            stats["multi_exec_calls"] += 1
            flags.append("multi-exec-calls:" + ",".join(sorted(call_hits)))
        elif len(opened_hits) >= 2 and scenario in {"S1", "S2", "S3", "S6", "S8"}:
            stats["multi_opened_info"] += 1

        ext = re.search(r"(?m)^extensions:\s*\n((?:[ \t].*\n)*)", text)
        has_ext = bool(re.search(r"(?m)^extensions:\s*(\[\])?\s*$", text))
        if marked_traces and not has_ext:
            stats["extensions_missing"] += 1
            flags.append("extensions-missing")
        if ext:
            for raw in ext.group(1).splitlines():
                item = raw.strip()
                if not item.startswith("-"):
                    continue
                val = item[1:].strip().strip("\"'")
                if val and val not in opened_block:
                    stats["extensions_not_opened"] += 1
                    flags.append("extensions-not-opened")
                    break

        if trace.signoff_errors(text):
            stats["seal_write_no_signoff"] += 1
            flags.append("seal-write-without-signoff")

        # Coverage only. Missing detail is not a finding and never enters HARD_COUNT.
        if re.search(r"(?m)^[ \t]+how:\s*(explicit|alias|implicit|continuation)\s*$", text) or re.search(
            r"(?m)^[ \t]+skills:\s*$", text
        ):
            stats["obs_skill"] += 1
        delegated = len(trace.machine_items(text, "delegations"))
        stats["obs_delegations"] += delegated
        if delegated or re.search(r"(?m)^[ \t]*(?:-[ \t]+)?kind:\s*delegate\s*$", text):
            stats["obs_delegate"] += 1
        if re.search(r"(?m)^[ \t]*(?:-[ \t]+)?kind:\s*model\s*$", text) or re.search(
            r"(?m)^[ \t]+model:\s*\S", text
        ):
            stats["obs_model"] += 1
        if re.search(r"(?m)^[ \t]+from:\s*\S", text) and re.search(r"(?m)^[ \t]+to:\s*\S", text):
            stats["obs_hop"] += 1
        if re.search(r"(?m)^[ \t]+from:\s*react:", text) and re.search(r"(?m)^[ \t]+to:\s*tool:", text):
            stats["obs_tool_hop"] += 1

        # Soft: S1 must open grilling; missing is MUST_ZERO, not HARD.
        if scenario == "S1" and not re.search(
            r"grilling/SKILL\.md|skills/grilling", opened_block
        ):
            stats["grill_not_opened"] += 1
            flags.append("grill-not-opened")
            grill_files.append(path.name)

        hard = [
            f
            for f in flags
            if f.startswith("multi-exec-calls")
            or f in ("seal-write-without-signoff", "extensions-not-opened", "extensions-missing")
        ]
        if hard:
            flagged.append((path.name, hard, scenario or "?"))

    def pct(x: int) -> float:
        return 0.0 if stats["n"] == 0 else round(100 * x / stats["n"], 1)

    print(f"# idev trace audit (last {stats['n']})")
    print(f"dir: {trace_dir}")
    print()
    print("| 指标 | 数量 | 占比 | 含义 |")
    print("|------|------|------|------|")
    print(
        f"| 缺 scenario | {stats['missing_scenario']} | {pct(stats['missing_scenario'])}% | "
        "路由未记 S1–S8（滚动窗外历史可忽略） |"
    )
    print(
        f"| **同轮多模块执行 calls** | {stats['multi_exec_calls']} | "
        f"{pct(stats['multi_exec_calls'])}% | 硬报警：应收敛 |"
    )
    print(
        f"| 仅 opened 多模块（深读） | {stats['multi_opened_info']} | "
        f"{pct(stats['multi_opened_info'])}% | 允许：单执行 + 邻接只读 |"
    )
    print(
        f"| calls 弱/空 | {stats['weak_calls']} | {pct(stats['weak_calls'])}% | "
        "软信号：补真实 calls |"
    )
    print(
        f"| 写了签收标记或对话确认代写，signoff 缺失或不全 | {stats['seal_write_no_signoff']} | "
        f"{pct(stats['seal_write_no_signoff'])}% | 硬报警：须补 signoff |"
    )
    print(
        f"| **阶段页未写入 opened** | {stats['extensions_not_opened']} | "
        f"{pct(stats['extensions_not_opened'])}% | 硬报警：extensions 里的路径必须出现在 opened |"
    )
    print(
        f"| **有标记的产品 trace 缺 extensions** | {stats['extensions_missing']} | "
        f"{pct(stats['extensions_missing'])}% | 硬报警：`.idev/traces` 必须写 extensions，空列表也可以 |"
    )
    print()
    print("## 周报「必须清零项」（不计入 HARD_COUNT，不改硬报警口径）")
    print("| 项 | 数量 | 占比 | 怎么清 |")
    print("|----|------|------|--------|")
    print(
        f"| calls 弱/空 | {stats['weak_calls']} | {pct(stats['weak_calls'])}% | "
        "补真实 `calls[]`（不伪造） |"
    )
    print(
        f"| `feature: -` 未绑票 | {stats['unbound_feature']} | {pct(stats['unbound_feature'])}% | "
        "小改先绑票走 S8 lite-change（s8-preflight）；非交付类对话可说明原因 |"
    )
    print(
        f"| S1 未打开 grilling | {stats['grill_not_opened']} | {pct(stats['grill_not_opened'])}% | "
        "S1 必开 `~/.cursor/skills/grilling/SKILL.md` 并写入 opened |"
    )
    print(
        f"MUST_ZERO_TOTAL={stats['weak_calls'] + stats['unbound_feature'] + stats['grill_not_opened']}"
    )
    if weak_files:
        print("- calls 弱/空样本（最多 10）: " + ", ".join(weak_files[:10]))
    if unbound_files:
        print("- 未绑票样本（最多 10）: " + ", ".join(unbound_files[:10]))
    if grill_files:
        print("- S1 未开 grilling 样本（最多 10）: " + ", ".join(grill_files[:10]))
    print()
    print("## 观察覆盖（不计清零、不进 HARD_COUNT）")
    print("| 项 | 数量 | 占比 | 含义 |")
    print("|----|------|------|------|")
    print(
        f"| 写了技能入口 | {stats['obs_skill']} | {pct(stats['obs_skill'])}% | "
        "`invoke.how` 或 `invoke.skills` |"
    )
    print(
        f"| 写了委派决定 | {stats['obs_delegate']} | {pct(stats['obs_delegate'])}% | "
        "`decisions.kind: delegate`，或 append 从留痕生成的 `delegations` |"
    )
    print(
        f"| 委派次数（由留痕生成） | {stats['obs_delegations']} | — | "
        "`delegations` 条目合计；和留痕份数对得上，不靠手记 |"
    )
    print(
        f"| 写了模型 | {stats['obs_model']} | {pct(stats['obs_model'])}% | "
        "`kind: model` 或 `model:` |"
    )
    print(
        f"| 写了组件跳 | {stats['obs_hop']} | {pct(stats['obs_hop'])}% | "
        "`calls.from` 与 `calls.to` |"
    )
    print(
        f"| 写了工具跳 | {stats['obs_tool_hop']} | {pct(stats['obs_tool_hop'])}% | "
        "`from: react:` 且 `to: tool:` |"
    )
    print(f"未消费关节失败={_open_joint_fails(trace_dir)}（inbox，不计清零、不进 HARD_COUNT）")
    print()
    print("## 硬报警样本（最多 15）")
    if not flagged:
        print("(无)")
    else:
        for name, flags, sc in flagged[:15]:
            print(f"- {name} [{sc}]: {', '.join(flags)}")
    print()
    print("说明：见 references/deep-read.md（报警表与深读规则）。")
    hard_count = (
        stats["multi_exec_calls"]
        + stats["seal_write_no_signoff"]
        + stats["extensions_not_opened"]
        + stats["extensions_missing"]
    )
    print(f"HARD_COUNT={hard_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
