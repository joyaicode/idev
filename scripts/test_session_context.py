#!/usr/bin/env python3
"""Stage-entry prior art: confirmed constraints, not a new gate.

`workflow.py` already carries authoritative lessons and kept programs into a
delegation brief. A stage entry has the same cold-context problem when the
conductor (or a single-person step) is doing the work, so `session-context.py`
must surface the same rows. These tests keep the boundary tight: candidates
stay out, missing ledgers stay quiet, and the stage line explains that prior
art is a constraint rather than an answer.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))

import prior_art  # noqa: E402


def load_session_context():
    spec = importlib.util.spec_from_file_location("idev_session_context", HERE / "session-context.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lesson(lid: str, status: str, scope: str) -> str:
    return (
        f"  - id: {lid}\n"
        f"    status: {status}\n"
        f"    scope: {scope}\n"
        f"    symptom: 回写卡住\n"
        f"    evidence: ev/{lid}.log\n"
        f"    action: 先看位点\n"
        f"    outcome: 好了\n"
        f"    not_when: 位点在推进时\n"
        f"    uses: 0\n"
    )


def program(sid: str, status: str, scope: str) -> str:
    return (
        f"  - id: {sid}\n"
        f"    status: {status}\n"
        f"    form: program\n"
        f"    trust: reviewed\n"
        f"    scope: {scope}\n"
        f"    claim: 先跑这个\n"
        f"    not_when: 没有位点时\n"
        f"    script: scripts/check.sh\n"
    )


class StagePriorArt(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.ticket = self.root / ".idev" / "task" / "demo"
        self.ticket.mkdir(parents=True)
        self.kernel = self.root / "kernel"
        self.kernel_state = self.kernel / "state"
        self.kernel_state.mkdir(parents=True)

    def write_ledgers(self, lessons: str = "", sediment: str = "") -> None:
        if lessons:
            (self.ticket / "lessons.yaml").write_text(
                "schema_version: 1\nlessons:\n" + lessons, encoding="utf-8"
            )
        if sediment:
            (self.ticket / "sediment.yaml").write_text(
                "schema_version: 1\nentries:\n" + sediment, encoding="utf-8"
            )

    def test_stage_entry_sees_authoritative_lesson_and_kept_program(self) -> None:
        self.write_ledgers(
            lessons=lesson("L1", "authoritative", "code"),
            sediment=program("S1", "kept", "code"),
        )
        lines = prior_art.lines(
            self.ticket, self.kernel_state, "demo", stage="code", repo=self.root
        )
        self.assertTrue(any(line.startswith("L1 [经验]") for line in lines))
        self.assertTrue(any(line.startswith("S1 [程序]") for line in lines))

    def test_candidate_and_retired_rows_stay_out(self) -> None:
        self.write_ledgers(
            lessons=(
                lesson("L1", "candidate", "code")
                + lesson("L2", "retired", "code")
            ),
            sediment=(
                program("S1", "candidate", "code")
                + program("S2", "retired", "code")
            ),
        )
        self.assertEqual(prior_art.lines(self.ticket, self.kernel_state, "demo", stage="code", repo=self.root), [])

    def test_out_of_scope_rows_stay_out(self) -> None:
        self.write_ledgers(
            lessons=lesson("L1", "authoritative", "结算"),
            sediment=program("S1", "kept", "结算"),
        )
        self.assertEqual(prior_art.lines(self.ticket, self.kernel_state, "demo", stage="code", repo=self.root), [])

    def test_missing_ledgers_stay_quiet(self) -> None:
        self.assertEqual(prior_art.lines(self.ticket, self.kernel_state, "demo", stage="code", repo=self.root), [])

    def test_kernel_state_ledger_is_read(self) -> None:
        self.kernel_state.joinpath("lessons.yaml").write_text(
            "schema_version: 1\nlessons:\n" + lesson("K1", "authoritative", "demo"),
            encoding="utf-8",
        )
        lines = prior_art.lines(None, self.kernel_state, "demo", stage="code", repo=self.root)
        self.assertTrue(any(line.startswith("K1 [经验]") for line in lines))

    def test_missing_ledger_dependency_stays_quiet(self) -> None:
        with mock.patch.dict(sys.modules, {"lessons": None, "sediment": None}):
            self.assertEqual(
                prior_art.lines(
                    self.ticket, self.kernel_state, "demo", stage="code", repo=self.root
                ),
                [],
            )

    def test_session_context_prints_prior_lines_and_boundary_note(self) -> None:
        self.write_ledgers(lessons=lesson("L1", "authoritative", "code"))
        module = load_session_context()
        module.kernel_root = lambda: self.kernel_state
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = module.main(
                [
                    "--repo", str(self.root),
                    "--feature", "demo",
                    "--scenario", "S2",
                    "--stage", "code",
                ]
            )
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("STAGE code", text)
        self.assertIn("PRIOR L1 [经验]", text)
        self.assertIn("PRIOR_NOTE 这是约束不是答案", text)

    def test_session_context_prints_no_prior_noise_without_matches(self) -> None:
        module = load_session_context()
        module.kernel_root = lambda: self.kernel_state
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = module.main(
                [
                    "--repo", str(self.root),
                    "--feature", "demo",
                    "--scenario", "S2",
                    "--stage", "code",
                ]
            )
        self.assertEqual(code, 0)
        self.assertNotIn("PRIOR ", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
