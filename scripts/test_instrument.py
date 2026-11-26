#!/usr/bin/env python3
"""The instrument ledger: bounded runtime forensics, enforced both ways.

Cursor's debug mode adds temporary logs and removes them after the fix. The
bounded channel only works if both directions are checked: a log line added
without registering, and a registered instrument that quietly vanished.
These tests lock the semantics the cleanup gate depends on — `check` exit 1
on any active instrument, exit 0 only when the ledger is clean or absent.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))

SCRIPT = HERE / "instrument.py"
HYP = HERE / "hypothesis.py"


class InstrumentLedger(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve() / "one"
        self.repo.mkdir(parents=True)
        for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
            subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)
        (self.repo / "src").mkdir()
        (self.repo / "src" / "A.java").write_text("a\nb\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.repo,
                        check=True, capture_output=True)

    def run_cmd(self, script: Path, *extra: str) -> tuple[int, str]:
        done = subprocess.run(
            [sys.executable, str(script), "--repo", str(self.repo), *extra],
            capture_output=True, text=True, timeout=60,
        )
        return done.returncode, done.stdout + done.stderr

    def hypothesis(self, claim: str) -> str:
        _rc, out = self.run_cmd(HYP, "add", "--feature", "demo", "--claim", claim)
        self.assertIn("OK", out)
        return out

    def add(self, *extra: str) -> tuple[int, str]:
        return self.run_cmd(SCRIPT, "add", "--feature", "demo", *extra)

    # --- add needs a real hypothesis ------------------------------------

    def ensure_hypothesis(self) -> None:
        """Most tests need a live hypothesis; the ones that test the
        refusal do not call this."""
        self.hypothesis("A.java 的 y 分支处理错")
        self.assertEqual(self.hyp_id(), "H1", "setUp should create H1")

    def hyp_id(self) -> str:
        import safeyaml

        path = self.repo / ".idev" / "task" / "demo" / "hypotheses.yaml"
        data = safeyaml.mapping(path)
        items = list(data.get("items") or [])
        return str(items[-1].get("id")) if items else ""

    def test_add_without_hypothesis_ledger_is_refused(self) -> None:
        rc, out = self.add("--hypothesis", "H1", "--file", "src/A.java:1", "--stub", "log")
        self.assertEqual(rc, 2)
        self.assertIn("BLOCKED", out)

    def test_add_with_unknown_hypothesis_is_refused(self) -> None:
        self.ensure_hypothesis()
        rc, out = self.add("--hypothesis", "H9", "--file", "src/A.java:1", "--stub", "log")
        self.assertEqual(rc, 2)
        self.assertIn("no such hypothesis", out)

    def test_add_with_real_hypothesis_registers_I1(self) -> None:
        self.ensure_hypothesis()
        rc, out = self.add("--hypothesis", "H1", "--file", "src/A.java:1", "--stub", "log")
        self.assertEqual(rc, 0)
        self.assertIn("I1", out)
        self.assertIn("IDEV-DBG I1", out)

    def test_add_rejects_a_location_without_a_line(self) -> None:
        self.ensure_hypothesis()
        rc, out = self.add("--hypothesis", "H1", "--file", "src/A.java", "--stub", "log")
        self.assertEqual(rc, 2)
        self.assertIn("path:line", out)

    # --- check: residue is the gate's signal ----------------------------

    def test_check_with_active_instrument_fails_with_residue(self) -> None:
        self.ensure_hypothesis()
        self.add("--hypothesis", "H1", "--file", "src/A.java:1", "--stub", "log")
        rc, out = self.run_cmd(SCRIPT, "check", "--feature", "demo")
        self.assertEqual(rc, 1)
        self.assertIn("instrument-residue", out)

    def test_check_passes_when_everything_is_removed(self) -> None:
        self.ensure_hypothesis()
        self.add("--hypothesis", "H1", "--file", "src/A.java:1", "--stub", "log")
        self.run_cmd(SCRIPT, "set", "--feature", "demo", "--id", "I1", "--status", "removed")
        rc, out = self.run_cmd(SCRIPT, "check", "--feature", "demo")
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    def test_check_without_a_ledger_passes(self) -> None:
        rc, out = self.run_cmd(SCRIPT, "check", "--feature", "never-instrumented")
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    # --- sweep: both directions ------------------------------------------

    def test_sweep_catches_an_unregistered_tag(self) -> None:
        (self.repo / "src" / "A.java").write_text(
            "a\nb\n// IDEV-DBG I2 rogue\n", encoding="utf-8")
        rc, out = self.run_cmd(SCRIPT, "sweep", "--feature", "demo")
        self.assertEqual(rc, 1)
        self.assertIn("unregistered-instrument", out)

    def test_sweep_catches_a_registered_but_vanished_instrument(self) -> None:
        self.ensure_hypothesis()
        self.add("--hypothesis", "H1", "--file", "src/A.java:1", "--stub", "log")
        # The log line was never written / already edited away.
        rc, out = self.run_cmd(SCRIPT, "sweep", "--feature", "demo")
        self.assertEqual(rc, 1)
        self.assertIn("stale-instrument", out)

    def test_sweep_passes_when_tag_and_ledger_agree(self) -> None:
        self.ensure_hypothesis()
        self.add("--hypothesis", "H1", "--file", "src/A.java:1", "--stub", "log v=")
        (self.repo / "src" / "A.java").write_text(
            "a\nlog(\"IDEV-DBG I1 v=1\")\n", encoding="utf-8")
        rc, out = self.run_cmd(SCRIPT, "sweep", "--feature", "demo")
        self.assertEqual(rc, 0)
        self.assertIn("sweep PASS", out)


if __name__ == "__main__":
    unittest.main()
