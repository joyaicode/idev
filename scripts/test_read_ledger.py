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

    def test_project_never_prunes_when_bytes_match_a_clean_worktree(self) -> None:
        """Grilling 4a of proposal 20261117: the pruner is a no-op without a diff.

        The digest gate runs first (a changed file is stale by digest before
        it is ever a pruning question), so pruning only ever enters the
        picture on a span whose bytes still match — and on a clean worktree
        there is no `context_pruned` at all. That is the `none` mode: callers
        behave exactly as before the hook existed.
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True, capture_output=True)
        ticket = repo / "ticket"
        (repo / "src").mkdir()
        py = repo / "src" / "app.py"
        py.write_text("def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True, capture_output=True)
        read_ledger.note(ticket, "look", "src/app.py:1:2", hashlib.sha256(py.read_bytes()).hexdigest())
        shown = read_ledger.project(ticket, "look", repo, set())
        self.assertIn("context_blocks", shown)
        self.assertNotIn("context_pruned", shown)

    def test_project_prunes_ast_span_outside_the_changed_function(self) -> None:
        """The ast-mode contract: outside beta±10 → context_pruned, visible.

        The setup is one state, read once: base commit → beta-only edit in
        the worktree → note the span against the *current* bytes. Nothing
        changes between the note and the projection, so the digest gate
        passes and the pruning question is the only one left. The 30 filler
        lines keep alpha's span farther than ±10 from beta, so the
        neighborhood rule has room to fire — and the row lands in
        `context_pruned` with the load hint, never in silence.
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True, capture_output=True)
        ticket = repo / "ticket"
        (repo / "src").mkdir()
        py = repo / "src" / "app.py"
        # 30 filler lines keep alpha's span farther than ±10 from beta.
        head = "def alpha():\n" + "".join("    # filler %d\n" % i for i in range(30)) + "    return 1\n"
        tail = "\n\ndef beta():\n    return 2\n"
        py.write_text(head + tail, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True, capture_output=True)
        # Beta-only worktree edit; the span is noted against these bytes.
        py.write_text(head + tail.replace("return 2", "return 5"), encoding="utf-8")
        alpha_span = "src/app.py:1:3"
        read_ledger.note(ticket, "look", alpha_span, hashlib.sha256(py.read_bytes()).hexdigest())
        shown = read_ledger.project(ticket, "look", repo, set())
        pruned = [row["span"] for row in shown.get("context_pruned") or []]
        self.assertIn(alpha_span, pruned)
        self.assertNotIn("context_blocks", shown)
        self.assertNotIn("context_stale", shown)

        # Same setup, but the ledger holds beta's own span: inside the
        # neighborhood, so it plays back — a prune that swallowed the
        # changed function itself would be the R3 failure mode.
        beta_span = "src/app.py:35:36"
        read_ledger.note(ticket, "look", beta_span, hashlib.sha256(py.read_bytes()).hexdigest())
        shown = read_ledger.project(ticket, "look", repo, set())
        played = [block["span"] for block in shown.get("context_blocks") or []]
        self.assertIn(beta_span, played)


if __name__ == "__main__":
    unittest.main()
