#!/usr/bin/env python3
"""Scope locks for deletion-budget.py."""
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("deletion-budget.py")
_spec = importlib.util.spec_from_file_location("deletion_budget", SCRIPT)
assert _spec is not None and _spec.loader is not None
deletion_budget = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deletion_budget)


class DeletionBudgetScope(unittest.TestCase):
    def test_skills_are_counted_and_state_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_root = deletion_budget.ROOT
            deletion_budget.ROOT = root
            try:
                (root / "skills").mkdir()
                (root / "state").mkdir()
                (root / "skills" / "a.md").write_text("one\n", encoding="utf-8")
                (root / "state" / "a.md").write_text("one\n", encoding="utf-8")
                subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
                subprocess.run(["git", "add", "."], cwd=root, check=True)
                subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True)

                (root / "skills" / "a.md").write_text("one\ntwo\n", encoding="utf-8")
                (root / "state" / "a.md").write_text("one\nthree\n", encoding="utf-8")
                subprocess.run(["git", "add", "."], cwd=root, check=True)
                subprocess.run(["git", "commit", "-m", "growth"], cwd=root, check=True, capture_output=True)

                self.assertEqual(deletion_budget.diff_numstat("HEAD~1"), (1, 0))
            finally:
                deletion_budget.ROOT = old_root


if __name__ == "__main__":
    unittest.main(verbosity=1)
