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
PEOPLE = CASES.with_name("people.yaml")
PRODUCTION = Path(__file__).resolve().parents[1] / "config" / "people.yaml"
TEST_IDENTITIES = {"tester", "张三", "alice"}


def load_cases() -> dict:
    if not CASES.is_file():
        raise SystemExit(f"BLOCKED cases file missing: {CASES}")
    data = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"BLOCKED {CASES} is not a mapping")
    return data


class SignoffCases(unittest.TestCase):
    """The `human` rows run against test/signoff/people.yaml alone, read
    through the same parser and union the conductor uses."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_cases()
        cls._files = w._people_files
        w._people_files = lambda: [PEOPLE]
        w._PEOPLE_CACHE.clear()

    @classmethod
    def tearDownClass(cls) -> None:
        w._people_files = cls._files
        w._PEOPLE_CACHE.clear()

    def test_mode_is_whitelist(self) -> None:
        """If the fixture goes missing, say that plainly instead of failing
        forty rows with a confusing message."""
        self.assertEqual(self.data.get("mode"), "whitelist")
        w._PEOPLE_CACHE.clear()
        self.assertEqual(
            w.people_whitelist(),
            {"wangwei794", "tester", "张三", "alice"},
            msg=f"{PEOPLE} is not the list the `human` rows assume",
        )
        self.assertEqual(w.people_warning(), "")

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
            {
                "确认不了",
                "同意吗",
                "LGTM but wait",
                "确认？",
                "idev-coder",
                "Claude",
                "claude-opus",
                "GPT-4o",
                "grok bot",
                "DeepSeek",
                "glm-4.6",
                "Qwen",
                "kimi",
                "ai助手",
                "evolve-curator",
            },
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


class SignoffByRefusal(unittest.TestCase):
    """The refusal says which half of is_human failed."""

    def setUp(self) -> None:
        w._PEOPLE_CACHE.clear()
        self.addCleanup(w._PEOPLE_CACHE.clear)
        key = (
            __import__("os").environ.get("IDEV_ROOT", ""),
            str(Path.cwd()),
        )
        w._PEOPLE_CACHE[key] = ({"wangwei794"}, "")

    def test_blank_by(self) -> None:
        self.assertEqual(
            w.signoff_by_refusal(""),
            "human.gate PASS needs --by with a person's name",
        )

    def test_an_agent_name(self) -> None:
        self.assertEqual(
            w.signoff_by_refusal("idev-coder"),
            "human.gate PASS needs --by with a person's name, not an agent",
        )

    def test_an_unlisted_name(self) -> None:
        self.assertEqual(
            w.signoff_by_refusal("tester"),
            "human.gate PASS needs --by with a name listed in people.yaml",
        )

    def test_a_listed_person(self) -> None:
        self.assertEqual(w.signoff_by_refusal("wangwei794"), "")


class ProductionWhitelist(unittest.TestCase):
    """config/people.yaml signs real gates, so it lists real people only."""

    def test_lists_people_and_no_test_identity(self) -> None:
        names = w._read_people(PRODUCTION)
        self.assertTrue(names, f"{PRODUCTION} lists nobody")
        self.assertEqual(
            names & TEST_IDENTITIES,
            set(),
            msg="test identities belong in test/signoff/people.yaml",
        )


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

    def test_a_question_passes(self) -> None:
        self.assertEqual(self._run("wangwei794", "同意吗"), [])

    def test_a_refusal_passes(self) -> None:
        self.assertEqual(self._run("wangwei794", "确认不了"), [])

    def test_continue_passes(self) -> None:
        self.assertEqual(self._run("wangwei794", "继续"), [])

    def test_an_empty_quote_passes(self) -> None:
        self.assertEqual(self._run("", ""), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
