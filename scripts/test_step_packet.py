#!/usr/bin/env python3
"""A step packet is a bounded page excerpt plus the included paths."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import safeyaml  # noqa: E402
import step_packet  # noqa: E402


class StepPacket(unittest.TestCase):
    def test_excerpt_is_bounded_and_hashes_the_whole_file(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "page.md"
        path.write_text("\n".join(f"line {i} " + ("x" * 80) for i in range(200)), encoding="utf-8")
        shown = step_packet.excerpt(path)
        self.assertIsNotNone(shown)
        self.assertLessEqual(shown["end"], step_packet.LIMIT_LINES)
        self.assertLessEqual(len(shown["text"]), step_packet.LIMIT_CHARS)
        self.assertEqual(shown["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_includes_are_only_the_marked_paths(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ticket = Path(tmp.name)
        (ticket / "arch.yaml").write_text(safeyaml.dump({
            "impact_candidates": [
                {"path": "src/a.go", "include": True},
                {"path": "src/b.go", "include": False},
            ],
        }), encoding="utf-8")
        self.assertEqual(step_packet.includes(ticket), ["src/a.go"])

    def test_header_is_the_executor_file_and_its_declared_tools(self) -> None:
        shown = step_packet.header("idev-ops")
        path = Path(__file__).resolve().parents[1] / "agents" / "idev-ops.md"
        self.assertEqual(shown["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertIn("Read", shown["tools"])
        self.assertEqual(step_packet.header("no-such-agent")["sha256"], "")


if __name__ == "__main__":
    unittest.main()
