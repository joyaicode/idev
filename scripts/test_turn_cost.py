#!/usr/bin/env python3
"""The turn-cost locks: what counts as read-only, when a ratio fails, which
transcript shapes are read, and where a session's own transcript is.

These back state/proposals/20261102-turn-cost-reduction.md. selfcheck.sh
replays the fixtures end to end; this file pins the edges a fixture cannot
show — a write command that must not pass as a read, a repo name with a dot
in it, a transcript that is not there at all.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import session_transcript  # noqa: E402


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TB = load("turn_budget", ROOT / "scripts" / "turn-budget.py")


def assistant_cursor(tools=(), text=""):
    content = []
    if text:
        content.append({"type": "text", "text": text})
    for name, raw in tools:
        content.append({"type": "tool_use", "name": name, "input": raw})
    return {"role": "assistant", "message": {"content": content}}


def reads(n, start=0):
    return [("Read", {"path": f"f{i}"}) for i in range(start, start + n)]


class ReadOnly(unittest.TestCase):
    """A call counts as read-only only when the command line says so."""

    def test_named_read_tools_count(self):
        for name in ("Read", "Grep", "Glob", "NotebookRead"):
            self.assertTrue(TB.readonly(name, {}), name)
        self.assertTrue(TB.readonly("mcp__codegraph__codegraph_context", {}))

    def test_plain_read_commands_count(self):
        for cmd in ("ls -la", "cat f", "grep -n x f", "git status --short",
                    "git log --oneline", "wc -l f", "find . -name x",
                    "head -5 f", "git diff HEAD"):
            self.assertTrue(TB.readonly("Bash", {"command": cmd}), cmd)

    def test_write_commands_do_not_count(self):
        for cmd in ("rm -rf f", "mv a b", "cp a b", "mkdir -p d", "touch f",
                    "git commit -m x", "git push", "git add .", "sed -i '' s/a/b/ f",
                    "chmod +x f", "tee f", "ln -s a b"):
            self.assertFalse(TB.readonly("Bash", {"command": cmd}), cmd)

    def test_a_redirect_is_a_write(self):
        self.assertFalse(TB.readonly("Bash", {"command": "grep x f > out"}))
        self.assertFalse(TB.readonly("Bash", {"command": "cat f >> out"}))

    def test_a_pipe_between_reads_is_still_a_read(self):
        self.assertTrue(TB.readonly("Bash", {"command": "grep x f | head -3"}))

    def test_a_script_deciding_for_itself_does_not_count(self):
        # The command line cannot say whether workflow.py writes. A miss here
        # costs less than a false alarm, so it is not a read.
        self.assertFalse(TB.readonly("Bash", {"command": "python3 scripts/workflow.py next"}))

    def test_an_edit_is_not_a_read(self):
        self.assertFalse(TB.readonly("Edit", {"file_path": "f"}))
        self.assertFalse(TB.readonly("Write", {"file_path": "f"}))


class Ratio(unittest.TestCase):
    """One read per round is the shape a person waits through."""

    def scan(self, events, **kw):
        return TB.scan(events, kw.pop("limit", 8), kw.pop("min_reads", TB.MIN_READS),
                       kw.pop("min_ratio", TB.MIN_RATIO))

    def opened(self):
        return (TB.event({"role": "user", "message": {"content": [
            {"type": "text", "text": "<user_query>\nq\n</user_query>"}]}}),)

    def rounds_of(self, groups, text="说一句"):
        """One assistant message per group, each carrying that group's reads."""
        out = list(self.opened())
        for group in groups:
            out.append(TB.event(assistant_cursor(group, text)))
        return out

    def test_one_read_per_round_fails(self):
        found = self.scan(self.rounds_of([[r] for r in reads(8)]))
        self.assertTrue(any("serial_reads=8 rounds=8" in f for f in found), found)

    def test_the_same_reads_shared_pass(self):
        found = self.scan(self.rounds_of([reads(4), reads(4, 4)]))
        self.assertEqual([f for f in found if "serial_reads" in f], [], found)

    def test_a_short_stretch_is_not_judged(self):
        # Under --min-reads there is nothing to batch; saying so would be noise.
        found = self.scan(self.rounds_of([[r] for r in reads(TB.MIN_READS - 1)]))
        self.assertEqual([f for f in found if "serial_reads" in f], [], found)

    def test_writes_between_reads_do_not_lower_the_ratio(self):
        # Only rounds that carry a read are counted, so an edit between them
        # neither helps nor hurts.
        groups = []
        for r in reads(8):
            groups.append([r])
            groups.append([("Edit", {"file_path": "f"})])
        found = self.scan(self.rounds_of(groups))
        self.assertTrue(any("rounds=8" in f for f in found), found)

    def test_the_threshold_is_a_knob(self):
        # Eight reads in two messages average 4.0, so a demand of 5.0 fails
        # what the default 1.5 lets through.
        batched = self.rounds_of([reads(4), reads(4, 4)])
        self.assertEqual([f for f in self.scan(batched) if "serial_reads" in f], [])
        self.assertTrue(any("serial_reads" in f
                            for f in self.scan(batched, min_ratio=5.0)))


