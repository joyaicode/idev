#!/usr/bin/env python3
"""termview: color and hyperlinks only for a person at a terminal.

The byte-stability law: a pipe (golden, CI, subagent capture) must get
exactly the plain text it always got — that lane is what snapshots record
and what parsers read. The interactive lane may add color and OSC 8
links, and must degrade to the same plain text when NO_COLOR is set.

    python3 scripts/lib/test_termview.py
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import termview  # noqa: E402


class TTY(io.StringIO):
    """A stream that claims to be a terminal."""

    def isatty(self) -> bool:  # noqa: N802
        return True


class Termview(unittest.TestCase):
    def test_pipe_lane_is_plain_text(self) -> None:
        # A StringIO has no isatty truthiness we control here; the default
        # stream is non-interactive, so paint returns the text unchanged.
        out = io.StringIO()
        self.assertEqual(termview.paint("FAIL  x", "FAIL", stream=out), "FAIL  x")

    def test_tty_lane_adds_color(self) -> None:
        tty = TTY()
        painted = termview.paint("FAIL  x", "FAIL", stream=tty)
        self.assertIn("\x1b[31m", painted)
        self.assertTrue(painted.endswith("x\x1b[39m"))

    def test_no_color_forces_the_plain_lane(self) -> None:
        old = os.environ.get("NO_COLOR")
        try:
            os.environ["NO_COLOR"] = "1"
            tty = TTY()
            self.assertEqual(termview.paint("FAIL  x", "FAIL", stream=tty), "FAIL  x")
            self.assertEqual(termview.link("l", "/etc/hosts", stream=tty), "/etc/hosts")
        finally:
            if old is None:
                os.environ.pop("NO_COLOR", None)
            else:
                os.environ["NO_COLOR"] = old

    def test_link_plain_lane_is_path_colon_line(self) -> None:
        out = io.StringIO()
        self.assertEqual(termview.link("label", "src/x.py", 12, stream=out), "src/x.py:12")

    def test_tty_link_is_osc8(self) -> None:
        tty = TTY()
        linked = termview.link("src/x.py", "src/x.py", stream=tty)
        self.assertIn("\x1b]8;;file://", linked)
        self.assertIn("\x1b]8;;\x1b\\", linked)

    def test_row_table_aligns_and_dashes_empty(self) -> None:
        table = termview.row_table([("route", "S8"), ("why", "")], stream=io.StringIO())
        self.assertEqual(table, "route  S8\nwhy    —")

    def test_row_table_keeps_multiline_values(self) -> None:
        table = termview.row_table([("k", "a\nb")], stream=io.StringIO())
        self.assertEqual(table, "k  a\n   b")

    def test_strip_md_table_drops_separators(self) -> None:
        rows = termview.strip_md_table(["| 项 | 值 |", "|----|----|", "| a | b |"])
        self.assertEqual(rows, [("项", "值"), ("a", "b")])


if __name__ == "__main__":
    unittest.main()
