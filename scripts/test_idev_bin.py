#!/usr/bin/env python3
"""One resolver for the idev binary: IDEV_BIN decides, a stale build is caught.

    python3 scripts/test_idev_bin.py
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))

import idev_bin  # noqa: E402


def touch(path: Path, at: float, body: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(body, encoding="utf-8")
    os.utime(path, (at, at))
    return path


class Explicit(unittest.TestCase):
    def resolve(self, value: str) -> str | None:
        with mock.patch.dict(os.environ, {"IDEV_BIN": value}):
            return idev_bin.path()

    def test_off_means_no_binary_even_with_a_build_on_disk(self) -> None:
        for value in ("off", "OFF", "none", "0"):
            self.assertIsNone(self.resolve(value), value)

    def test_a_missing_path_is_not_swapped_for_another_binary(self) -> None:
        self.assertIsNone(self.resolve("/nonexistent/idev"))

    def test_an_existing_path_is_used_as_given(self) -> None:
        with tempfile.NamedTemporaryFile() as f:
            self.assertEqual(self.resolve(f.name), f.name)


class Staleness(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.now = time.time()
        touch(self.root / "go.mod", self.now - 300, "module example.com/stale\n\ngo 1.21\n")
        touch(self.root / "cmd" / "idev" / "main.go", self.now - 300, "package main\n\nfunc main() {}\n")
        self.binary = touch(self.root / "bin" / "idev", self.now - 200)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_a_build_newer_than_every_source_is_fresh(self) -> None:
        self.assertFalse(idev_bin.stale(self.binary, self.root))

    def test_an_edited_source_makes_it_stale(self) -> None:
        touch(self.root / "internal" / "x" / "x.go", self.now - 100)
        self.assertTrue(idev_bin.stale(self.binary, self.root))

    def test_an_embedded_schema_counts(self) -> None:
        touch(self.root / "api" / "schemas" / "run.json", self.now - 100)
        self.assertTrue(idev_bin.stale(self.binary, self.root))

    def test_tests_and_docs_do_not(self) -> None:
        touch(self.root / "internal" / "x" / "x_test.go", self.now - 100)
        touch(self.root / "internal" / "x" / "README.md", self.now - 100)
        self.assertFalse(idev_bin.stale(self.binary, self.root))

    def kernel(self, rebuild: bool) -> tuple[str | None, str]:
        err = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k != "IDEV_BIN"}
        with mock.patch.object(idev_bin, "KERNEL", self.root), \
                mock.patch.object(idev_bin, "_auto", []), \
                mock.patch.dict(os.environ, env, clear=True), \
                contextlib.redirect_stderr(err):
            return idev_bin.path(rebuild=rebuild), err.getvalue()

    def test_a_stale_build_is_named_when_it_is_not_rebuilt(self) -> None:
        touch(self.root / "cmd" / "idev" / "main.go", self.now - 100)
        found, said = self.kernel(rebuild=False)
        self.assertEqual(found, str(self.binary))
        self.assertIn("older than the Go sources", said)

    @unittest.skipUnless(shutil.which("go"), "Go toolchain not on PATH")
    def test_a_stale_build_is_rebuilt_in_place(self) -> None:
        touch(self.root / "cmd" / "idev" / "main.go", self.now - 100)
        found, said = self.kernel(rebuild=True)
        self.assertEqual(found, str(self.binary))
        self.assertIn("rebuilt", said)
        self.assertFalse(idev_bin.stale(self.binary, self.root))
        self.assertTrue(os.access(self.binary, os.X_OK))
        self.assertEqual(list(self.binary.parent.glob(".idev.*.tmp")), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
