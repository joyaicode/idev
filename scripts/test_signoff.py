#!/usr/bin/env python3
"""The signoff cases in test/signoff/cases.yaml, run against workflow_spec.

The first Python unit test in this repo. unittest rather than pytest so the
macOS system interpreter (3.9.6) can run it with nothing installed.

Go reads the same cases.yaml from P1 on. If this file and the Go test ever
report different results for a row, one of the two implementations has
drifted and the signoff gate is no longer one rule.

    python3 scripts/test_signoff.py          # or: -v for every row
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import workflow_spec as w  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("BLOCKED pyyaml is required (the idev contracts are all yaml)")

CASES = Path(__file__).resolve().parents[1] / "test" / "signoff" / "cases.yaml"


def load_cases() -> dict:
    if not CASES.is_file():
        raise SystemExit(f"BLOCKED cases file missing: {CASES}")
    data = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"BLOCKED {CASES} is not a mapping")
    return data


class SignoffCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_cases()

    def test_mode_is_blacklist_only(self) -> None:
        """Every `human: ok: true` row assumes no whitelist is in force.

        If someone drops a people.yaml into the kernel or the data root, the
        expectations in cases.yaml stop describing reality — so say that
        plainly instead of failing forty rows with a confusing message.
        """
        self.assertEqual(self.data.get("mode"), "blacklist-only")
        w._PEOPLE_CACHE.clear()
        self.assertEqual(
            w.people_whitelist(),
            set(),
            msg=(
                "a people.yaml is in force, so the `human` rows no longer apply; "
                "run this with IDEV_ROOT unset and no config/people.yaml"
            ),
        )
        self.assertIn("blacklist-only", w.people_warning())

    def test_confirm(self) -> None:
        for case in self.data.get("confirm") or []:
            quote = case["quote"]
            with self.subTest(quote=quote, gate=case.get("gate_type", "")):
                got = w.parse_confirm(
                    quote,
                    case.get("gate_type", "") or "",
                    case.get("origin", "") or "",
                )
                self.assertEqual(got.ok, case["ok"], f"{quote!r} ok")
                self.assertEqual(got.reason, case["reason"], f"{quote!r} reason")
                # The thin wrapper must agree with the parser it wraps.
                if not case.get("gate_type"):
                    self.assertEqual(w.is_confirm(quote), case["ok"])

    def test_reject(self) -> None:
        for case in self.data.get("reject") or []:
            with self.subTest(quote=case["quote"]):
                self.assertEqual(w.is_reject(case["quote"]), case["ok"])

    def test_human(self) -> None:
        w._PEOPLE_CACHE.clear()
        for case in self.data.get("human") or []:
            with self.subTest(name=case["name"]):
                self.assertEqual(w.is_human(case["name"]), case["ok"])

    def test_regressions_are_covered(self) -> None:
        """The rows the review called out must still be present and failing.

        Guards against someone "fixing" a flaky row by deleting it.
        """
        rows = (self.data.get("confirm") or []) + (self.data.get("human") or [])
        flagged = {
            str(r.get("quote", r.get("name", ""))) for r in rows if r.get("regression")
        }
        self.assertEqual(
            flagged,
            {"确认不了", "同意吗", "LGTM but wait", "确认？", "idev-coder", "Claude"},
            msg="the review's regression rows changed; update the review, not the test",
        )


class WhitelistBehaviour(unittest.TestCase):
    """is_human's second gate, exercised without touching the real config."""

    def setUp(self) -> None:
        w._PEOPLE_CACHE.clear()
        self.addCleanup(w._PEOPLE_CACHE.clear)

    def _with_whitelist(self, names: set, warning: str = "") -> None:
        key = (
            __import__("os").environ.get("IDEV_ROOT", ""),
            str(Path.cwd()),
        )
        w._PEOPLE_CACHE[key] = (names, warning)

    def test_whitelist_refuses_an_unlisted_name(self) -> None:
        self._with_whitelist({"wangwei794"})
        self.assertTrue(w.is_human("wangwei794"))
        self.assertFalse(w.is_human("someone-plausible"))

    def test_whitelist_is_case_and_space_insensitive(self) -> None:
        self._with_whitelist({"wangwei794"})
        self.assertTrue(w.is_human("  WangWei794 "))

    def test_blacklist_still_wins_over_the_whitelist(self) -> None:
        """Listing an agent must not make it a person."""
        self._with_whitelist({"idev-coder", "claude", "wangwei794"})
        self.assertFalse(w.is_human("idev-coder"))
        self.assertFalse(w.is_human("claude"))
        self.assertTrue(w.is_human("wangwei794"))


class CheckRunUsesTheGate(unittest.TestCase):
    """check_run is where a forged signoff would actually land."""

    def _run(self, by: str, quote: str) -> list:
        errors: list = []
        w.check_run(
            {
                "schema_version": 1,
                "workflow_id": "lite-change",
                "feature": "f",
                "status": "running",
                "steps": [
                    {
                        "id": "gate",
                        "kind": "human.gate",
                        "status": "PASS",
                        "signoff": {"by": by, "quote": quote},
                    }
                ],
            },
            Path("run.yaml"),
            errors,
        )
        return errors

    def test_a_person_with_a_confirmation_passes(self) -> None:
        self.assertEqual(self._run("wangwei794", "确认"), [])

    def test_an_agent_cannot_sign(self) -> None:
        self.assertTrue(self._run("idev-coder", "确认"))

    def test_a_question_is_not_a_confirmation(self) -> None:
        self.assertTrue(self._run("wangwei794", "同意吗"))

    def test_a_refusal_is_not_a_confirmation(self) -> None:
        self.assertTrue(self._run("wangwei794", "确认不了"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