class Shapes(unittest.TestCase):
    """Both transcript shapes, and the tool-name difference between them."""

    def test_cursor_user_query_opens_a_segment(self):
        role, starts, _, _ = TB.event({"role": "user", "message": {"content": [
            {"type": "text", "text": "<user_query>\nq\n</user_query>"}]}})
        self.assertEqual(role, "user")
        self.assertTrue(starts)

    def test_cursor_plain_user_text_does_not_open_one(self):
        _, starts, _, _ = TB.event({"role": "user", "message": {"content": [
            {"type": "text", "text": "no marker"}]}})
        self.assertFalse(starts)

    def test_claude_code_user_message_opens_a_segment(self):
        role, starts, _, _ = TB.event({"type": "user", "message": {
            "role": "user", "content": "看一下"}})
        self.assertEqual(role, "user")
        self.assertTrue(starts)

    def test_a_tool_result_does_not_open_a_segment(self):
        _, starts, _, _ = TB.event({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "content": "out"}]}})
        self.assertFalse(starts)

    def test_a_meta_line_does_not_open_a_segment(self):
        _, starts, _, _ = TB.event({"type": "user", "isMeta": True,
                                    "message": {"role": "user", "content": "meta"}})
        self.assertFalse(starts)

    def test_non_conversation_lines_are_dropped(self):
        for kind in ("mode", "permission-mode", "atis-latch", "summary"):
            self.assertIsNone(TB.event({"type": kind}))

    def test_bash_is_the_shell(self):
        _, _, _, tools = TB.event({"type": "assistant", "message": {
            "role": "assistant", "content": [{"type": "tool_use", "name": "Bash",
                                              "input": {"command": "go test ./...",
                                                        "block_until_ms": 120000}}]}})
        self.assertEqual(TB.shell_cmds(tools), [("go test ./...", 120000)])

    def test_shell_still_is(self):
        _, _, _, tools = TB.event(assistant_cursor(
            [("Shell", {"command": "ls", "block_until_ms": 1})]))
        self.assertEqual(TB.shell_cmds(tools), [("ls", 1)])


