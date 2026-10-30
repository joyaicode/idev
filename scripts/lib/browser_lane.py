#!/usr/bin/env python3
"""Receipt lane for browser programs. No browser."""
from __future__ import annotations

from browser_history import history_problem, keep_key
from browser_shape import (
    INLINE_IMAGE,
    REQUEST,
    changes_page,
    digest,
    field_problem,
    flag,
    reject,
    shape_problem,
    steals_focus,
)

STATUSES = ("queued", "running", "succeeded", "failed", "interrupted")
MUTATIONS = ("none", "possible", "unknown")
OPS = ("run", "inspect", "finish", "discard", "claim")
META = "_meta"
ACTIVE_LIMIT = 8
INLINE_CAP = 4096
REASON_CAP = 180


def open_count(lane: dict) -> int:
    tasks = lane.get("tasks") if isinstance(lane, dict) else None
    if not isinstance(tasks, dict):
        return 0
    count = 0
    for body in tasks.values():
        meta = body.get(META) if isinstance(body, dict) else None
        state = meta.get("state") if isinstance(meta, dict) else "open"
        if state != "discarded":
            count += 1
    return count


def room_for(lane: dict, task: str) -> str:
    if task_map(lane, task):
        return ""
    if open_count(lane) >= ACTIVE_LIMIT:
        return "task_limit"
    return ""


def task_map(lane: dict, task: str) -> dict:
    tasks = lane.get("tasks") if isinstance(lane, dict) else None
    if not isinstance(tasks, dict):
        return {}
    found = tasks.get(task)
    return found if isinstance(found, dict) else {}


def same_request(prior: dict, program: str) -> dict:
    if prior.get("program_sha256") != digest(program):
        return reject("new_id_required")
    return {"action": "stored", "reason": "", "receipt": prior}


def digest_present(receipts: dict, program: str) -> bool:
    want = digest(program)
    for key, item in receipts.items():
        if key == META or not isinstance(item, dict):
            continue
        if item.get("program_sha256") == want:
            return True
    return False


def latest_errors(receipts: dict) -> list:
    carried: list = []
    for key, item in receipts.items():
        if key == META or not isinstance(item, dict) or not item.get("errors"):
            continue
        carried = [str(text) for text in item["errors"] if str(text).strip()]
    return carried


def queued(submission: dict, carried: list) -> dict:
    body = {
        "task": str(submission["task"]),
        "request_id": str(submission["request_id"]),
        "program_sha256": digest(str(submission["program"])),
        "status": "queued",
        "mutation": "none",
        "verified": False,
        "business_ok": False,
        "outcome": "known",
    }
    if carried:
        body["carried_errors"] = carried
    key = str(submission.get("idempotency_key") or "").strip()
    changing = changes_page(str(submission["program"]), flag(submission.get("mutates")))
    if key and changing:
        body["idempotency_key"] = key
    return body


def prepared(submission: dict) -> dict:
    problem = field_problem(submission)
    if problem:
        return reject(problem)
    if steals_focus(submission):
        return reject("steals_focus")
    program = str(submission["program"])
    target = str(submission.get("target") or "named")
    changing = changes_page(program, flag(submission.get("mutates")))
    problem = shape_problem(program, changing, target)
    if problem:
        return reject(problem)
    return {"program": program, "changing": changing}


def admit_run(lane: dict, submission: dict) -> dict:
    ready = prepared(submission)
    if ready.get("action") == "reject":
        return ready
    task = str(submission["task"])
    problem = room_for(lane, task)
    if problem:
        return reject(problem)
    receipts = task_map(lane, task)
    program = ready["program"]
    prior = receipts.get(str(submission["request_id"]))
    if isinstance(prior, dict) and prior.get("program_sha256"):
        return same_request(prior, program)
    problem = history_problem(receipts, submission, ready)
    if problem:
        return reject(problem)
    if ready["changing"] and digest_present(receipts, program):
        return reject("write_once")
    carried = latest_errors(receipts)
    return {"action": "run", "reason": "", "receipt": queued(submission, carried)}


