#!/usr/bin/env python3
"""What the receipts already stored say about the next program."""
from __future__ import annotations

from browser_shape import AMBIGUOUS, POSITION, REQUEST, flag

META = "_meta"


def history_problem(receipts: dict, submission: dict, ready: dict) -> str:
    program = ready["program"]
    changing = ready["changing"]
    hit = position_problem(receipts, program, changing)
    if hit:
        return hit
    return key_problem(submission, receipts, changing)


def position_problem(receipts: dict, program: str, changing: bool) -> str:
    if not changing or POSITION.search(program) is None:
        return ""
    if AMBIGUOUS.search(blob(last_receipt(receipts))):
        return "position_retry"
    return ""


def key_problem(submission: dict, receipts: dict, changing: bool) -> str:
    sent = str(submission.get("idempotency_key") or "").strip()
    if sent and REQUEST.match(sent) is None:
        return "idempotency_key"
    if not changing:
        return ""
    prior = stored_key(receipts)
    if prior and sent != prior:
        return "idempotency_key"
    return ""


def last_receipt(receipts: dict) -> dict:
    found: dict = {}
    for key, item in receipts.items():
        if key == META or not isinstance(item, dict) or not item.get("program_sha256"):
            continue
        found = item
    return found


def blob(item: dict) -> str:
    parts = [str(text) for text in item.get("errors") or [] if str(text).strip()]
    reason = str(item.get("block_reason") or "").strip()
    if reason:
        parts.append(reason)
    return "\n".join(parts)


def stored_key(receipts: dict) -> str:
    found = ""
    for key, item in receipts.items():
        if key == META or not isinstance(item, dict):
            continue
        text = str(item.get("idempotency_key") or "").strip()
        if text:
            found = text
    return found


def keep_key(stored: dict, prior: object) -> dict:
    if stored.get("idempotency_key"):
        return stored
    if isinstance(prior, dict) and prior.get("idempotency_key"):
        body = dict(stored)
        body["idempotency_key"] = prior["idempotency_key"]
        return body
    return stored


def tally(lane: dict) -> dict:
    counts = {"false_success": 0, "unknown": 0, "failed": 0, "verified": 0}
    tasks = lane.get("tasks") if isinstance(lane, dict) else None
    if not isinstance(tasks, dict):
        return counts
    for body in tasks.values():
        add_task(counts, body)
    return counts


def add_task(counts: dict, body: object) -> None:
    if not isinstance(body, dict):
        return
    for key, item in body.items():
        if key == META or not isinstance(item, dict):
            continue
        add_receipt(counts, item)


def add_receipt(counts: dict, item: dict) -> None:
    status = str(item.get("status") or "")
    mutation = str(item.get("mutation") or "")
    if status == "interrupted" or mutation == "unknown" or item.get("outcome") == "unknown":
        counts["unknown"] += 1
        return
    if status == "failed":
        counts["failed"] += 1
        return
    if status != "succeeded":
        return
    if flag(item.get("business_ok")) and flag(item.get("verified")):
        counts["verified"] += 1
        return
    counts["false_success"] += 1
