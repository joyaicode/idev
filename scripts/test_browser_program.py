#!/usr/bin/env python3
"""browser-program.py 的准入与回执。不启动浏览器。

    python3 scripts/test_browser_program.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("browser_program", SCRIPTS / "browser-program.py")
prog = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(prog)  # type: ignore[union-attr]


READ = "await page.goto('https://example.test'); return await page.title();"
CLICK = (
    "await page.getByRole('button', {name: 'Save'}).click();\n"
    "await expect(page.getByText('Saved')).toBeVisible();"
)


def _sub(program: str, request_id: str = "save-01", **extra) -> dict:
    body = {"task": "save-profile", "request_id": request_id, "program": program}
    body.update(extra)
    return body


def _lane_after_run(submission: dict) -> dict:
    decision = prog.admit({}, submission)
    return prog.put({}, decision["receipt"])


class AdmitTest(unittest.TestCase):
    def test_read_runs_then_same_id_returns_receipt(self) -> None:
        submission = _sub(READ)
        first = prog.admit({}, submission)
        self.assertEqual(first["action"], "run")
        self.assertEqual(first["receipt"]["status"], "queued")
        self.assertFalse(first["receipt"]["business_ok"])
        lane = _lane_after_run(submission)
        second = prog.admit(lane, submission)
        self.assertEqual(second["action"], "stored")
        self.assertEqual(second["receipt"]["program_sha256"], first["receipt"]["program_sha256"])

    def test_same_id_new_text_needs_a_new_id(self) -> None:
        lane = _lane_after_run(_sub(READ))
        decision = prog.admit(lane, _sub(READ + "\nreturn 1;"))
        self.assertEqual(decision["reason"], "new_id_required")

    def test_write_without_assertion_is_refused(self) -> None:
        program = "await page.getByRole('button', {name: 'Save'}).click();"
        decision = prog.admit({}, _sub(program))
        self.assertEqual(decision["reason"], "assertion_required")

    def test_write_runs_once(self) -> None:
        submission = _sub(CLICK)
        self.assertEqual(prog.admit({}, submission)["action"], "run")
        lane = _lane_after_run(submission)
        again = prog.admit(lane, _sub(CLICK, request_id="save-02"))
        self.assertEqual(again["reason"], "write_once")

    def test_read_may_use_another_request_id(self) -> None:
        lane = _lane_after_run(_sub(READ))
        decision = prog.admit(lane, _sub(READ, request_id="save-02"))
        self.assertEqual(decision["action"], "run")

    def test_force_click_is_refused(self) -> None:
        program = CLICK.replace(".click()", ".click({force: true})")
        decision = prog.admit({}, _sub(program))
        self.assertEqual(decision["reason"], "force_click")

    def test_named_target_rejects_bare_coordinates(self) -> None:
        program = "await page.mouse.click(12, 40);\nawait expect(page.getByText('Saved')).toBeVisible();"
        decision = prog.admit({}, _sub(program))
        self.assertEqual(decision["reason"], "coordinate_for_named")

    def test_visual_target_allows_coordinates(self) -> None:
        program = "await page.mouse.click(12, 40);\nawait expect(page.getByText('Saved')).toBeVisible();"
        decision = prog.admit({}, _sub(program, target="visual"))
        self.assertEqual(decision["action"], "run")

    def test_other_task_does_not_see_the_receipt(self) -> None:
        lane = _lane_after_run(_sub(CLICK))
        other = _sub(CLICK)
        other["task"] = "other"
        self.assertEqual(prog.admit(lane, other)["action"], "run")

    def test_bad_request_id(self) -> None:
        decision = prog.admit({}, _sub(READ, request_id="has space"))
        self.assertEqual(decision["reason"], "request_id")

    def test_declared_mutation_without_assertion(self) -> None:
        decision = prog.admit({}, _sub(READ, mutates=True))
        self.assertEqual(decision["reason"], "assertion_required")


class ApplyTest(unittest.TestCase):
    def test_succeeded_is_not_business_ok(self) -> None:
        lane = _lane_after_run(_sub(CLICK))
        receipt = _sub(CLICK)
        receipt.update(status="succeeded", mutation="possible", verified=False, business_ok=False)
        result = prog.apply(lane, receipt)
        self.assertTrue(result["ok"])
        stored = result["lane"]["tasks"]["save-profile"]["save-01"]
        self.assertEqual(stored["status"], "succeeded")
        self.assertFalse(stored["business_ok"])

    def test_business_ok_requires_verified(self) -> None:
        receipt = _sub(CLICK)
        receipt.update(status="succeeded", mutation="possible", verified=False, business_ok=True)
        result = prog.apply({}, receipt)
        self.assertEqual(result["reason"], "business_unverified")
        self.assertEqual(result["lane"], {})

    def test_verified_business_ok_sticks(self) -> None:
        receipt = _sub(CLICK)
        receipt.update(status="succeeded", mutation="possible", verified=True, business_ok=True)
        result = prog.apply({}, receipt)
        stored = result["lane"]["tasks"]["save-profile"]["save-01"]
        self.assertTrue(stored["verified"])
        self.assertTrue(stored["business_ok"])

    def test_apply_rejects_a_different_program(self) -> None:
        lane = _lane_after_run(_sub(CLICK))
        receipt = _sub(CLICK + "\nreturn 1;")
        receipt.update(status="succeeded", mutation="none", verified=True, business_ok=True)
        result = prog.apply(lane, receipt)
        self.assertEqual(result["reason"], "new_id_required")


class CliTest(unittest.TestCase):
    def test_schema_and_round_trip(self) -> None:
        schema = subprocess.run(
            [sys.executable, str(SCRIPTS / "browser-program.py"), "--schema"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(schema.returncode, 0)
        self.assertIn("write_once", schema.stdout)
        self.assertIn("evaluate_click", schema.stdout)
        self.assertIn("claimed_tab", schema.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            lane = Path(tmp) / "lane.yaml"
            submission = textwrap.dedent(
                """\
                task: save-profile
                request_id: save-01
                program: |
                  await page.goto('https://example.test');
                  return await page.title();
                """
            )
            first = subprocess.run(
                [sys.executable, str(SCRIPTS / "browser-program.py"), "admit", "--lane", str(lane)],
                input=submission, check=False, capture_output=True, text=True,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("action: run", first.stdout)
            self.assertIn(prog.PASS_LINE, first.stdout)
            second = subprocess.run(
                [sys.executable, str(SCRIPTS / "browser-program.py"), "admit", "--lane", str(lane)],
                input=submission, check=False, capture_output=True, text=True,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("action: stored", second.stdout)
            broken = Path(tmp) / "broken.yaml"
            broken.write_text(":\n  -", encoding="utf-8")
            bad = subprocess.run(
                [sys.executable, str(SCRIPTS / "browser-program.py"), "admit", "--lane", str(broken)],
                input=submission, check=False, capture_output=True, text=True,
            )
            self.assertEqual(bad.returncode, 2)
            finish = subprocess.run(
                [sys.executable, str(SCRIPTS / "browser-program.py"), "admit", "--lane", str(lane)],
                input="op: finish\ntask: save-profile\n",
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(finish.returncode, 0, finish.stderr)
            self.assertIn("state: finished", finish.stdout)
            self.assertNotIn("lane:", finish.stdout)


class FullTest(unittest.TestCase):
    def test_evaluate_click_is_refused_and_a_later_locator_is_not(self) -> None:
        inside = "await page.evaluate(() => document.querySelector('button').click());"
        self.assertEqual(prog.admit({}, _sub(inside))["reason"], "evaluate_click")
        later = "const title = await page.evaluate(() => document.title);\n" + CLICK
        self.assertEqual(prog.admit({}, _sub(later))["action"], "run")

    def test_image_outside_and_parallel_writes(self) -> None:
        image = CLICK + "\nreturn await page.screenshot({ encoding: 'base64' });"
        self.assertEqual(prog.admit({}, _sub(image))["reason"], "inline_image")
        outside = "await chromium.launch();\n" + READ
        self.assertEqual(prog.admit({}, _sub(outside))["reason"], "outside_task")
        parallel = (
            "await Promise.all([page.getByRole('button', {name: 'Save'}).click()]);\n"
            "await expect(page.getByText('Saved')).toBeVisible();"
        )
        self.assertEqual(prog.admit({}, _sub(parallel))["reason"], "parallel_write")

    def test_foreground_is_refused(self) -> None:
        decision = prog.admit({}, _sub(READ, background=False))
        self.assertEqual(decision["reason"], "steals_focus")

    def test_unknown_outcome_cannot_count_as_done(self) -> None:
        receipt = _sub(CLICK)
        receipt.update(status="interrupted", mutation="unknown", verified=True, business_ok=True)
        self.assertEqual(prog.apply({}, receipt)["reason"], "outcome_unknown")

    def test_failure_needs_a_reason_and_a_wide_result_is_refused(self) -> None:
        failed = _sub(CLICK)
        failed.update(status="failed", mutation="none", verified=False, business_ok=False)
        self.assertEqual(prog.apply({}, failed)["reason"], "block_reason")
        wide = _sub(READ)
        wide.update(
            status="succeeded", mutation="none", verified=True, business_ok=True,
            result="x" * (prog.INLINE_CAP + 1),
        )
        self.assertEqual(prog.apply({}, wide)["reason"], "unreduced_result")

    def test_errors_carry_into_the_next_program(self) -> None:
        receipt = _sub(CLICK)
        receipt.update(
            status="failed", mutation="possible", verified=False, business_ok=False,
            errors=["HTTP 504"],
        )
        lane = prog.apply(_lane_after_run(_sub(CLICK)), receipt)["lane"]
        nxt = prog.admit(lane, _sub(READ, request_id="save-02"))
        self.assertEqual(nxt["receipt"]["carried_errors"], ["HTTP 504"])

    def test_inspect_claim_and_discard(self) -> None:
        lane = _lane_after_run(_sub(READ))
        seen = prog.admit(lane, {"op": "inspect", "task": "save-profile", "request_id": "save-01"})
        self.assertEqual(seen["action"], "stored")
        missing = prog.admit(lane, {"op": "inspect", "task": "save-profile", "request_id": "nope"})
        self.assertEqual(missing["reason"], "missing")
        claimed = prog.admit(lane, {"op": "claim", "task": "save-profile", "tab_ids": ["tab-1"]})
        blocked = prog.admit(claimed["lane"], {"op": "discard", "task": "save-profile", "tabs": ["tab-1"]})
        self.assertEqual(blocked["reason"], "claimed_tab")
        done = prog.admit(claimed["lane"], {"op": "discard", "task": "save-profile", "tabs": ["session-1"]})
        self.assertEqual(done["receipt"]["state"], "discarded")
        self.assertEqual(done["receipt"]["claimed"], ["tab-1"])
        self.assertEqual(done["receipt"]["closed"], ["session-1"])

    def test_ninth_open_task_waits_until_one_is_discarded(self) -> None:
        lane: dict = {}
        for index in range(prog.ACTIVE_LIMIT):
            decision = prog.admit(lane, _sub(READ, request_id="read-01", task=f"task-{index}"))
            self.assertEqual(decision["action"], "run")
            lane = prog.put(lane, decision["receipt"])
        blocked = prog.admit(lane, _sub(READ, request_id="read-01", task="task-extra"))
        self.assertEqual(blocked["reason"], "task_limit")
        lane = prog.admit(lane, {"op": "discard", "task": "task-0", "tabs": []})["lane"]
        opened = prog.admit(lane, _sub(READ, request_id="read-01", task="task-extra"))
        self.assertEqual(opened["action"], "run")

    def test_negative_duration_is_refused(self) -> None:
        receipt = _sub(READ)
        receipt.update(status="succeeded", mutation="none", verified=True, business_ok=True, duration_ms=-1)
        self.assertEqual(prog.apply({}, receipt)["reason"], "duration_ms")


class AdviseTest(unittest.TestCase):
    def test_running_waits_and_unknown_stays_on_the_old_request(self) -> None:
        waiting = prog.advise({"status": "running", "mutation": "none"})
        self.assertEqual(waiting["action"], "wait")
        unknown = prog.advise({"status": "interrupted", "mutation": "possible"})
        self.assertEqual(unknown["action"], "probe")
        self.assertEqual(unknown["why"], "outcome_unknown")
        self.assertIn("原请求号", unknown["do"])

    def test_strict_mode_tightens_until_a_change_might_have_landed(self) -> None:
        missed = {"status": "failed", "mutation": "none", "errors": ["strict mode violation: resolved to 2 elements"]}
        self.assertEqual(prog.advise(missed)["action"], "tighten")
        landed = dict(missed, mutation="possible")
        self.assertEqual(prog.advise(landed)["why"], "mutation_possible")

    def test_overlay_late_error_and_unfinished_save(self) -> None:
        overlay = {"status": "failed", "mutation": "none", "block_reason": "subtree intercepts pointer events"}
        self.assertEqual(prog.advise(overlay)["action"], "unblock")
        late = {
            "status": "succeeded", "mutation": "none", "verified": True, "business_ok": True,
            "carried_errors": ["HTTP 504"],
        }
        self.assertEqual(prog.advise(late)["action"], "late")
        saving = {"status": "succeeded", "mutation": "possible", "verified": False, "business_ok": False}
        self.assertEqual(prog.advise(saving)["why"], "not_done")

    def test_verified_continues_and_a_bare_failure_holds(self) -> None:
        done = {"status": "succeeded", "mutation": "possible", "verified": True, "business_ok": True}
        self.assertEqual(prog.advise(done)["action"], "continue")
        bare = {"status": "failed", "mutation": "none", "errors": ["HTTP 500"]}
        advice = prog.advise(bare)
        self.assertEqual(advice["action"], "hold")
        carried = dict(bare, carried_errors=["HTTP 504"])
        self.assertEqual(prog.advise(carried)["also"], "carried_errors")

    def test_unverified_business_ok_and_a_long_error_are_refused(self) -> None:
        bad = {"status": "succeeded", "mutation": "none", "verified": False, "business_ok": True}
        self.assertEqual(prog.advise(bad)["reason"], "business_unverified")
        receipt = _sub(CLICK)
        receipt.update(status="failed", mutation="none", errors=["e" * (prog.INLINE_CAP + 1)])
        self.assertEqual(prog.apply({}, receipt)["reason"], "unreduced_result")

    def test_advise_cli_does_not_print_pass(self) -> None:
        done = subprocess.run(
            [sys.executable, str(SCRIPTS / "browser-program.py"), "advise"],
            input="status: queued\nmutation: none\n",
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("action: wait", done.stdout)
        self.assertNotIn("PASS", done.stdout)


class SceneTest(unittest.TestCase):
    def test_a_failure_without_page_changes_is_not_a_scene(self) -> None:
        receipt = {"status": "failed", "mutation": "none", "errors": ["strict mode violation"]}
        report = prog.scene(receipt)
        self.assertIn("page_changes", report["gaps"])
        self.assertFalse(report["ready"])
        receipt["page_changes"] = []
        self.assertTrue(prog.scene(receipt)["ready"])

    def test_screenshot_is_a_file_path(self) -> None:
        receipt = _sub(CLICK)
        receipt.update(
            status="failed", mutation="none", errors=["遮罩"],
            page_changes=[], screenshot="data:image/png;base64,aaaa",
        )
        self.assertEqual(prog.apply({}, receipt)["reason"], "screenshot")
        receipt["screenshot"] = "state/shot.png"
        stored = prog.apply({}, receipt)
        self.assertTrue(stored["ok"])
        body = stored["lane"]["tasks"]["save-profile"]["save-01"]
        self.assertEqual(body["screenshot"], "state/shot.png")


class DepthTest(unittest.TestCase):
    def test_listener_after_the_action_and_a_page_without_finally(self) -> None:
        late = CLICK + "\npage.on('dialog', dialog => dialog.accept());"
        self.assertEqual(prog.admit({}, _sub(late))["reason"], "listen_late")
        early = "page.on('dialog', dialog => dialog.accept());\n" + CLICK
        self.assertEqual(prog.admit({}, _sub(early))["action"], "run")
        opened = "const page2 = await context.newPage();\n" + READ
        self.assertEqual(prog.admit({}, _sub(opened))["reason"], "page_left_open")
        closed = "try { const page2 = await context.newPage(); } finally { await page2.close(); }\n" + READ
        self.assertEqual(prog.admit({}, _sub(closed))["action"], "run")

    def test_an_index_is_not_how_you_recover_an_ambiguous_click(self) -> None:
        failed = _sub(CLICK)
        failed.update(status="failed", mutation="none", errors=["strict mode violation: resolved to 2 elements"])
        lane = prog.apply(_lane_after_run(_sub(CLICK)), failed)["lane"]
        nth = (
            "await page.getByRole('button', {name: 'Save'}).nth(0).click();\n"
            "await expect(page.getByText('Saved')).toBeVisible();"
        )
        self.assertEqual(prog.admit(lane, _sub(nth, request_id="save-02"))["reason"], "position_retry")
        exact = (
            "await page.getByRole('button', {name: 'Save', exact: true}).click();\n"
            "await expect(page.getByText('Saved')).toBeVisible();"
        )
        self.assertEqual(prog.admit(lane, _sub(exact, request_id="save-02"))["action"], "run")

    def test_a_later_write_keeps_the_same_idempotency_key(self) -> None:
        lane = _lane_after_run(_sub(CLICK, idempotency_key="order-1"))
        other = CLICK.replace("Save", "Send")
        missing = prog.admit(lane, _sub(other, request_id="save-02"))
        self.assertEqual(missing["reason"], "idempotency_key")
        kept = prog.admit(lane, _sub(other, request_id="save-02", idempotency_key="order-1"))
        self.assertEqual(kept["action"], "run")
        done = _sub(CLICK)
        done.update(status="succeeded", mutation="possible", verified=True, business_ok=True)
        stored = prog.apply(lane, done)["lane"]
        body = stored["tasks"]["save-profile"]["save-01"]
        self.assertEqual(body["idempotency_key"], "order-1")

    def test_a_long_error_must_lift_out_the_blocker(self) -> None:
        receipt = _sub(CLICK)
        receipt.update(status="failed", mutation="none", errors=["e" * (prog.lane.REASON_CAP + 1)])
        self.assertEqual(prog.apply({}, receipt)["reason"], "block_reason")
        receipt["block_reason"] = "遮罩"
        self.assertTrue(prog.apply({}, receipt)["ok"])

    def test_tally_keeps_false_success_apart_from_unknown(self) -> None:
        saved = _sub(READ)
        saved.update(status="succeeded", mutation="none", verified=False, business_ok=False)
        lane = prog.apply(_lane_after_run(_sub(READ)), saved)["lane"]
        lost = _sub(READ, request_id="save-02")
        lost.update(status="interrupted", mutation="unknown", verified=False, business_ok=False)
        lane = prog.apply(lane, lost)["lane"]
        counts = prog.tally(lane)
        self.assertEqual(counts["false_success"], 1)
        self.assertEqual(counts["unknown"], 1)
        self.assertEqual(counts["verified"], 0)


if __name__ == "__main__":
    unittest.main()