class Fixtures(unittest.TestCase):
    """The fixtures selfcheck replays keep their verdicts."""

    FIX = ROOT / "test" / "fixtures" / "turn-budget"

    def run_tb(self, name):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "turn-budget.py"), str(self.FIX / name)],
            capture_output=True, text=True,
        )

    def test_green_cursor_fixture_passes(self):
        self.assertEqual(self.run_tb("green.jsonl").returncode, 0)

    def test_streak_fixture_still_reports_its_streak(self):
        out = self.run_tb("streak.jsonl")
        self.assertEqual(out.returncode, 1)
        self.assertIn("streak=9", out.stdout)

    def test_claude_shape_fixture_is_read_at_all(self):
        # Before the shape was read, a transcript with a 159-round silent
        # streak in it came back "ok".
        out = self.run_tb("claude-shape.jsonl")
        self.assertEqual(out.returncode, 1)
        self.assertIn("long_block=120000", out.stdout)
        self.assertIn("serial_reads=9", out.stdout)

    def test_shared_reads_fixture_passes(self):
        self.assertEqual(self.run_tb("shared-reads.jsonl").returncode, 0)

    def test_no_path_means_this_session(self):
        # Without a transcript the budget is not a failure. A fresh temp
        # directory has no project folder, so it is that case.
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "turn-budget.py")],
                capture_output=True, text=True, cwd=tmp,
            )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("no transcript", out.stdout)

    def test_a_named_path_that_is_not_a_file_is_an_error(self):
        # Parsing answers [] for a file it cannot read, so without this a
        # typo in the path would come back as a cheerful "ok".
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "turn-budget.py"),
                 str(Path(tmp) / "nope.jsonl")],
                capture_output=True, text=True,
            )
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertNotIn("ok", out.stdout)

    def test_a_torn_line_does_not_refuse_the_whole_file(self):
        # A transcript being written to mid-round should still be judgeable.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text(
                json.dumps({"type": "user", "message": {"role": "user",
                                                        "content": "q"}}) + "\n"
                '{"type": "assistant" torn\n', encoding="utf-8")
            out = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "turn-budget.py"), str(path)],
                capture_output=True, text=True,
            )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


class SessionFolder(unittest.TestCase):
    """The project-folder name rule, and being tolerant of having no file."""

    def test_dots_become_dashes_too(self):
        # Replacing only slashes misses every repo with a dot in its name.
        got = session_transcript.slug(Path("/Users/x/go/src/coding.jd.com/joypaas"))
        self.assertEqual(got, "-Users-x-go-src-coding-jd-com-joypaas")

    def test_a_leading_slash_becomes_a_dash(self):
        self.assertTrue(session_transcript.slug(Path("/tmp")).startswith("-"))

    def test_no_folder_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(session_transcript.newest(Path(tmp)))
            self.assertEqual(session_transcript.session(Path(tmp)), (0, 0))

    def test_rounds_of_none_does_not_fall_back_to_this_session(self):
        # A caller that already looked and found nothing must not be handed
        # the running conversation in its place.
        self.assertEqual(session_transcript.rounds(None), (0, 0))

    def test_rounds_counts_assistant_lines_and_last_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in [
                {"type": "mode"},
                {"type": "user", "message": {"role": "user", "content": "hi"}},
                {"type": "assistant", "message": {"role": "assistant", "content": [],
                                                  "usage": {"input_tokens": 2,
                                                            "cache_read_input_tokens": 1000}}},
                {"type": "assistant", "message": {"role": "assistant", "content": [],
                                                  "usage": {"input_tokens": 2,
                                                            "cache_creation_input_tokens": 3000}}},
            ]) + "\n", encoding="utf-8")
            self.assertEqual(session_transcript.rounds(path), (2, 3002))

    def test_a_broken_line_does_not_stop_the_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text(
                '{"type": "assistant", "message": {"role": "assistant"}}\n'
                '{"type": "assistant" oops\n', encoding="utf-8")
            self.assertEqual(session_transcript.rounds(path)[0], 1)


