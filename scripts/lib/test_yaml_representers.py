#!/usr/bin/env python3
"""report.raw keeps its newlines through the delegation write path.

The delegation machine checks (FACTS / DOC_DRIFT / SCOPE / RED_FIRST / ASSUMED
…) are all line-anchored, and `_paths()` does whole-word matching on the same
text. yaml.safe_dump renders a multi-line str as a folded single-quoted scalar,
so a grep over the file sees one long line instead of the lines the agent
wrote. LiteralString opts report.raw into block style (`|`) so the newlines
survive both the round trip and a plain grep.

    python3 scripts/lib/test_yaml_representers.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import safeyaml  # noqa: E402
import yaml_representers  # noqa: E402


RAW = (
    "STATUS: PASS\n"
    "FACTS: codegraph src/app.py:main\n"
    "DOC_DRIFT: 无\n"
    "ASSUMED: 无\n"
    "SCOPE: src/app.py:main\n"
    "RED_FIRST: 无\n"
)


class LiteralRoundTrip(unittest.TestCase):
    def test_literal_string_dumps_as_block(self) -> None:
        record = {"report": {"raw": yaml_representers.LiteralString(RAW)}}
        text = yaml_representers.dump(record)
        self.assertIn("raw: |", text)
        # Every field stays on its own line, so `grep '^FACTS:'` finds it.
        self.assertIn("\n    FACTS: codegraph src/app.py:main\n", text)

    def test_round_trip_preserves_newlines(self) -> None:
        record = {"report": {"raw": yaml_representers.LiteralString(RAW)}}
        text = yaml_representers.dump(record)
        back = safeyaml.mapping_from_text(text)
        self.assertEqual(back["report"]["raw"], RAW)

    def test_plain_dump_folds_but_round_trips(self) -> None:
        # Document the contrast: safe_dump round-trips the value, but the file
        # is one folded scalar, so a line-anchored grep goes blind. LiteralString
        # exists for the file shape, not to fix a lost value.
        text = yaml_representers.dump({"report": {"raw": RAW}})
        self.assertNotIn("raw: |", text)
        self.assertEqual(safeyaml.mapping_from_text(text)["report"]["raw"], RAW)


if __name__ == "__main__":
    unittest.main()