def inspect_receipt(lane: dict, submission: dict) -> dict:
    task = str(submission.get("task") or "").strip()
    if not task:
        return reject("task_required")
    if REQUEST.match(str(submission.get("request_id") or "")) is None:
        return reject("request_id")
    prior = task_map(lane, task).get(str(submission["request_id"]))
    if not isinstance(prior, dict) or not prior.get("program_sha256"):
        return reject("missing")
    return {"action": "stored", "reason": "", "receipt": prior}


def hits_claimed(claimed: list, closing: list) -> bool:
    owned = {str(item) for item in claimed}
    return any(str(item) in owned for item in closing)


def finish_task(lane: dict, submission: dict, keep: bool) -> dict:
    task = str(submission.get("task") or "").strip()
    if not task:
        return reject("task_required")
    if not task_map(lane, task):
        return reject("missing")
    closing = submission.get("tabs") or []
    if not isinstance(closing, list):
        return reject("tabs")
    body = dict(task_map(lane, task))
    meta = dict(body.get(META) or {})
    claimed = [str(item) for item in meta.get("claimed") or []]
    if not keep and hits_claimed(claimed, closing):
        return reject("claimed_tab")
    meta["state"] = "finished" if keep else "discarded"
    meta["claimed"] = claimed
    if not keep:
        meta["closed"] = [str(item) for item in closing]
    body[META] = meta
    return {"action": "stored", "reason": "", "receipt": meta, "lane": put_body(lane, task, body)}


def merge_ids(existing: list, extra: list) -> list:
    claimed = [str(item) for item in existing]
    for item in extra:
        text = str(item).strip()
        if text and text not in claimed:
            claimed.append(text)
    return claimed


def claim_tabs(lane: dict, submission: dict) -> dict:
    task = str(submission.get("task") or "").strip()
    if not task:
        return reject("task_required")
    ids = submission.get("tab_ids")
    if not isinstance(ids, list) or not merge_ids([], ids):
        return reject("tab_ids")
    if room_for(lane, task):
        return reject("task_limit")
    body = dict(task_map(lane, task))
    meta = dict(body.get(META) or {})
    meta["claimed"] = merge_ids(meta.get("claimed") or [], ids)
    meta.setdefault("state", "open")
    body[META] = meta
    shown = {"claimed": meta["claimed"]}
    return {"action": "stored", "reason": "", "receipt": shown, "lane": put_body(lane, task, body)}


def admit(lane: dict, submission: dict) -> dict:
    op = str(submission.get("op") or "run")
    if op not in OPS:
        return reject("op")
    if op == "inspect":
        return inspect_receipt(lane, submission)
    if op == "finish":
        return finish_task(lane, submission, True)
    if op == "discard":
        return finish_task(lane, submission, False)
    if op == "claim":
        return claim_tabs(lane, submission)
    return admit_run(lane, submission)


def outcome_of(status: str, mutation: str) -> str:
    if status == "interrupted" or mutation == "unknown":
        return "unknown"
    return "known"


def text_list(value: object) -> list:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def stored_receipt(receipt: dict) -> dict:
    status = str(receipt["status"])
    mutation = str(receipt["mutation"])
    body = {
        "task": str(receipt["task"]),
        "request_id": str(receipt["request_id"]),
        "program_sha256": digest(str(receipt["program"])),
        "status": status,
        "mutation": mutation,
        "verified": flag(receipt.get("verified")),
        "business_ok": flag(receipt.get("business_ok")),
        "outcome": outcome_of(status, mutation),
        "errors": text_list(receipt.get("errors")),
        "page_changes": text_list(receipt.get("page_changes")),
    }
    return with_optional(body, receipt)


