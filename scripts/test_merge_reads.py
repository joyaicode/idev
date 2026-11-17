#!/usr/bin/env python3
"""merge_reads folds whole-file Reads into the ticket ledger — facts only.

Proposal 20261117-agent-loop-enhancement D2 (grilling 3a: transcript-
derived, ticket files only). Every test pins one clause of the contract:
no step context / no transcript / no repo → silent no-op; partial reads
never noted; existing rows never rewritten; spans and digests always
match the bytes on disk.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "lib"))

import trace  # noqa: E402


TRACE_BODY = """schema_version: 2
at: 2026-11-17T10:00:00+08:00
feature: demo
route:
  scenario: S8
  module: workflows
  stage: code
  why: 命中别名
thinking:
  summary: 一行
calls: []
recorded:
  - step: code-pass
    status: PASS
"""


def sh(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class MergeReads(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve()
        self.ticket = self.repo / ".idev" / "task" / "demo"
        (self.ticket / "workflow").mkdir(parents=True)
        sh("git", "init", "-q", ".", cwd=self.repo)
        self._cwd = Path.cwd()
        import os

        os.chdir(self.repo)
        self.addCleanup(os.chdir, self._cwd)

    def _transcript(self, uses: list[tuple[str, dict]]) -> None:
        """Fake this session's transcript where session_transcript looks.

        The module reads ~/.claude/projects/<slug-of-cwd>/*.jsonl — slug is
        a pure string transform of cwd, so pointing HOME at the temp repo
        (setUp chdir'd there) lands the fake file exactly where newest()
        looks. No monkey-patching: the module under test runs its real
        discovery path.
        """
        import os

        rows = []
        for i, (name, raw) in enumerate(uses):
            rows.append({
                "type": "assistant",
                "timestamp": "2026-11-17T10:%02d:00.000+08:00" % (i + 1),
                "message": {"content": [{"type": "tool_use", "name": name, "input": raw}]},
            })
        home = self.repo / "fake-home"
        slug = trace.session_transcript.slug()
        target = home / ".claude" / "projects" / slug
        target.mkdir(parents=True)
        (target / "session.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8",
        )
        os.environ["HOME"] = str(home)
        self.addCleanup(os.environ.pop, "HOME", None)

    def test_no_step_context_means_nothing_noted(self) -> None:
        bare = TRACE_BODY.replace("recorded:\n  - step: code-pass\n    status: PASS\n", "")
        self.assertEqual(trace.merge_reads(self.ticket, bare), [])

    def test_whole_file_read_becomes_one_ledger_row(self) -> None:
        import read_ledger

        source = self.repo / "src" / "app.py"
        source.parent.mkdir()
        source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
        self._transcript([("Read", {"file_path": str(source)})])
        noted = trace.merge_reads(self.ticket, TRACE_BODY)
        self.assertEqual(noted, ["src/app.py:1:2"])
        rows = read_ledger.load(self.ticket)
        self.assertEqual(rows, [{
            "step": "code-pass", "span": "src/app.py:1:2",
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }])

    def test_partial_read_is_never_noted(self) -> None:
        source = self.repo / "src" / "app.py"
        source.parent.mkdir()
        source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
        self._transcript([("Read", {"file_path": str(source), "offset": 1, "limit": 1})])
        self.assertEqual(trace.merge_reads(self.ticket, TRACE_BODY), [])

    def test_outside_repo_read_is_never_noted(self) -> None:
        # A directory above the checkout: reading it is real, noting it is
        # pointless — read_ledger refuses spans outside the repo, so the row
        # could never replay. (Inside the temp root would not prove this:
        # the temp root *is* the repo here.)
        outside = Path(self.tmp.name).parent / "idev-merge-reads-outside.txt"
        outside.write_text("x\n", encoding="utf-8")
        self.addCleanup(outside.unlink)
        self._transcript([("Read", {"file_path": str(outside)})])
        self.assertEqual(trace.merge_reads(self.ticket, TRACE_BODY), [])

    def test_existing_row_is_not_rewritten(self) -> None:
        import read_ledger

        source = self.repo / "src" / "app.py"
        source.parent.mkdir()
        source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
        old_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        read_ledger.note(self.ticket, "code-pass", "src/app.py:1:2", old_digest)
        source.write_text("def alpha():\n    return 2\n", encoding="utf-8")
        self._transcript([("Read", {"file_path": str(source)})])
        noted = trace.merge_reads(self.ticket, TRACE_BODY)
        # (step, span) already known → not noted, not rewritten: this fills
        # gaps, history stays as written.
        self.assertEqual(noted, [])
        rows = read_ledger.load(self.ticket)
        self.assertEqual(rows[0]["sha256"], old_digest)


if __name__ == "__main__":
    unittest.main()
