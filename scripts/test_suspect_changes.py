#!/usr/bin/env python3
"""Change-window attribution: the suspect list before the first hypothesis.

evidence.md 闭环-1 says 先查变更记录, but the window was hand-filled and the
change list was left to the agent. suspect-changes.py joins the two axes
mechanically. These tests lock: the window must be sourced (an unsourced
window is how unrelated evidence gets swept in), NOT_SHIPPED files never
name suspects, and the output feeds hypothesis.py's add directly.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "suspect-changes.py"

BASE = datetime(2026, 11, 20, 9, 0, 0, tzinfo=timezone(timedelta(hours=8)))


class SuspectChanges(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve() / "one"
        self.repo.mkdir(parents=True)
        for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
            subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)
        self.t0 = BASE
        self.commit("init", [("src/main/A.java", "a\n")])

    def commit(self, subject: str, files: list[tuple[str, str]],
               at: datetime | None = None) -> None:
        when = (at or self.t0).strftime("%Y-%m-%dT%H:%M:%S %z")
        env = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
        for name, text in files:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", subject], cwd=self.repo,
                      check=True, capture_output=True, env=env)
        self.t0 = self.t0 + timedelta(hours=1)

    def run_cmd(self, *extra: str) -> tuple[int, str]:
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *extra],
            capture_output=True, text=True, timeout=60,
        )
        return done.returncode, done.stdout + done.stderr

    def window(self, source: str = "告警时间",
               lo: str = "2026-11-20T00:00:00+08:00",
               hi: str = "2026-11-21T00:00:00+08:00") -> tuple[int, str]:
        return self.run_cmd("--window", f"{lo}..{hi}", "--window-source", source)

    # --- the window must be sourced ---------------------------------------

    def test_an_unsourced_window_is_refused(self) -> None:
        rc, out = self.run_cmd(
            "--window", "2026-11-20T00:00:00+08:00..2026-11-21T00:00:00+08:00",
            "--window-source", "随手写的")
        self.assertEqual(rc, 2)
        self.assertIn("BLOCKED", out)
        self.assertIn("window-without-source", out)

    def test_a_malformed_window_is_refused(self) -> None:
        rc, out = self.run_cmd("--window", "bad", "--window-source", "告警时间")
        self.assertEqual(rc, 2)
        self.assertIn("<from>..<to>", out)

    # --- what gets named, what never does ----------------------------------

    def test_a_shipped_change_inside_the_window_is_named(self) -> None:
        self.commit("touch A", [("src/main/A.java", "a\nb\n")])
        rc, out = self.window()
        self.assertEqual(rc, 0)
        self.assertIn("src/main/A.java", out)

    def test_not_shipped_files_never_name_suspects(self) -> None:
        # The setUp init commit touched A.java (shipped); add only noise.
        self.commit("docs only", [("docs/readme.md", "z\n")])
        self.commit("tests only", [("src/test/T.java", "t\n")])
        rc, out = self.window(lo="2026-11-20T10:00:00+08:00")
        self.assertEqual(rc, 0)
        self.assertNotIn("docs/readme.md", out)
        self.assertNotIn("src/test/T.java", out)
        self.assertIn("没有会进产物的变更", out)

    def test_changes_outside_the_window_are_not_named(self) -> None:
        self.commit("inside", [("src/main/A.java", "a\nb\n")])
        self.commit("after the window", [("src/main/B.java", "b\n")],
                    at=BASE + timedelta(days=3))
        rc, out = self.window()
        self.assertEqual(rc, 0)
        self.assertIn("src/main/A.java", out)
        self.assertNotIn("B.java", out)

    def test_output_carries_a_pasteable_hypothesis_add_line(self) -> None:
        self.commit("touch A", [("src/main/A.java", "a\nb\n")])
        rc, out = self.window()
        self.assertEqual(rc, 0)
        self.assertIn("hypothesis.py add", out)
        self.assertRegex(out, r'commit [0-9a-f]{7}')
        self.assertIn("嫌疑不是证据", out)


if __name__ == "__main__":
    unittest.main()