class Handoff(unittest.TestCase):
    """HANDOFF names the ticket and says it is not a stop."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.trace = load("trace_mod", ROOT / "scripts" / "trace.py")
        except Exception as exc:  # pragma: no cover
            raise unittest.SkipTest(f"trace.py not importable here: {exc}")

    def test_threshold_matches_the_measured_crossing(self):
        # Context crossed 100k around round 95-100 across ten sessions.
        self.assertEqual(self.trace.HANDOFF_ROUNDS, 100)

    def test_the_line_carries_ticket_and_stage(self):
        line = self.trace.handoff_line(
            'feature: "demo"\nroute:\n  stage: "code"\n', 137, 152000)
        self.assertTrue(line.startswith("HANDOFF rounds=137"))
        self.assertIn("ctx=152000", line)
        self.assertIn("feature=demo", line)
        self.assertIn("stage=code", line)
        self.assertIn("不是停点", line)

    def test_a_missing_context_size_is_left_out(self):
        line = self.trace.handoff_line('feature: "demo"\n', 101, 0)
        self.assertNotIn("ctx=", line)

    def test_the_budget_holds_off_until_a_verdict_is_possible(self):
        # serial_reads needs six rounds carrying a read; a streak needs nine.
        # Under that floor the child process would read megabytes to say
        # nothing.
        self.assertLessEqual(self.trace.BUDGET_FROM_ROUND, TB.MIN_READS)
        self.assertGreater(self.trace.BUDGET_FROM_ROUND, 0)
        self.assertLess(self.trace.BUDGET_FROM_ROUND, self.trace.HANDOFF_ROUNDS)


class AgentColdStart(unittest.TestCase):
    """--agents prints the other cold start without judging it."""

    def test_it_lists_every_executor_and_exits_zero(self):
        out = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "cold-start-size.py"), "--agents"],
            capture_output=True, text=True,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        for page in ("idev-coder.md", "idev-deliver.md", "idev-ops.md",
                     "idev-reviewer.md", "idev-verifier.md"):
            self.assertIn(page, out.stdout)
        self.assertNotIn("FAIL", out.stdout)

    def test_the_conductor_budget_is_untouched(self):
        """--agents must not change what the conductor's budget counts.

        The budget is COLD and nothing else; the on-demand list below it is
        named by SKILL.md's body and is explicitly not counted. Executor
        pages belong on that list — the capability table points at them by
        name and `BODY_REF` includes `agents/` on purpose — so "the output
        never says idev-coder.md" was a stand-in that SKILL.md outgrew,
        not the property being guarded. Check the property instead: the
        counted section holds the two cold-start pages and nothing from
        agents/, and the agent view's own header stays out.
        """
        out = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "cold-start-size.py")],
            capture_output=True, text=True,
        )
        self.assertIn("cold start", out.stdout)
        self.assertNotIn("# agent cold start:", out.stdout)
        counted = out.stdout.split("on demand")[0]
        self.assertIn("SKILL.md", counted)
        self.assertIn("references/agent-brief.md", counted)
        self.assertNotIn("agents/", counted)


class LastPrompt(unittest.TestCase):
    """The person's own words, read back from the transcript."""

    def write(self, tmp, rows):
        path = Path(tmp) / "t.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return path

    def test_the_most_recent_words_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, [
                {"type": "user", "message": {"role": "user", "content": "第一句"}},
                {"type": "assistant", "message": {"role": "assistant", "content": []}},
                {"type": "user", "message": {"role": "user", "content": "第二句"}},
            ])
            self.assertEqual(session_transcript.last_prompt(path), "第二句")

    def test_a_tool_result_is_not_the_person_talking(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, [
                {"type": "user", "message": {"role": "user", "content": "真的人话"}},
                {"type": "assistant", "message": {"role": "assistant", "content": []}},
                {"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "content": "命令输出"}]}},
            ])
            self.assertEqual(session_transcript.last_prompt(path), "真的人话")

    def test_a_meta_line_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, [
                {"type": "user", "message": {"role": "user", "content": "真的人话"}},
                {"type": "user", "isMeta": True,
                 "message": {"role": "user", "content": "注入的上下文"}},
            ])
            self.assertEqual(session_transcript.last_prompt(path), "真的人话")

    def test_no_transcript_is_empty_not_an_error(self):
        self.assertEqual(session_transcript.last_prompt(None), "")


