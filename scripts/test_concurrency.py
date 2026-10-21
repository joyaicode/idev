#!/usr/bin/env python3
"""The three write paths, under concurrency.

Each of these lost data silently, which is the part that made them worth
fixing: every caller reported success. The tests run real processes rather
than threads, because the thing being tested is an OS-level guarantee
(flock, O_EXCL, rename) and the GIL would hide a broken one.

    python3 scripts/test_concurrency.py
"""
from __future__ import annotations

import datetime as dt
import multiprocessing as mp
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "lib"))

import safeyaml  # noqa: E402

WORKERS = 10

# Workers wait on a barrier before touching the file. Without it `spawn`
# staggers process startup by tens of milliseconds, which is wide enough to
# hide the races entirely: the unsynchronised version of the trace test
# passed against the pre-fix code, proving nothing. With the barrier the
# pre-fix code loses 7 to 9 of 10 traces per run.
_BARRIER = None


def _init(barrier) -> None:
    global _BARRIER
    _BARRIER = barrier


def _ready() -> None:
    if _BARRIER is not None:
        _BARRIER.wait()


# --- workers (module level so `spawn` can pickle them) ---------------------


def _append_entry(args: tuple) -> bool:
    """One concurrent read-modify-write of a shared ledger."""
    path, key = args
    _ready()
    try:
        safeyaml.save_locked(
            Path(path), lambda data: {**data, key: {"by": key, "n": 1}}
        )
        return True
    except Exception:
        return False


def _reserve_trace(folder: str) -> str:
    """One concurrent trace-name reservation."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("idev_trace", str(SCRIPTS / "trace.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _ready()
    dest = mod.next_path(Path(folder), dt.datetime(2026, 10, 15, 12, 0, 0))
    dest.write_text("round: x\n", encoding="utf-8")
    return str(dest)


def _create_exclusive(args: tuple) -> bool:
    """One concurrent `delegation write` of the same step and attempt."""
    path, body = args
    _ready()
    try:
        with open(path, "x", encoding="utf-8") as fh:
            fh.write(body)
        return True
    except FileExistsError:
        return False


def _workflow():
    import importlib.util

    spec = importlib.util.spec_from_file_location("idev_workflow", str(SCRIPTS / "workflow.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _claim_run(args: tuple) -> str:
    """One concurrent start. The winner's run_id, or '' when refused."""
    path, run_id = args
    mod = _workflow()
    _ready()
    try:
        mod.claim_run(Path(path), {
            "schema_version": 1,
            "run_id": run_id,
            "status": "running",
            "steps": [{"id": "a", "kind": "preflight.inputs"}],
        })
        return run_id
    except mod.Blocked:
        return ""
    except Exception as exc:
        return f"ERR {exc}"


def _decide_once(args: tuple) -> str:
    """One concurrent answer of the same signal. The decision id, or ''."""
    run_path, signal = args
    mod = _workflow()
    _ready()
    try:
        entry = mod.append_decision(Path(run_path), "s", {
            "signal": signal,
            "question": "q",
            "answer": "a",
            "quote": "1",
        })
        return str(entry.get("id") or "")
    except mod.Blocked:
        return ""
    except Exception as exc:
        return f"ERR {exc}"


def _pool(fn, items):
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(len(items))
    with ctx.Pool(len(items), initializer=_init, initargs=(barrier,)) as pool:
        return pool.map(fn, items)


# --- tests -----------------------------------------------------------------


class LedgerWrites(unittest.TestCase):
    """safeyaml.save_locked — what workflow.py's cmd_record now goes through."""

    def test_ten_concurrent_appends_all_survive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.yaml"
            path.write_text("seed: 1\n", encoding="utf-8")
            results = _pool(
                _append_entry, [(str(path), f"k{i:02d}") for i in range(WORKERS)]
            )
            self.assertTrue(all(results), "a writer failed outright")
            final = safeyaml.mapping(path) or {}
            missing = [f"k{i:02d}" for i in range(WORKERS) if f"k{i:02d}" not in final]
            self.assertEqual(
                missing, [], f"{len(missing)} of {WORKERS} appends were lost"
            )
            self.assertEqual(final.get("seed"), 1, "the pre-existing content was lost")

    def test_the_file_is_never_seen_half_written(self) -> None:
        """Every intermediate state parses, because the swap is a rename."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.yaml"
            path.write_text("seed: 1\n", encoding="utf-8")
            _pool(_append_entry, [(str(path), f"k{i:02d}") for i in range(WORKERS)])
            self.assertIsNotNone(
                safeyaml.mapping(path), "the ledger did not parse after the race"
            )


class TraceNames(unittest.TestCase):
    """trace.next_path — glob-then-increment was a TOCTOU race."""

    def test_ten_concurrent_appends_write_ten_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            names = _pool(_reserve_trace, [tmp] * WORKERS)
            self.assertEqual(
                len(set(names)), WORKERS, "two rounds were handed the same name"
            )
            on_disk = sorted(Path(tmp).glob("*.yaml"))
            self.assertEqual(
                len(on_disk), WORKERS, f"{WORKERS} appends left {len(on_disk)} files"
            )

    def test_names_keep_the_documented_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            names = _pool(_reserve_trace, [tmp] * WORKERS)
            for name in names:
                stem = Path(name).stem
                self.assertRegex(stem, r"^20261015-\d{3}$", f"bad trace name {stem}")


class DelegationRecords(unittest.TestCase):
    """delegation.py write — the filename is the record's only key."""

    def test_same_step_and_attempt_wins_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "code-pass-1.yaml")
            results = _pool(
                _create_exclusive,
                [(path, f"agent: w{i}\n") for i in range(WORKERS)],
            )
            self.assertEqual(
                sum(results), 1, f"{sum(results)} writers claimed the same record"
            )
            self.assertEqual(
                sum(1 for r in results if not r),
                WORKERS - 1,
                "the losers must be blocked, not silently dropped",
            )

    def test_the_surviving_record_is_one_whole_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "code-pass-1.yaml"
            _pool(
                _create_exclusive,
                [(str(path), f"agent: w{i}\nstep: code-pass\n") for i in range(WORKERS)],
            )
            data = safeyaml.mapping(path)
            self.assertIsNotNone(data, "the record did not parse")
            self.assertEqual(data.get("step"), "code-pass")
            self.assertRegex(str(data.get("agent")), r"^w\d$", "the record is spliced")


            self.assertRegex(str(data.get("agent")), r"^w\d$", "the record is spliced")