def with_optional(body: dict, receipt: dict) -> dict:
    if receipt.get("duration_ms") is not None:
        body["duration_ms"] = receipt["duration_ms"]
    reason = str(receipt.get("block_reason") or "").strip()
    if reason:
        body["block_reason"] = reason
    carried = text_list(receipt.get("carried_errors"))
    if carried:
        body["carried_errors"] = carried
    key = str(receipt.get("idempotency_key") or "").strip()
    if key:
        body["idempotency_key"] = key
    if "result" in receipt:
        body["result"] = receipt["result"]
    shot = str(receipt.get("screenshot") or "").strip()
    if shot:
        body["screenshot"] = shot
    return body


def duration_problem(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return "duration_ms"
    return ""


def list_problem(receipt: dict) -> str:
    for name in ("errors", "page_changes"):
        value = receipt.get(name)
        if value is not None and not isinstance(value, list):
            return name
    return ""


def wide(value: object) -> bool:
    if isinstance(value, str):
        return len(value) > INLINE_CAP
    if isinstance(value, dict):
        return any(wide(item) for item in value.values())
    if isinstance(value, list):
        return any(wide(item) for item in value)
    return False


def image_result(value: object) -> bool:
    if isinstance(value, str):
        return INLINE_IMAGE.search(value) is not None
    if isinstance(value, dict):
        return any(image_result(item) for item in value.values())
    if isinstance(value, list):
        return any(image_result(item) for item in value)
    return False


def failed_reason(receipt: dict) -> str:
    if receipt.get("status") != "failed":
        return ""
    if str(receipt.get("block_reason") or "").strip():
        return ""
    if buried(receipt.get("errors")):
        return "block_reason"
    if receipt.get("errors"):
        return ""
    return "block_reason"


def buried(errors: object) -> bool:
    return any(len(item) > REASON_CAP for item in text_list(errors))


def receipt_extra(receipt: dict) -> str:
    status = str(receipt.get("status") or "")
    mutation = str(receipt.get("mutation") or "")
    if flag(receipt.get("business_ok")) and outcome_of(status, mutation) == "unknown":
        return "outcome_unknown"
    problem = duration_problem(receipt.get("duration_ms"))
    if problem:
        return problem
    problem = list_problem(receipt) or result_problem(receipt) or shot_problem(receipt.get("screenshot"))
    if problem:
        return problem
    return failed_reason(receipt)


def shot_problem(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or not value.strip():
        return "screenshot"
    if INLINE_IMAGE.search(value) or len(value) > INLINE_CAP:
        return "screenshot"
    return ""


def result_problem(receipt: dict) -> str:
    for name in ("result", "errors", "page_changes"):
        if image_result(receipt.get(name)):
            return "inline_image"
        if wide(receipt.get(name)):
            return "unreduced_result"
    return ""


def receipt_problem(receipt: dict) -> str:
    problem = field_problem(receipt)
    if problem:
        return problem
    if receipt.get("status") not in STATUSES:
        return "status"
    if receipt.get("mutation") not in MUTATIONS:
        return "mutation"
    if flag(receipt.get("business_ok")) and not flag(receipt.get("verified")):
        return "business_unverified"
    return receipt_extra(receipt)


def put(lane: dict, receipt: dict) -> dict:
    task = receipt["task"]
    request_id = receipt["request_id"]
    tasks = dict(lane.get("tasks") or {})
    current = dict(tasks.get(task) or {})
    current[request_id] = receipt
    tasks[task] = current
    return {"tasks": tasks}


def put_body(lane: dict, task: str, body: dict) -> dict:
    tasks = dict(lane.get("tasks") or {})
    tasks[task] = body
    return {"tasks": tasks}


def apply(lane: dict, receipt: dict) -> dict:
    problem = receipt_problem(receipt)
    if problem:
        return {"ok": False, "reason": problem, "lane": lane}
    task = str(receipt["task"])
    request_id = str(receipt["request_id"])
    prior = task_map(lane, task).get(request_id)
    program = str(receipt["program"])
    if isinstance(prior, dict) and prior.get("program_sha256") != digest(program):
        return {"ok": False, "reason": "new_id_required", "lane": lane}
    stored = keep_key(stored_receipt(receipt), prior)
    return {"ok": True, "reason": "", "lane": put(lane, stored)}
