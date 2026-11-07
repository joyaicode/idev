#!/usr/bin/env python3
"""A loaded span is replayed into the next attempt when its bytes still match."""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import read_ledger  # noqa: E402


class ReadLedger(unittest.TestCase):
    def test_note_replaces_the_same_span(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ticket = Path(tmp.name)
        read_ledger.note(ticket, "code-pass", "src/a.go:1:20", "abc")
        read_ledger.note(ticket, "code-pass", "src/a.go:1:20", "def")
        rows = read_ledger.load(ticket)
        self.assertEqual(rows, [{"step": "code-pass", "span": "src/a.go:1:20", "sha256": "def"}])

    def test_load_without_feature_does_not_write_a_ledger(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        (repo / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
        cmd = [
            sys.executable, str(HERE / "context-stage.py"), "load",
            "--repo", str(repo), "--id", "a.txt:1:2",
        ]
        done = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse((repo / ".idev" / "task" / "demo" / "workflow" / "reads.yaml").exists())
        done = subprocess.run(cmd + ["--feature", "demo", "--step", "code-pass"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        rows = read_ledger.load(repo / ".idev" / "task" / "demo")
        self.assertEqual([row["span"] for row in rows if row.get("step") == "code-pass"], ["a.txt:1:2"])

    def test_project_replays_matching_bytes_and_drops_the_rest(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        ticket = repo / "ticket"
        source = repo / "src" / "a.go"
        source.parent.mkdir(parents=True)
        source.write_text("package a\nfunc F() {}\n", encoding="utf-8")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        read_ledger.note(ticket, "look", "src/a.go:1:2", digest)
        read_ledger.note(ticket, "look", "src/missing.go:1:1", digest)
        read_ledger.note(ticket, "look", "../secret:1:1", digest)
        shown = read_ledger.project(ticket, "look", repo, set())
        self.assertEqual(shown["context_blocks"][0]["span"], "src/a.go:1:2")
        self.assertIn("1|package a", shown["context_blocks"][0]["text"])
        self.assertIn("2|func F() {}", shown["context_blocks"][0]["text"])
        self.assertEqual(shown["context_stale"][0], {"span": "src/missing.go:1:1", "reason": "文件不在"})
        self.assertNotIn("secret", str(shown["context_blocks"]))
        self.assertEqual(shown["context_refused"][0]["span"], "../secret:1:1")
        source.write_text("package a\nfunc G() {}\n", encoding="utf-8")
        changed = read_ledger.project(ticket, "look", repo, set())
        self.assertNotIn("context_blocks", changed)
        self.assertIn({"span": "src/a.go:1:2", "reason": "文件已变"}, changed["context_stale"])
        self.assertNotIn("func F", str(changed))

    def test_project_omits_the_oldest_past_four_blocks(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        ticket = repo / "ticket"
        (repo / "src").mkdir()
        for i in range(5):
            path = repo / "src" / f"a{i}.go"
            path.write_text(f"line {i}\n", encoding="utf-8")
            read_ledger.note(ticket, "look", f"src/a{i}.go:1:1", hashlib.sha256(path.read_bytes()).hexdigest())
        shown = read_ledger.project(ticket, "look", repo, set())
        self.assertEqual(
            [block["span"] for block in shown["context_blocks"]],
            [f"src/a{i}.go:1:1" for i in range(1, 5)],
        )
        self.assertEqual(shown["context_omitted"], [{
            "span": "src/a0.go:1:1",
            "sha256": hashlib.sha256((repo / "src" / "a0.go").read_bytes()).hexdigest(),
        }])


if __name__ == "__main__":
    unittest.main()
