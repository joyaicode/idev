#!/usr/bin/env python3
"""Phase 2 locks: structured retain, usage-scan dry-run, A/B grader, deletion-budget.

    python3 scripts/test_phase2.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDEV = HERE.parent
sys.path.insert(0, str(HERE / "lib"))
sys.path.insert(0, str(HERE))


class StructuredRetain(unittest.TestCase):
    def test_trace_facts_land_in_timeline(self) -> None:
        import structured_retain as sr
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dirs = {
                "memory": root / "memory.md",
                "timeline": root / "timeline",
            }
            trace = root / "20261028-001.yaml"
            trace.write_text(
                "schema_version: 2\nfeature: demo\nat: \"2026-10-28T00:00:00Z\"\n"
                "route:\n  scenario: S8\ncalls:\n  - kind: model\n    name: inherit\n"
                "extensions: []\n",
                encoding="utf-8",
            )
            dest = sr.append_facts(dirs, trace)
            self.assertIsNotNone(dest)
            body = dest.read_text(encoding="utf-8")
            self.assertIn("scenario: S8", body)
            self.assertIn("feature: demo", body)


class UsageScan(unittest.TestCase):
    def test_dry_run_keeps_protected_and_blocks_kernel_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "product"
            (repo / "docs" / "task").mkdir(parents=True)
            proc = subprocess.run(
                [sys.executable, str(IDEV / "scripts" / "usage-scan.py"),
                 "--repo", str(repo), "--days", "60", "--kernel", str(IDEV)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("protected_cold=", proc.stdout)
            self.assertIn("KEEP recipe lite-change", proc.stdout)
            blocked = subprocess.run(
                [sys.executable, str(IDEV / "scripts" / "usage-scan.py"),
                 "--repo", str(IDEV), "--kernel", str(IDEV), "--apply"],
                capture_output=True, text=True,
            )
            self.assertEqual(blocked.returncode, 2, blocked.stdout + blocked.stderr)
            self.assertIn("BLOCKED", blocked.stderr)


class AbGrade(unittest.TestCase):
    def test_named_cases_pass(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(IDEV / "test" / "eval" / "ab" / "grade.py"),
             "--all", "--runs", "1"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("access-layer-unified-exception", proc.stdout)
        self.assertIn("approval-template-config", proc.stdout)
        self.assertIn("SUMMARY", proc.stdout)


class DeletionBudget(unittest.TestCase):
    def test_json_shape(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(IDEV / "scripts" / "deletion-budget.py"), "--json", "--since", "HEAD"],
            capture_output=True, text=True, cwd=str(IDEV),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertIn("added", data)
        self.assertIn("deleted", data)


class CompactKeepsStructure(unittest.TestCase):
    def test_apply_writes_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            idev = repo / ".idev"
            traces = idev / "traces"
            traces.mkdir(parents=True)
            (idev / "reviews").mkdir()
            (idev / "inbox").mkdir()
            (idev / "proposals").mkdir()
            # Two traces; hot=1 so the older one folds.
            old = traces / "old.yaml"
            old.write_text(
                "schema_version: 2\nfeature: keep-me\nat: \"2026-01-01T00:00:00Z\"\n"
                "route:\n  scenario: S1\ncalls:\n  - kind: model\n    name: x\nextensions: []\n",
                encoding="utf-8",
            )
            os.utime(old, (1_700_000_000, 1_700_000_000))
            new = traces / "new.yaml"
            new.write_text("schema_version: 2\nfeature: hot\nroute:\n  scenario: S2\n", encoding="utf-8")
            # Force fold via generations: write memory with last_compact far behind.
            (idev / "memory.md").write_text(
                "---\nmarker: idev-memory\ngeneration: 5\nlast_compact_generation: 0\n---\n\n# mem\n",
                encoding="utf-8",
            )
            # Cite old.yaml twice from reviews so cites trigger even without gen... we use gen.
            proc = subprocess.run(
                [sys.executable, str(IDEV / "scripts" / "execution-clean.py"),
                 "--repo", str(repo), "--compact", "--hot", "1", "--generations", "1", "--apply"],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            timeline = idev / "timeline" / "keep-me.yaml"
            self.assertTrue(timeline.is_file(), proc.stdout)
            self.assertIn("S1", timeline.read_text(encoding="utf-8"))
            self.assertFalse(old.is_file())
            self.assertTrue(new.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=1)