class MergeFacts(unittest.TestCase):
    """A script fills the facts. It never fills a judgement."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.trace = load("trace_facts", ROOT / "scripts" / "trace.py")
        except Exception as exc:  # pragma: no cover
            raise unittest.SkipTest(f"trace.py not importable here: {exc}")

    def test_one_line_clips_and_escapes(self):
        one = self.trace._one_line('他说 "改一下"\n第二行', limit=200)
        self.assertEqual(one, '"他说 \\"改一下\\""')
        self.assertNotIn("\n", one)

    def test_one_line_respects_the_limit(self):
        one = self.trace._one_line("长" * 500, limit=10)
        self.assertLessEqual(len(one), 10 + 4)
        self.assertTrue(one.endswith('…"'))

    def test_a_trigger_already_written_is_left_alone(self):
        text = 'invoke:\n  trigger: "人自己写的"\n  matched: "x"\n'
        self.assertEqual(self.trace.merge_facts(text), text)

    def test_no_invoke_block_is_left_alone(self):
        text = 'route:\n  module: conventions\n'
        self.assertEqual(self.trace.merge_facts(text), text)

    def test_judgements_are_never_filled(self):
        # The point of the line: facts yes, reasoning no.
        text = ('invoke:\n  trigger: ""\n  matched: ""\n'
                'route:\n  module: conventions\n  why: ""\n'
                'thinking:\n  summary: ""\n')
        out = self.trace.merge_facts(text)
        self.assertEqual(self.trace.field(self.trace.block(out, "route"), "why"), "")
        self.assertEqual(
            self.trace.field(self.trace.block(out, "thinking"), "summary"), "")
        self.assertEqual(self.trace.field(self.trace.block(out, "invoke"), "matched"), "")

    def test_a_surprise_leaves_the_text_alone(self):
        # It runs on every round; it must not be able to break one.
        text = 'invoke:\n  trigger: ""\n'
        with mock.patch.object(self.trace.session_transcript, "newest",
                               side_effect=RuntimeError("boom")):
            self.assertEqual(self.trace.merge_facts(text), text)

    def test_nothing_said_means_nothing_filled(self):
        text = 'invoke:\n  trigger: ""\n'
        with mock.patch.object(self.trace.session_transcript, "last_prompt",
                               return_value="   "):
            self.assertEqual(self.trace.merge_facts(text), text)

    def test_it_fills_from_what_the_person_said(self):
        text = 'invoke:\n  trigger: ""\n  matched: "x"\n'
        with mock.patch.object(self.trace.session_transcript, "newest",
                               return_value=Path("/nonexistent.jsonl")), \
             mock.patch.object(self.trace.session_transcript, "last_prompt",
                               return_value="继续完成所有优化"):
            out = self.trace.merge_facts(text)
        self.assertEqual(
            self.trace.field(self.trace.block(out, "invoke"), "trigger"),
            "继续完成所有优化")
        # Filling one field does not disturb its neighbours.
        self.assertIn('matched: "x"', out)


class ToolUses(unittest.TestCase):
    """Tool calls come out raw; what they mean is the caller's call."""

    def write(self, tmp, rows):
        path = Path(tmp) / "t.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return path

    def row(self, name, raw, stamp=None):
        row = {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": name, "input": raw}]}}
        if stamp:
            row["timestamp"] = stamp
        return row

    def test_calls_come_back_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, [self.row("Read", {"file_path": "a"}),
                                    self.row("Bash", {"command": "ls"})])
            self.assertEqual(session_transcript.tool_uses(path),
                             [("Read", {"file_path": "a"}), ("Bash", {"command": "ls"})])

    def test_a_window_filters_by_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, [
                self.row("Read", {"file_path": "old"}, "2026-11-01T10:00:00+08:00"),
                self.row("Read", {"file_path": "new"}, "2026-11-02T10:00:00+08:00"),
            ])
            since = dt.datetime.fromisoformat("2026-11-01T12:00:00+08:00")
            got = session_transcript.tool_uses(path, since, None)
            self.assertEqual([raw["file_path"] for _, raw in got], ["new"])

    def test_a_line_without_a_timestamp_is_kept(self):
        # Dropping a call that really happened is worse than keeping a stray.
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, [self.row("Read", {"file_path": "nostamp"})])
            since = dt.datetime.fromisoformat("2026-11-01T12:00:00+08:00")
            self.assertEqual(len(session_transcript.tool_uses(path, since, None)), 1)

    def test_no_transcript_is_an_empty_list(self):
        self.assertEqual(session_transcript.tool_uses(None), [])

    def test_the_same_file_is_parsed_once(self):
        # A round asks the same megabytes several things.
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, [self.row("Read", {"file_path": "a"})])
            self.assertIs(session_transcript.rows(path), session_transcript.rows(path))

    def test_a_grown_file_is_not_served_stale(self):
        # Size is in the cache key, so a transcript written to mid-round is
        # re-read even when mtime has not ticked.
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, [self.row("Read", {"file_path": "a"})])
            first = len(session_transcript.tool_uses(path))
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(self.row("Read", {"file_path": "b"})) + "\n")
            second = len(session_transcript.tool_uses(path))
        self.assertEqual((first, second), (1, 2))


