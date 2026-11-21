#!/usr/bin/env python3
"""product_sink._tracked_process_files: process files git already tracks.

The ignore block only stops *new* files. Ones tracked before it landed stay
in the index and keep receiving diffs, so ensure_marker reports each one and
never untacks it — that reconciliation is the person's call. Durable keeps
(memory.md, task/**, docs/**, …) are filtered by the same _GITIGNORE_KEEP
list the block is written from.

    python3 scripts/lib/test_product_sink.py
"""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import product_sink  # noqa: E402


class TrackedProcessFiles(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="idev-sink-")
        self.repo = Path(self._tmp.name) / "prod"
        self.repo.mkdir()
        subprocess.run(
            ["git", "-C", str(self.repo), "init", "-q"],
            check=True, capture_output=True,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _track_all(self) -> None:
        subprocess.run(
            ["git", "-C", str(self.repo), "add", "-A", "-f"],
            check=True, capture_output=True,
        )

    def test_process_files_are_reported(self) -> None:
        traces = self.repo / ".idev" / "traces"
        traces.mkdir(parents=True)
        (traces / "t.yaml").write_text("x\n", encoding="utf-8")
        self._track_all()
        self.assertEqual(
            product_sink._tracked_process_files(self.repo),
            ["/.idev/traces/t.yaml"],
        )

    def test_durable_keeps_are_not_reported(self) -> None:
        idev = self.repo / ".idev"
        idev.mkdir()
        for name in ("task", "pack", "docs", "checks", "workflows"):
            (idev / name).mkdir()
        (idev / "task" / "f1.md").write_text("t\n", encoding="utf-8")
        (idev / "pack" / "p.md").write_text("p\n", encoding="utf-8")
        (idev / "docs" / "d.md").write_text("d\n", encoding="utf-8")
        (idev / "checks" / "c.sh").write_text("c\n", encoding="utf-8")
        (idev / "workflows" / "w.yaml").write_text("w\n", encoding="utf-8")
        (idev / "memory.md").write_text("m\n", encoding="utf-8")
        (idev / "marker.yaml").write_text("marker: idev\n", encoding="utf-8")
        self._track_all()
        self.assertEqual(product_sink._tracked_process_files(self.repo), [])

    def test_untracked_files_are_quiet(self) -> None:
        idev = self.repo / ".idev"
        idev.mkdir()
        (idev / "marker.yaml").write_text("marker: idev\n", encoding="utf-8")
        (idev / "traces").mkdir()
        (idev / "traces" / "t.yaml").write_text("x\n", encoding="utf-8")  # untracked
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            product_sink.ensure_marker(self.repo)
        self.assertEqual(err.getvalue().strip().splitlines(), [])

    def test_ensure_marker_warns_on_tracked_process_file(self) -> None:
        traces = self.repo / ".idev" / "traces"
        traces.mkdir(parents=True)
        (traces / "t.yaml").write_text("x\n", encoding="utf-8")
        self._track_all()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            product_sink.ensure_marker(self.repo)
        lines = err.getvalue().strip().splitlines()
        self.assertTrue(
            any("traces/t.yaml" in line and "WARN" in line for line in lines),
            lines,
        )
        # The tracked file is never removed by the scaffold.
        self.assertTrue((traces / "t.yaml").is_file())
        # Re-running stays quiet about the same finding only when the file
        # is gone from the index; here it is still tracked, so it warns again.
        err2 = io.StringIO()
        with contextlib.redirect_stderr(err2):
            product_sink.ensure_marker(self.repo)
        self.assertTrue(any("WARN" in line for line in err2.getvalue().splitlines()))


if __name__ == "__main__":
    unittest.main()
