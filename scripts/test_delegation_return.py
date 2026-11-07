#!/usr/bin/env python3
"""Structured delegation-return schema check (phase 1 §7).

    python3 scripts/test_delegation_return.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import delegation_return as dret  # noqa: E402

VALID = HERE.parent / "api" / "schemas" / "testdata" / "delegation-return" / "valid" / "coder-pass.json"
# These four go through jsonschema. requirements.txt lists it as a single-lock
# dependency: missing it skips this one check rather than stopping the run, and
# selfcheck.sh prints that out loud. The test file has to honour the same grade
# — otherwise running it directly errors while selfcheck calls it green, which
# is exactly the inconsistency that grading was supposed to remove. The other
# two cases never reach the validator, so they keep running.
HAVE_SCHEMA = importlib.util.find_spec("jsonschema") is not None
SCHEMA_CASES = frozenset({
    "test_valid_fixture_passes",
    "test_block_in_report_passes_check",
    "test_invalid_block_fails",
    "test_signoff_writes_must_be_empty",
})


class ExtractAndValidate(unittest.TestCase):
    def setUp(self) -> None:
        if not HAVE_SCHEMA and self._testMethodName in SCHEMA_CASES:
            self.skipTest("jsonschema 未安装；装法见 requirements.txt 头部（PEP 668 的机器要多一个 flag）")

    def test_valid_fixture_passes(self) -> None:
        data = json.loads(VALID.read_text(encoding="utf-8"))
        self.assertEqual(dret.validate(data), [])

    def test_block_in_report_passes_check(self) -> None:
        body = VALID.read_text(encoding="utf-8")
        raw = "STATUS: PASS\n\n```json idev-return\n" + body + "\n```\n"
        self.assertEqual(dret.check_report(raw), "PASS")

    def test_invalid_block_fails(self) -> None:
        raw = (
            "STATUS: PASS\n\n```json idev-return\n"
            '{"schema":"idev.delegation-return/1","status":"PASS"}\n'
            "```\n"
        )
        got = dret.check_report(raw)
        self.assertTrue(got.startswith("FAIL:"), got)

    def test_absent_is_warn_unless_required(self) -> None:
        self.assertTrue(dret.check_report("STATUS: PASS\n").startswith("WARN:"))
        self.assertTrue(
            dret.check_report("STATUS: PASS\n", require=True).startswith("FAIL:")
        )

    def test_signoff_writes_must_be_empty(self) -> None:
        data = json.loads(VALID.read_text(encoding="utf-8"))
        data["signoff_writes"] = ["deliver.yaml accepted"]
        errors = dret.validate(data)
        self.assertTrue(errors, errors)

    def test_apply_as_main_overwrites_prose_from_json(self) -> None:
        data = json.loads(VALID.read_text(encoding="utf-8"))
        raw = "STATUS: FAIL\nCHANGED: wrong.py\nEVIDENCE: old.md\nASSUMED: stale\n"
        got = dret.apply_as_main(raw, data)
        self.assertIn(f"STATUS: {data['status']}", got)
        self.assertNotIn("STATUS: FAIL", got)
        if data.get("changed"):
            for path in data["changed"]:
                self.assertIn(str(path), got)
        if data.get("assumed"):
            self.assertIn(f"ASSUMED: {data['assumed']}", got)
            self.assertNotIn("ASSUMED: stale", got)


if __name__ == "__main__":
    unittest.main(verbosity=1)
