#!/usr/bin/env python3
"""The bounded-fix brake, measured instead of typed in.

conventions/evidence.md step 5 stops a fix loop on the same signature three
times, two rounds with no effective code change, or 15 minutes still red.
The second one used to take `--delta` on trust and call "the failure looks
the same" a semantic match. Both now come from git: how many lines moved,
and whether this patch *is* the last patch. A loop that reports on itself
has an interest in the answer, which is the one case where asking it is
the wrong design.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))

import safeyaml  # noqa: E402

SCRIPT = HERE / "failure_signature.py"
LOG = "FAILED test_x\nAssertionError: boom\n"


class BoundedFix(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve() / "one"
        self.repo.mkdir(parents=True)
        self.log = self.repo.parent / "fail.log"
        self.log.write_text(LOG, encoding="utf-8")

    def git_repo(self) -> None:
        for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
            subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)
        (self.repo / "a.txt").write_text("a\nb\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.repo, check=True, capture_output=True)

    def append(self, *extra: str) -> tuple[int, str]:
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), "append",
             "--feature", "demo", "--log", str(self.log), *extra],
            capture_output=True, text=True, timeout=60,
        )
        return done.returncode, done.stdout + done.stderr

    def attempts(self) -> list[dict]:
        data = safeyaml.mapping(self.repo / ".idev" / "task" / "demo" / "fix-attempts.yaml")
        return list(data["attempts"])

    # --- the brake ----------------------------------------------------

    def test_two_rounds_without_touching_the_code_escalate(self) -> None:
        self.git_repo()
        self.assertEqual(self.append()[0], 0)
        code, out = self.append()
        self.assertEqual(code, 2, out)
        self.assertIn("no effective code change", out)
        self.assertIn("escalate to a person", out)

    def test_a_real_change_keeps_the_loop_going(self) -> None:
        self.git_repo()
        (self.repo / "a.txt").write_text("a\nb\nc\n", encoding="utf-8")
        self.assertEqual(self.append()[0], 0)
        (self.repo / "a.txt").write_text("a\nb\nc\nd\n", encoding="utf-8")
        code, out = self.append()
        self.assertEqual(code, 0, out)
        self.assertEqual([a["delta"] for a in self.attempts()], [1, 2])

    def test_the_same_patch_twice_is_not_a_semantic_change(self) -> None:
        """Not "the failure looks the same" — this patch is byte-for-byte the last one."""
        self.git_repo()
        (self.repo / "a.txt").write_text("a\nb\nc\n", encoding="utf-8")
        self.append()
        self.append()
        self.assertEqual([a["semantic_change"] for a in self.attempts()], [True, False])

    def test_an_untracked_file_counts_as_a_change(self) -> None:
        self.git_repo()
        self.append()
        (self.repo / "new.txt").write_text("x\ny\n", encoding="utf-8")
        self.append("--result", "PASS")
        self.assertEqual([a["delta"] for a in self.attempts()], [0, 2])

    def test_the_ledger_writing_itself_is_not_a_change(self) -> None:
        """.idev/ is where this ledger lives; counting it would hide the brake behind itself.

        The ticket directory is usually committed, so from round two on the
        ledger shows up in `git diff HEAD` — a tree where nothing else moved
        would read as a change every single round and the brake would never
        fire. This is the case that bites in a real checkout, so it is the
        one the test builds.
        """
        self.git_repo()
        self.append()
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "ticket"], cwd=self.repo, check=True, capture_output=True)
        code, out = self.append()
        self.assertEqual(self.attempts()[1]["delta"], 0, out)
        code, out = self.append()
        self.assertEqual(code, 2, "a tracked ledger must not read as a code change")
        self.assertIn("no effective code change", out)

    # --- falling back -------------------------------------------------

    def test_without_git_the_round_uses_what_was_passed_and_says_so(self) -> None:
        code, out = self.append("--delta", "7")
        self.assertEqual(code, 0, out)
        self.assertIn("not a git checkout", out)
        self.assertEqual(self.attempts()[0]["delta"], 7)
        self.assertNotIn("patch_fingerprint", self.attempts()[0])

    def test_an_explicit_delta_wins_over_the_measurement(self) -> None:
        self.git_repo()
        (self.repo / "a.txt").write_text("a\nb\nc\n", encoding="utf-8")
        self.append("--delta", "99")
        self.assertEqual(self.attempts()[0]["delta"], 99)

    def test_the_record_line_still_has_its_four_fields(self) -> None:
        self.git_repo()
        _, out = self.append()
        line = next(ln for ln in out.splitlines() if ln.startswith("LINE "))
        self.assertEqual(len(line[5:].split(" | ")), 4, line)


if __name__ == "__main__":
    unittest.main()
