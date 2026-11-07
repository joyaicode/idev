#!/usr/bin/env python3
"""scope.baseline stops when the sealed goal moved."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "scope-baseline.py"
GIT = {
    "GIT_AUTHOR_NAME": "idev",
    "GIT_AUTHOR_EMAIL": "idev@example.com",
    "GIT_COMMITTER_NAME": "idev",
    "GIT_COMMITTER_EMAIL": "idev@example.com",
}


class ScopeBaseline(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.env = dict(os.environ, **GIT)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True, env=self.env)
        self.baseline = self.repo / ".idev" / "task" / "demo" / "baseline.yaml"
        self.baseline.parent.mkdir(parents=True)
        self.baseline.write_text("sealed: true\ngoal: keep\nnon_goal: drop\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, env=self.env)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.repo, check=True, env=self.env)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_check(self) -> tuple[int, str]:
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), "--feature", "demo"],
            capture_output=True, text=True, env=self.env,
        )
        return done.returncode, done.stdout + done.stderr

    def test_pass_when_the_sealed_file_matches_head(self) -> None:
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("SCOPE PASS", out)

    def test_blocks_when_the_goal_changes(self) -> None:
        self.baseline.write_text("sealed: true\ngoal: moved\nnon_goal: drop\n", encoding="utf-8")
        code, out = self.run_check()
        self.assertEqual(code, 2, out)
        self.assertIn("differs from HEAD", out)

    def test_blocks_when_head_is_not_sealed(self) -> None:
        self.baseline.write_text("sealed: false\ngoal: keep\nnon_goal: drop\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, env=self.env)
        subprocess.run(["git", "commit", "-q", "-m", "open"], cwd=self.repo, check=True, env=self.env)
        code, out = self.run_check()
        self.assertEqual(code, 2, out)
        self.assertIn("not sealed", out)


if __name__ == "__main__":
    unittest.main()
