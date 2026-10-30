#!/usr/bin/env python3
"""Next step from one browser receipt. No browser, no replay."""
from __future__ import annotations

import re

from browser_lane import INLINE_CAP, INLINE_IMAGE, MUTATIONS, STATUSES, flag, outcome_of, text_list
from browser_shape import AMBIGUOUS

BLOCKER = re.compile(r"intercepts pointer|not actionable|overlay|遮罩", re.I)

DO = {
    "wait": "用同一任务和请求号 inspect，取回这条回执。",
    "probe": "另交一段只读程序，核对页面现在停在哪。会改页面的操作留在原请求号上，核对之后从当前页继续。",
    "late": "先核对上一段改动的业务结果，再决定下一段。",
    "tighten": "下一段把定位收进预期区域。请求号用新的，程序文本要变。",
    "unblock": "下一段先处理挡住点击的那一层，再点真正的控件。请求号用新的。",
    "continue": "这段已经核对过。下一步需要新判断时再另交一段。",
    "hold": "先读 block_reason 和 errors，再交一段文本不同的程序。",
}


def advise_problem(receipt: dict) -> str:
    if not isinstance(receipt, dict):
        return "receipt"
    status = str(receipt.get("status") or "")
    mutation = str(receipt.get("mutation") or "none")
    if status not in STATUSES:
        return "status"
    if mutation not in MUTATIONS:
        return "mutation"
    if flag(receipt.get("business_ok")) and not flag(receipt.get("verified")):
        return "business_unverified"
    if flag(receipt.get("business_ok")) and outcome_of(status, mutation) == "unknown":
        return "outcome_unknown"
    return ""


def blob(receipt: dict) -> str:
    parts = text_list(receipt.get("errors"))
    reason = str(receipt.get("block_reason") or "").strip()
    if reason:
        parts.append(reason)
    return "\n".join(parts)


def still_running(receipt: dict) -> bool:
    return str(receipt.get("status")) in ("queued", "running")


def unknown_outcome(receipt: dict) -> bool:
    status = str(receipt.get("status"))
    mutation = str(receipt.get("mutation") or "none")
    return outcome_of(status, mutation) == "unknown"


def late_error(receipt: dict) -> bool:
    if str(receipt.get("status")) != "succeeded":
        return False
    return bool(text_list(receipt.get("carried_errors")))


def maybe_changed(receipt: dict) -> bool:
    if str(receipt.get("status")) != "failed":
        return False
    return str(receipt.get("mutation") or "none") == "possible"


def ambiguous(receipt: dict) -> bool:
    if str(receipt.get("status")) != "failed":
        return False
    return AMBIGUOUS.search(blob(receipt)) is not None


def blocked(receipt: dict) -> bool:
    if str(receipt.get("status")) != "failed":
        return False
    return BLOCKER.search(blob(receipt)) is not None


def not_done(receipt: dict) -> bool:
    if str(receipt.get("status")) != "succeeded":
        return False
    return not flag(receipt.get("business_ok"))


def done(receipt: dict) -> bool:
    if str(receipt.get("status")) != "succeeded":
        return False
    return flag(receipt.get("business_ok")) and flag(receipt.get("verified"))


def failed_open(receipt: dict) -> bool:
    return str(receipt.get("status")) == "failed"


RULES = (
    (still_running, "wait", "running"),
    (unknown_outcome, "probe", "outcome_unknown"),
    (late_error, "late", "carried_errors"),
    (maybe_changed, "probe", "mutation_possible"),
    (ambiguous, "tighten", "ambiguous_locator"),
    (blocked, "unblock", "blocked_target"),
    (not_done, "probe", "not_done"),
    (done, "continue", "verified"),
    (failed_open, "hold", "unclassified"),
)


def classify(receipt: dict) -> tuple[str, str]:
    for check, action, why in RULES:
        if check(receipt):
            return action, why
    return "hold", "unclassified"


def advise(receipt: dict) -> dict:
    problem = advise_problem(receipt)
    if problem:
        return {"action": "reject", "reason": problem, "do": ""}
    action, why = classify(receipt)
    body = {"action": action, "why": why, "do": DO[action]}
    if action != "late" and text_list(receipt.get("carried_errors")):
        body["also"] = "carried_errors"
    return body


KEEP = (
    "task", "request_id", "status", "mutation", "outcome",
    "block_reason", "errors", "page_changes", "carried_errors",
    "screenshot", "duration_ms",
)


def scene_gaps(receipt: dict) -> list[str]:
    gaps = []
    if str(receipt.get("status") or "") not in STATUSES:
        gaps.append("status")
    if str(receipt.get("mutation") or "") not in MUTATIONS:
        gaps.append("mutation")
    failed = str(receipt.get("status")) == "failed"
    reason = str(receipt.get("block_reason") or "").strip()
    if failed and not text_list(receipt.get("errors")) and not reason:
        gaps.append("block_reason")
    if "page_changes" not in receipt:
        gaps.append("page_changes")
    return gaps


def shot_gap(receipt: dict) -> str:
    if "screenshot" not in receipt:
        return ""
    text = receipt.get("screenshot")
    if not isinstance(text, str) or not text.strip():
        return "screenshot"
    if INLINE_IMAGE.search(text) or len(text) > INLINE_CAP:
        return "screenshot"
    return ""


def scene(receipt: dict) -> dict:
    if not isinstance(receipt, dict):
        return {"ready": False, "gaps": ["receipt"], "keep": list(KEEP)}
    gaps = scene_gaps(receipt)
    shot = shot_gap(receipt)
    if shot:
        gaps.append(shot)
    return {"ready": not gaps, "gaps": gaps, "keep": list(KEEP)}
