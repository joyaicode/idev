#!/usr/bin/env python3
"""ticket_yaml.load_ticket_yaml: read what the gates read, reject what they reject.

check-feature gates on deliver / verify / ops YAML, and every gate goes
through load_ticket_yaml first. A file that is not a mapping, or text that
is not YAML at all, must raise TicketYamlError — a gate that "cannot read"
has to say so, not fall through to a pass on empty defaults.

    python3 scripts/test_ticket_yaml.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ticket_yaml  # noqa: E402


class LoadTicketYaml(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="idev-ticket-yaml-")
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, name: str, body: str) -> Path:
        path = self.dir / name
        path.write_text(body, encoding="utf-8")
        return path

    def test_mapping_loads(self) -> None:
        path = self._write("ok.yaml", "goal: one\nitems:\n  - a\n")
        doc = ticket_yaml.load_ticket_yaml(path)
        self.assertEqual(doc["goal"], "one")
        self.assertEqual(doc["items"], ["a"])

    def test_empty_file_yields_empty_mapping(self) -> None:
        # Documented behavior: an empty file loads as {} so a missing-file
        # check can distinguish "no ticket yet" from "unreadable ticket".
        # The unreadable case is the next test.
        path = self._write("empty.yaml", "")
        self.assertEqual(ticket_yaml.load_ticket_yaml(path), {})

    def test_scalar_raises(self) -> None:
        path = self._write("scalar.yaml", "just a string\n")
        with self.assertRaises(ticket_yaml.TicketYamlError):
            ticket_yaml.load_ticket_yaml(path)

    def test_list_raises(self) -> None:
        path = self._write("list.yaml", "- a\n- b\n")
        with self.assertRaises(ticket_yaml.TicketYamlError):
            ticket_yaml.load_ticket_yaml(path)

    def test_broken_yaml_raises(self) -> None:
        path = self._write("broken.yaml", "a: [unclosed\n")
        with self.assertRaises(ticket_yaml.TicketYamlError):
            ticket_yaml.load_ticket_yaml(path)

    def test_as_str_normalizes(self) -> None:
        self.assertEqual(ticket_yaml.as_str(None), "")
        self.assertEqual(ticket_yaml.as_str(True), "true")
        self.assertEqual(ticket_yaml.as_str(False), "false")
        self.assertEqual(ticket_yaml.as_str("  padded  "), "padded")
        self.assertEqual(ticket_yaml.as_str(42), "42")


if __name__ == "__main__":
    unittest.main()
