#!/usr/bin/env python3
"""solo_e2e: one person, every role, drive=auto — mid-chain gates ride the
machine checks and only the FINAL_REVIEW after done still asks.

Proposal 20261125-solo-e2e-through. The pure pieces this suite locks:
solo_e2e() composition, the SOLO_RELAXABLE_HOLDS subset of HARD_HOLDS
(unseal/reopen relax, 回退/promote/生产写/push/经验入库 never do), and the
FINAL_REVIEW line in session-context (pointer assembly, zero prose).

    python3 scripts/test_solo_e2e.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))

import drive_mode  # noqa: E402


def run_ctx(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HERE / "session-context.py"), *args],
        capture_output=True, text=True, check=False, cwd=cwd,
    )


class SoloE2E(unittest.TestCase):
    def test_composition_needs_both_solo_and_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / ".idev").mkdir()
            # One name in people.yaml: staffing is solo (a real checkout
            # without a list would fall back to git user, which the
            # developer's own machine supplies — not hermetic). solo_e2e
            # must not fire on staffing alone while drive is assisted.
            (repo / ".idev" / "people.yaml").write_text("people: [wang]\n", encoding="utf-8")
            self.assertFalse(drive_mode.solo_e2e(repo, repo / "state"))
            drive_mode.set_mode(repo, "auto", kernel_state=repo / "state")
            self.assertTrue(drive_mode.solo_e2e(repo, repo / "state"))

    def test_collaborative_never_fires(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / ".idev").mkdir()
            (repo / ".idev" / "people.yaml").write_text("people: [wang, li]\n", encoding="utf-8")
            drive_mode.set_mode(repo, "auto", kernel_state=repo / "state")
            self.assertFalse(drive_mode.solo_e2e(repo, repo / "state"))

    def test_solo_with_auto_fires(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / ".idev").mkdir()
            (repo / ".idev" / "people.yaml").write_text("people: [wang]\n", encoding="utf-8")
            drive_mode.set_mode(repo, "auto", kernel_state=repo / "state")
            self.assertTrue(drive_mode.solo_e2e(repo, repo / "state"))

    def test_solo_with_assisted_does_not_fire(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / ".idev").mkdir()
            (repo / "staffing.yaml").write_text(
                "roles:\n  product: [wang]\n  dev: [wang]\n", encoding="utf-8"
            )
            drive_mode.set_mode(repo, "assisted", kernel_state=repo / "state")
            self.assertFalse(drive_mode.solo_e2e(repo, repo / "state"))


class RelaxableHolds(unittest.TestCase):
    def test_relaxed_marks_are_exactly_the_unseal_words(self):
        self.assertEqual(
            set(drive_mode.SOLO_RELAXABLE_HOLDS),
            {"解封", "解除密封", "启封", "开封", "unseal",
             "打开基线", "重新打开基线", "打開基線", "重新打開基線", "reopen"},
        )
        self.assertTrue(
            set(drive_mode.SOLO_RELAXABLE_HOLDS) < set(drive_mode.HARD_HOLDS)
        )

    def test_reopen_relaxes_under_solo(self):
        self.assertTrue(drive_mode.hard_held("需要 reopen 基线"))
        self.assertFalse(drive_mode.hard_held("需要 reopen 基线", relax_solo=True))
        self.assertTrue(drive_mode.hard_held("解除密封", relax_solo=True) is False)

    def test_push_promote_rollback_never_relax(self):
        for text in ("准备 git push", "要 promote 了", "回退到需求", "生产写", "经验入库"):
            self.assertTrue(drive_mode.hard_held(text, relax_solo=True), text)

    def test_hard_held_signal_passes_relax_through(self):
        self.assertTrue(drive_mode.hard_held_signal("reopen 基线"))
        self.assertFalse(drive_mode.hard_held_signal("reopen 基线", relax_solo=True))
        self.assertTrue(drive_mode.hard_held_signal("git push", relax_solo=True))


class FinalReviewLine(unittest.TestCase):
    def _ticket(self, repo: Path, stage: str, aligned: bool) -> None:
        task = repo / "docs" / "task" / "demo"
        task.mkdir(parents=True, exist_ok=True)
        (task / "deliver.yaml").write_text(
            "stage: %s\naligned: %s\n" % (stage, "true" if aligned else "false"),
            encoding="utf-8",
        )

    def test_fires_on_done_and_aligned(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / ".idev").mkdir()
            (repo / "marker.yaml").write_text("marker: idev\nid: demo\n", encoding="utf-8")
            self._ticket(repo, "done", True)
            (repo / ".idev" / "drive-mode.yaml").write_text("mode: auto\n", encoding="utf-8")
            done = run_ctx("--repo", str(repo), "--feature", "demo")
            self.assertIn("FINAL_REVIEW demo", done.stdout, done.stdout + done.stderr)

    def test_not_before_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / ".idev").mkdir()
            (repo / "marker.yaml").write_text("marker: idev\nid: demo\n", encoding="utf-8")
            self._ticket(repo, "test", False)
            (repo / ".idev" / "drive-mode.yaml").write_text("mode: auto\n", encoding="utf-8")
            done = run_ctx("--repo", str(repo), "--feature", "demo")
            self.assertNotIn("FINAL_REVIEW", done.stdout)

    def test_done_but_not_aligned_does_not_fire(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / ".idev").mkdir()
            (repo / "marker.yaml").write_text("marker: idev\nid: demo\n", encoding="utf-8")
            self._ticket(repo, "done", False)
            (repo / ".idev" / "drive-mode.yaml").write_text("mode: auto\n", encoding="utf-8")
            done = run_ctx("--repo", str(repo), "--feature", "demo")
            self.assertNotIn("FINAL_REVIEW", done.stdout)

    def test_assisted_does_not_fire(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / ".idev").mkdir()
            (repo / "marker.yaml").write_text("marker: idev\nid: demo\n", encoding="utf-8")
            self._ticket(repo, "done", True)
            (repo / ".idev" / "drive-mode.yaml").write_text("mode: assisted\n", encoding="utf-8")
            done = run_ctx("--repo", str(repo), "--feature", "demo")
            self.assertNotIn("FINAL_REVIEW", done.stdout)


if __name__ == "__main__":
    unittest.main()
