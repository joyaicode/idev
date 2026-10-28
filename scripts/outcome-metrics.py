#!/usr/bin/env python3
"""Outcome counts for phase 2: WIP aging and rework. Counts only, never a gate.

    outcome-metrics.py --repo <checkout> [--days N] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import outcome_metrics_lib as om  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--days", type=int, default=60, help="rework window (default 60)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = om.report_for(args.repo.resolve(), days=args.days)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    rework = report["rework"]
    print(f"# outcome-metrics  {Path(report['repo']).name}  tickets={report['tickets']}  window={args.days}d")
    print("## stage histogram")
    for stage, n in report["stage_histogram"].items():
        if n:
            print(f"  {stage:8} {n}")
    print(f"## WIP (not done): {report['wip']['count']}  oldest={report['wip']['oldest_age_days']}d")
    for row in report["wip"]["rows"][:15]:
        print(f"  {row['age_days']:>4}d  {row['stage']:8}  {row['feature']}")
    print(
        f"## rework ({args.days}d): records={rework['records']} "
        f"retried={rework['retried']} rejected={rework['rejected']} "
        f"check_fail={rework['check_fail']}"
    )
    for agent, b in sorted(rework["by_agent"].items(), key=lambda kv: -kv[1]["retried"]):
        if b["retried"] or b["rejected"] or b["check_fail"]:
            print(
                f"  {agent:16} retried={b['retried']} rejected={b['rejected']} "
                f"check_fail={b['check_fail']} records={b['records']}"
            )
    print("## UNPROVEN (no event stream yet)")
    for line in report["unproven"]:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
