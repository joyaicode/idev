#!/usr/bin/env python3
"""Fixtures for outcome-metrics.py (phase 2 §1).

    python3 scripts/test_outcome_metrics.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDEV = HERE.parent
SCRIPT = IDEV / "scripts" / "outcome-metrics.py"


class OutcomeMetrics(unittest.TestCase):
    def test_wip_and_rework_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ticket = root / "docs" / "task" / "demo-wip"
            ticket.mkdir(parents=True)
            (ticket / "deliver.yaml").write_text(
                "stage: code\ngoal: demo\n", encoding="utf-8"
            )
            done = root / "docs" / "task" / "demo-done"
            done.mkdir(parents=True)
            (done / "deliver.yaml").write_text(
                "stage: done\ngoal: shipped\n", encoding="utf-8"
            )
            rec_dir = ticket / "workflow" / "delegations" / "01TEST"
            rec_dir.mkdir(parents=True)
            (rec_dir / "S1-code_pass-a1.yaml").write_text(
                "agent: idev-coder\nattempt: 2\nat: 2026-10-20T12:00:00Z\n"
                "outcome: recorded\nchecks:\n  scope-held: FAIL:x\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--repo", str(root), "--json", "--days", "60"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            self.assertEqual(report["wip"]["count"], 1)
            self.assertEqual(report["wip"]["rows"][0]["feature"], "demo-wip")
            self.assertEqual(report["stage_histogram"]["done"], 1)
            self.assertEqual(report["rework"]["retried"], 1)
            self.assertGreaterEqual(report["rework"]["check_fail"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