class MergeOpened(unittest.TestCase):
    """opened is filled from facts. calls stays the conductor's."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.trace = load("trace_opened", ROOT / "scripts" / "trace.py")
        except Exception as exc:  # pragma: no cover
            raise unittest.SkipTest(f"trace.py not importable here: {exc}")

    def test_a_kernel_page_becomes_relative(self):
        self.assertEqual(
            self.trace._kernel_relative(str(ROOT / "SKILL.md")), "SKILL.md")
        self.assertEqual(
            self.trace._kernel_relative(str(ROOT / "references" / "agent-brief.md")),
            "references/agent-brief.md")

    def test_a_file_outside_the_kernel_is_not_a_page(self):
        self.assertEqual(self.trace._kernel_relative("/etc/hosts"), "")
        self.assertEqual(self.trace._kernel_relative(""), "")

    def test_an_opened_list_already_written_is_left_alone(self):
        text = "opened:\n  - SKILL.md\n"
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.trace.merge_opened(text, Path(tmp)), text)

    def test_a_surprise_leaves_the_text_alone(self):
        text = "opened: []\n"
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(self.trace.session_transcript, "newest",
                               side_effect=RuntimeError("boom")):
            self.assertEqual(self.trace.merge_opened(text, Path(tmp)), text)

    def test_calls_are_never_filled(self):
        # The line this change refuses to cross: deciding whether a shell
        # command is a call, and under which kind, is a judgement — and a
        # wrong audit entry is worse than a missing one.
        text = "opened: []\ncalls: []\n"
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(self.trace.session_transcript, "tool_uses",
                               return_value=[("Bash", {"command": "python3 scripts/x.py"}),
                                             ("Read", {"file_path": str(ROOT / "SKILL.md")})]):
            out = self.trace.merge_opened(text, Path(tmp))
        self.assertIn("SKILL.md", out)
        self.assertNotIn("scripts/x.py", out)
        self.assertEqual(self.trace.block(out, "calls").strip(), "")

    def test_reads_of_kernel_pages_are_listed_once(self):
        page = str(ROOT / "SKILL.md")
        text = "opened: []\n"
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(self.trace.session_transcript, "tool_uses",
                               return_value=[("Read", {"file_path": page}),
                                             ("Read", {"file_path": page}),
                                             ("Edit", {"file_path": page})]):
            out = self.trace.merge_opened(text, Path(tmp))
        self.assertEqual(out.count("SKILL.md"), 1, out)


if __name__ == "__main__":
    unittest.main()
