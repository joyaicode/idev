#!/usr/bin/env python3
"""signoff-audit: a `by` under a record of work is not a signature.

The judgement these lock is the one the tool got wrong: it held every `by`
to `is_human`, so 25 of its 27 `newly-failing` rows were files written
exactly the way trace.md and workflow-schema.md ask for. The fix is not
"skip those fields" — a field that names the worker still has to name
somebody, which is the only reason the two real `by: human` rows survive.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "signoff_audit", Path(__file__).resolve().with_name("signoff-audit.py")
)
sa = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(sa)


def findings(body: str) -> list:
    """Scan one yaml document as if it sat in a checkout."""
    repo = Path(tempfile.mkdtemp())
    doc = repo / "docs" / "task"
    doc.mkdir(parents=True)
    (doc / "run.yaml").write_text(body, encoding="utf-8")
    return sa.scan(repo)


def reported(body: str) -> list:
    return [f for f in findings(body) if f["reportable"]]


class FieldClass(unittest.TestCase):
    def test_parent_drops_the_list_index(self) -> None:
        self.assertEqual(sa.parent_of("steps[0].verification"), "verification")
        self.assertEqual(sa.parent_of("recorded[3]"), "recorded")
        self.assertEqual(sa.parent_of(""), "")

    def test_by_is_a_signature_unless_it_hangs_off_a_record_of_work(self) -> None:
        self.assertEqual(sa.field_class("steps[0].signoff", "by"), "signoff")
        self.assertEqual(sa.field_class("", "by"), "signoff")
        self.assertEqual(sa.field_class("steps[0].verification", "by"), "actor")
        self.assertEqual(sa.field_class("recorded[3]", "by"), "actor")

    def test_the_key_settles_it_when_the_key_says_signed(self) -> None:
        # `confirmed_by` under `lessons[]` is still a confirmation.
        self.assertEqual(sa.field_class("lessons[2]", "confirmed_by"), "signoff")

    def test_only_a_quote_under_a_signoff_is_a_confirmation(self) -> None:
        self.assertEqual(sa.field_class("steps[1].signoff", "quote"), "signoff")
        self.assertEqual(sa.field_class("decisions[0]", "quote"), "actor")


class ActorFields(unittest.TestCase):
    def test_the_verifier_agent_is_what_the_schema_asks_for(self) -> None:
        # workflow-schema.md: `record PASS --verified-by <that agent>`.
        out = reported("steps:\n  - verification:\n      by: idev-reviewer\n")
        self.assertEqual(out, [])

    def test_conductor_is_the_documented_third_fallback(self) -> None:
        # trace.md: `by`（签字人，否则执行者，否则 `conductor`）
        out = reported("recorded:\n  - by: conductor\n  - by: idev-verifier\n")
        self.assertEqual(out, [])

    def test_a_placeholder_is_still_reported_in_an_actor_field(self) -> None:
        """The whole point: `revisions[].by` allows an agent, not a non-name."""
        out = reported("revisions:\n  - by: idev-verifier\n  - by: human\n")
        self.assertEqual([f["value"] for f in out], ["human"])
        self.assertEqual(out[0]["verdict"], "newly-failing")

    def test_an_allowed_agent_says_so_rather_than_claiming_it_names_nobody(self) -> None:
        folded = [f for f in findings("recorded:\n  - by: idev-coder\n")]
        self.assertEqual(len(folded), 1)
        self.assertFalse(folded[0]["reportable"])
        self.assertIn("allowed", folded[0]["why"])


class SignoffFields(unittest.TestCase):
    def test_an_agent_cannot_sign(self) -> None:
        out = reported("steps:\n  - signoff:\n      by: idev-coder\n")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["why"], "not a person")

    def test_an_empty_signature_never_stopped_being_valid(self) -> None:
        out = reported("steps:\n  - signoff:\n      by: ''\n")
        self.assertEqual(out, [])

    def test_a_confirmation_carrying_work_is_reported(self) -> None:
        out = reported("steps:\n  - signoff:\n      quote: 修复所有问题\n")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["field"], "quote")

    def test_an_answer_to_a_question_is_not_a_lapsed_signature(self) -> None:
        # workflow-schema.md: 决策不是签字。
        out = reported("decisions:\n  - quote: 成立，receipt-file 不符合设计要求\n")
        self.assertEqual(out, [])


class Output(unittest.TestCase):
    def _repo(self) -> Path:
        repo = Path(tempfile.mkdtemp())
        doc = repo / "docs" / "task"
        doc.mkdir(parents=True)
        (doc / "run.yaml").write_text(
            "recorded:\n  - by: idev-verifier\nrevisions:\n  - by: human\n",
            encoding="utf-8",
        )
        return repo

    def test_default_run_names_only_what_needs_a_person(self) -> None:
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = sa.main(["--repo", str(self._repo())])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("newly-failing         1", out)
        self.assertIn("human", out)
        self.assertNotIn("idev-verifier", out)
        self.assertIn("--all for those", out)

    def test_all_brings_the_raw_sweep_back(self) -> None:
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            sa.main(["--repo", str(self._repo()), "--all"])
        self.assertIn("idev-verifier", buf.getvalue())

    def test_a_lapsed_signature_and_a_role_word_are_different_findings(self) -> None:
        """`revisions[].by: human` is a changelog written before names were
        used there. Telling someone to re-sign it is wrong advice."""
        import contextlib
        import io

        repo = Path(tempfile.mkdtemp())
        doc = repo / "docs" / "task"
        doc.mkdir(parents=True)
        (doc / "run.yaml").write_text(
            "steps:\n  - signoff:\n      by: idev-coder\nrevisions:\n  - by: human\n",
            encoding="utf-8",
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            sa.main(["--repo", str(repo)])
        out = buf.getvalue()
        resign = out.index("need a person to re-sign")
        role = out.index("name nobody where a name belongs")
        # Each finding sits under its own heading, so the advice fits it.
        self.assertLess(out.index("idev-coder", resign), role)
        self.assertGreater(out.index("'human'"), role)


if __name__ == "__main__":
    unittest.main()
