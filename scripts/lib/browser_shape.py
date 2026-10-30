#!/usr/bin/env python3
"""Shape checks for one browser program. No browser."""
from __future__ import annotations

import hashlib
import re

TARGETS = ("named", "visual")
REQUEST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
FORCE = re.compile(r"force\s*:\s*true", re.I)
MOUSE = re.compile(r"mouse\s*\.\s*click\s*\(|click\s*\(\s*\d+\s*,\s*\d+")
ASSERT = re.compile(r"\bexpect\s*\(|\bassert\b")
WRITE = re.compile(
    r"\.(?:click|dblclick|fill|press|type|check|uncheck|selectOption|setInputFiles)\s*\("
    r"|mouse\s*\.\s*(?:click|down|up)\s*\("
)
INLINE_IMAGE = re.compile(r"data:image/|encoding\s*:\s*['\"]base64['\"]", re.I)
OUTSIDE = re.compile(
    r"connectOverCDP|remote-debugging-port|browser\.close\s*\(|chromium\.launch\s*\("
)
PARALLEL = re.compile(r"Promise\.all\s*\(")
AMBIGUOUS = re.compile(
    r"strict mode|resolved to \d+ elements|matches \d+ elements|多个",
    re.I,
)
POSITION = re.compile(r"\.nth\s*\(|\.first\s*\(")
LISTEN = re.compile(r"page\.on\s*\(|waitForEvent\s*\(")
NEWPAGE = re.compile(r"\.newPage\s*\(")


def digest(program: str) -> str:
    return hashlib.sha256(program.encode("utf-8")).hexdigest()


def reject(reason: str) -> dict:
    return {"action": "reject", "reason": reason, "receipt": None}


def flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return False


def field_problem(body: dict) -> str:
    if not str(body.get("task") or "").strip():
        return "task_required"
    if REQUEST.match(str(body.get("request_id") or "")) is None:
        return "request_id"
    if not str(body.get("program") or "").strip():
        return "program_required"
    target = body.get("target") or "named"
    if target not in TARGETS:
        return "target"
    return ""


def changes_page(program: str, declared: bool) -> bool:
    return declared or WRITE.search(program) is not None


def evaluate_click(program: str) -> bool:
    for match in re.finditer(r"evaluate\s*\(", program, re.I):
        window = program[match.end():match.end() + 240]
        click = window.find(".click(")
        if click < 0 or re.search(r"getBy|\.locator\s*\(", window[:click]):
            continue
        return True
    return False


def shape_problem(program: str, changing: bool, target: str) -> str:
    if FORCE.search(program):
        return "force_click"
    if evaluate_click(program):
        return "evaluate_click"
    if INLINE_IMAGE.search(program):
        return "inline_image"
    if OUTSIDE.search(program):
        return "outside_task"
    if target == "named" and MOUSE.search(program):
        return "coordinate_for_named"
    if changing and PARALLEL.search(program):
        return "parallel_write"
    if changing and ASSERT.search(program) is None:
        return "assertion_required"
    if listen_late(program):
        return "listen_late"
    if page_left_open(program):
        return "page_left_open"
    return ""


def listen_late(program: str) -> bool:
    heard = LISTEN.search(program)
    wrote = WRITE.search(program)
    if heard is None or wrote is None:
        return False
    return wrote.start() < heard.start()


def page_left_open(program: str) -> bool:
    if NEWPAGE.search(program) is None:
        return False
    return re.search(r"\bfinally\b", program) is None


def steals_focus(submission: dict) -> bool:
    if submission.get("background") is False:
        return True
    if str(submission.get("background") or "").strip().lower() == "false":
        return True
    return flag(submission.get("foreground"))
