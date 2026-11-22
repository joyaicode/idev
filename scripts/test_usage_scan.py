#!/usr/bin/env python3
"""usage-scan: what retires is what the evidence says, not what is popular.

usage-scan.py decides which cold recipes move to attic/. It runs against
product repos (--repo) and refuses the kernel itself, PROTECTED names stay,
--apply actually moves. Each of those is a lock in its own right: a scan
that "protects" by printing but still moves, or that counts a protected
name as cold, retires the wrong thing — and retirement is the one action
here that is annoying to undo.

    python3 scripts/test_usage_scan.py
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "usage-scan.py"


def load_scan():
    spec = importlib.util.spec_from_file_location("usage_scan", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UsageScan(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="idev-usage-")
        self.base = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_module_loads(self) -> None:
        # The negative lock: an import-time crash is how a scan silently
        # retires nothing while reporting nothing.
        module = load_scan()
        self.assertTrue(hasattr(module, "main") or hasattr(module, "run"))

    def test_kernel_repo_is_refused(self) -> None:
        # --apply against the kernel itself must refuse: the kernel has no
        # product-side execution evidence, so a "cold" reading is a guess.
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(SCRIPT.parents[1]), "--apply"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("kernel", (proc.stdout + proc.stderr).lower())


if __name__ == "__main__":
    unittest.main()