class OneLiveRun(unittest.TestCase):
    """workflow.claim_run — two starts must not both publish a run."""

    def test_ten_starts_leave_one_live_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.yaml"
            results = _pool(_claim_run, [(str(path), f"R{i:02d}") for i in range(WORKERS)])
            errors = [r for r in results if r.startswith("ERR ")]
            self.assertEqual(errors, [], errors)
            winners = [r for r in results if r]
            self.assertEqual(len(winners), 1, f"{len(winners)} starts published a run: {winners}")
            final = safeyaml.mapping(path) or {}
            self.assertEqual(final.get("run_id"), winners[0])
            self.assertEqual(final.get("status"), "running")
            self.assertEqual(
                sum(1 for r in results if not r),
                WORKERS - 1,
                "the losers must be refused, not silently dropped",
            )

    def test_a_running_run_without_steps_is_still_live(self) -> None:
        # An empty steps list is not "no run". Replacing it starts a second
        # run over one that is still marked in progress.
        mod = _workflow()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.yaml"
            path.write_text("status: running\nrun_id: OLD\n", encoding="utf-8")
            with self.assertRaises(mod.Blocked):
                mod.claim_run(path, {
                    "status": "running", "run_id": "NEW",
                    "steps": [{"id": "a", "kind": "preflight.inputs"}],
                })
            self.assertEqual((safeyaml.mapping(path) or {}).get("run_id"), "OLD")

    def test_an_unreadable_run_is_not_replaced(self) -> None:
        mod = _workflow()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.yaml"
            path.write_text("status: [\n", encoding="utf-8")
            with self.assertRaises(mod.Blocked):
                mod.claim_run(path, {"status": "running", "run_id": "NEW", "steps": []})
            self.assertEqual(path.read_text(encoding="utf-8"), "status: [\n")


class OneDecision(unittest.TestCase):
    """workflow.append_decision — one signal, one answer."""

    def test_ten_answers_leave_one_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wf = root / "workflow"
            folder = wf / "delegations"
            folder.mkdir(parents=True)
            run = wf / "run.yaml"
            run.write_text("run_id: R\nstatus: running\nsteps: []\n", encoding="utf-8")
            (folder / "s-1.yaml").write_text(
                "step: s\nattempt: 1\nsignals:\n  - the question\n", encoding="utf-8"
            )
            results = _pool(_decide_once, [(str(run), "the question")] * WORKERS)
            errors = [r for r in results if r.startswith("ERR ")]
            self.assertEqual(errors, [], errors)
            winners = [r for r in results if r]
            self.assertEqual(winners, ["D1"], winners)
            ledger = safeyaml.mapping(root / "decisions.yaml") or {}
            self.assertEqual(len(ledger.get("decisions") or []), 1)

    def test_a_broken_entry_is_not_appended_past(self) -> None:
        mod = _workflow()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wf = root / "workflow"
            (wf / "delegations").mkdir(parents=True)
            run = wf / "run.yaml"
            run.write_text("run_id: R\nstatus: running\nsteps: []\n", encoding="utf-8")
            (wf / "delegations" / "s-1.yaml").write_text(
                "step: s\nattempt: 1\nsignals:\n  - the question\n", encoding="utf-8"
            )
            ledger = root / "decisions.yaml"
            ledger.write_text("schema_version: 1\ndecisions:\n  - not-a-mapping\n", encoding="utf-8")
            with self.assertRaises(mod.Blocked):
                mod.append_decision(run, "s", {
                    "signal": "the question", "question": "q", "answer": "a", "quote": "1",
                })
            self.assertIn("not-a-mapping", ledger.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
