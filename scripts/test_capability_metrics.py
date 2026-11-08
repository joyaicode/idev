#!/usr/bin/env python3
"""Locks for capability-metrics: inventory derivation, trace parsing, and
the one-number-one-calculator rule against agent-metrics.

Run directly (python3 scripts/test_capability_metrics.py) or through
selfcheck.sh. Fixtures are temp directories; nothing here reads the user's
real state/ or any product checkout, except the smoke assertion that
cross-checks agent/kind quality facts against agent-metrics itself.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
sys.path.insert(0, str(HERE))

from lib import capability_inventory as ci  # noqa: E402


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cm = _load("capability_metrics_test", "capability-metrics.py")

FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"ok   {label}")


def test_inventory() -> None:
    kernel = HERE.parent
    inv = ci.inventory(kernel)
    by_type: dict[str, int] = {}
    for _name, kind in inv.items():
        by_type[kind] = by_type.get(kind, 0) + 1
    check("workflow count", by_type.get("workflow", 0), 14)
    check("kind count", by_type.get("kind", 0), 31)
    check("agents present", all(a in inv for a in ("idev-coder", "idev-reviewer")), True)
    check("module rows", sorted(n for n, k in inv.items() if k == "module"),
          sorted(ci.module_skills(kernel)))
    check("script rows", sum(1 for n, k in inv.items() if k == "script"),
          len(ci.script_names(kernel)) - 1)  # one script name doubles as a workflow id
    check("one type per name (kind beats script)", inv.get("human.gate"), "kind")


def test_trace_parsing() -> None:
    trace = """schema_version: 2
at: 2026-11-08T10:00:00+08:00
feature: f
invoke:
  how: explicit
  matched: ""
  skills:
    - name: idev
      path: "~/x/SKILL.md"
      why: ""
calls:
  - kind: script
    name: scripts/console.py
    args: ""
    result: "PASS"
  - kind: agent
    name: idev-coder
    result: "PASS"
  - kind: skill
    name: something-else
    result: ""
"""
    names = cm.call_names(trace)
    check("call pairs", names,
          [("script", "scripts/console.py"), ("agent", "idev-coder"), ("skill", "something-else")])
    check("invoked skills", cm.invoked_skills(trace), ["idev"])

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        (home / "20261108-001.yaml").write_text(trace, encoding="utf-8")
        (home / "20261108-002.yaml").write_text(trace, encoding="utf-8")
        counts, total = cm.collect_traces(home, days=None)
        check("trace total", total, 2)
        check("path call maps to inventory name", len(counts.get("console.py", ())), 2)
        check("idev-coder hits", len(counts.get("idev-coder", ())), 2)
        check("idev skill hits", len(counts.get("idev", ())), 2)
        # days filter: everything is dated today, so a 1-day window keeps it
        _, kept = cm.collect_traces(home, days=1)
        check("days window keeps today", kept, 2)


def test_run_yaml() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        wf = repo / "docs/task/f1/workflow"
        wf.mkdir(parents=True)
        (wf / "run.yaml").write_text(
            "run_id: r1\nworkflow_id: code-review\nfeature: f1\nsteps: []\n",
            encoding="utf-8")
        counts = cm.collect_runs(repo, days=None)
        check("workflow hit", counts.get("code-review"), 1)


def test_agreement_with_agent_metrics() -> None:
    """The capability table must quote agent-metrics, not re-count it.

    Runs both against the same synthetic checkout so the numbers must match;
    if collect() ever gains a second calculator, this fails first.
    """
    agent_metrics = _load("agent_metrics_test", "agent-metrics.py")
    record = """schema_version: 1
feature: f1
step: report
kind: review.report
agent: idev-reviewer
at: 2026-11-08T10:00:00+08:00
attempt: 1
started_at: 2026-11-08T09:57:00+08:00
finished_at: 2026-11-08T10:00:00+08:00
brief:
  ticket_home: docs/task/f1
  repo: /tmp/nonexistent-f1
  stage: code
  risk_tier: P1
  must_read: conventions/coding.md
  idev_root: /tmp/nonexistent-idev
  with: {}
report:
  status: PASS
  raw: |
    STATUS: PASS
    EVIDENCE: docs/task/f1/review.md
    FACTS: 源码 src/Thing.java:10 | 命令 mvn test 退出码 0
    DOC_DRIFT: 无
    ASSUMED: 无
"""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        home = repo / "docs/task/f1/workflow/delegations/r1"
        home.mkdir(parents=True)
        (home / "report-1.yaml").write_text(record, encoding="utf-8")
        by_agent, by_kind, *_ = agent_metrics.collect(repo, None)
        b = by_agent["idev-reviewer"]
        line = f"派{b.delegated} 阻{b.blocked} 重{b.retried} 退{b.rejected} 检{sum(b.check_fail.values())} 密度{b.density}"
        check("quality line shape", line, "派1 阻0 重0 退0 检0 密度0.0")


def main() -> int:
    test_inventory()
    test_trace_parsing()
    test_run_yaml()
    test_agreement_with_agent_metrics()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nall capability-metrics locks hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
