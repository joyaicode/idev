#!/usr/bin/env python3
"""Workflow syntax (schema_version 1) as code.

references/workflow-schema.md is the prose. This module is the same contract
for tools: workflow-check validates with it, workflow.py drives runs with it.
selfcheck keeps the kind table in the prose equal to KINDS here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# kind -> where the agent goes to execute it (the "落到" column).
KINDS: dict[str, str] = {
    "preflight.inputs": "scripts/s8-preflight.sh",
    "route.s4": "conventions/SKILL.md",
    "deliver.advance": "deliver/SKILL.md",
    "deliver.code_pass": "deliver/SKILL.md",
    "review.report": "conventions/coding.md",
    "review.fix": "conventions/coding.md",
    "verify.plan": "verify/SKILL.md",
    "verify.run": "verify/SKILL.md",
    "docs.backfill": "docs/SKILL.md",
    "docs.changelog": "docs/SKILL.md",
    "ops.classify": "ops/SKILL.md",
    "human.gate": "references/chat-confirm-signoff.md",
    "shell.confirmed": "-",
    "localdev.start": "workflow-defaults.yaml commands.start",
    "localdev.approval_off": "workflow-defaults.yaml commands.approval_off",
    "localdev.stop": "workflow-defaults.yaml commands.stop",
    "ui.lifecycle_run": "workflow-defaults.yaml commands.lifecycle",
    "ui.surface_scan": "scripts/ui-surface-scan.py",
    "ui.playbook_sync": "conventions/coding.md",
    "ui.coverage_lock": "scripts/ui-coverage-check.py",
    "ui.fix_deposit": "conventions/evidence.md",
    "ui.clean_pass_loop": "-",
    "ui.product_batch": "-",
    "git.replace_check": "-",
    "frontend.lint_fix": "workflow-defaults.yaml commands.lint_fix",
    "java.build": "-",
    "git.sensitive_shield": "references/workflow-repo-commit.md",
    "git.sensitive_restore": "references/workflow-repo-commit.md",
    "git.commit_push": "references/workflow-repo-commit.md",
}
LEGACY_KINDS = {"ui.product_batch"}
FORBIDDEN = {"auto.seal", "auto.accepted", "skip.signoff", "multi.module.load"}

TOP_FIELDS = {
    "schema_version", "id", "aliases", "summary", "doc", "risk_tier",
    "needs_ticket", "params", "policy", "steps", "roles", "rules",
}
PARAM_FIELDS = {"name", "required", "from", "default", "product_key"}
PARAM_FROM = {"user", "deliver.yaml", "default", "product"}
STEP_FIELDS = {"id", "kind", "label", "with"}
RISK_TIERS = {"P0", "P1", "P2"}
POLICY: dict[str, Any] = {
    "on_fail": {"stop", "ask"},
    "on_gate": {"stop"},
    "on_case_fail": {"stop_fix_continue"},
    "require_clean_pass": bool,
    "max_clean_attempts": int,
}

RUN_STATUS = {"pending", "running", "blocked", "done", "aborted"}
STEP_STATUS = {"PASS", "FAIL", "UNPROVEN", "SKIPPED", "BLOCKED"}
STEP_DONE = {"PASS", "SKIPPED", "UNPROVEN"}
STEP_STOP = {"FAIL", "BLOCKED"}

CONFIRM_WORDS = ("确认", "全签", "同意", "lgtm")
AGENT_NAMES = {"agent", "ai", "cursor", "assistant"}


def check_recipe(data: Any, path: Path, errors: list[str]) -> None:
    if not isinstance(data, dict):
        errors.append(f"{path}: not a mapping")
        return
    for key in sorted(set(data) - TOP_FIELDS):
        errors.append(f"{path}: unknown top-level field {key!r}")
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{path}: schema_version must be {SCHEMA_VERSION}")
    wid = data.get("id")
    if not wid or not isinstance(wid, str):
        errors.append(f"{path}: missing id")
    elif path.stem != wid:
        errors.append(f"{path}: id {wid!r} != filename stem {path.stem!r}")
    aliases = data.get("aliases")
    if aliases is not None and (
        not isinstance(aliases, list) or not all(isinstance(a, str) and a for a in aliases)
    ):
        errors.append(f"{path}: aliases must be a list of non-empty strings")
    if "risk_tier" in data and data["risk_tier"] not in RISK_TIERS:
        errors.append(f"{path}: risk_tier must be one of {sorted(RISK_TIERS)}")
    if "needs_ticket" in data and not isinstance(data["needs_ticket"], bool):
        errors.append(f"{path}: needs_ticket must be true or false")
    doc = data.get("doc")
    if doc is not None:
        home = path.parent.parent
        if not isinstance(doc, str) or not doc.strip() or Path(doc).is_absolute() or ".." in Path(doc).parts:
            errors.append(f"{path}: doc must be a relative path under {home}")
        elif not (home / doc).is_file():
            errors.append(f"{path}: doc {doc} does not exist under {home}")
    _check_params(data.get("params"), path, errors)
    _check_policy(data.get("policy"), path, errors)
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append(f"{path}: steps must be non-empty list")
        return
    seen: set[str] = set()
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"{path}: steps[{i}] not a mapping")
            continue
        for key in sorted(set(step) - STEP_FIELDS):
            errors.append(f"{path}: steps[{i}] unknown field {key!r}")
        sid = step.get("id")
        kind = step.get("kind")
        if not sid:
            errors.append(f"{path}: steps[{i}] missing id")
        elif sid in seen:
            errors.append(f"{path}: duplicate step id {sid}")
        else:
            seen.add(sid)
        if kind in FORBIDDEN:
            errors.append(f"{path}: forbidden kind {kind}")
        elif kind not in KINDS:
            errors.append(f"{path}: unknown kind {kind}")
        if "with" in step and not isinstance(step["with"], dict):
            errors.append(f"{path}: steps[{i}].with must be a mapping")
        elif kind == "human.gate":
            _check_gate(step, f"{path}: steps[{i}]", errors)


def _check_gate(step: dict, where: str, errors: list[str]) -> None:
    """A gate declares what it will write: with.will_write ([] = nothing) or 将代写 in label."""
    payload = step.get("with") or {}
    if "will_write" in payload:
        will = payload["will_write"]
        if not isinstance(will, list) or not all(isinstance(w, str) and w.strip() for w in will):
            errors.append(f"{where} human.gate with.will_write must be a list of non-empty strings ([] = 将代写: 无)")
    elif "将代写" not in str(step.get("label") or ""):
        errors.append(f"{where} human.gate needs with.will_write or 将代写 in label")


def will_write_line(step: dict) -> str:
    payload = step.get("with") or {}
    if "will_write" in payload:
        return "将代写: " + ("、".join(payload["will_write"]) or "无")
    label = str(step.get("label") or "")
    return label[label.index("将代写"):] if "将代写" in label else ""


def _check_params(params: Any, path: Path, errors: list[str]) -> None:
    if params is None:
        return
    if not isinstance(params, list):
        errors.append(f"{path}: params must be a list")
        return
    names: set[str] = set()
    for i, param in enumerate(params):
        if not isinstance(param, dict):
            errors.append(f"{path}: params[{i}] not a mapping")
            continue
        for key in sorted(set(param) - PARAM_FIELDS):
            errors.append(f"{path}: params[{i}] unknown field {key!r}")
        name = param.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{path}: params[{i}] missing name")
        elif name in names:
            errors.append(f"{path}: duplicate param {name}")
        else:
            names.add(name)
        if not isinstance(param.get("required"), bool):
            errors.append(f"{path}: params[{i}].required must be true or false")
        src = param.get("from")
        if src not in PARAM_FROM:
            errors.append(f"{path}: params[{i}].from must be one of {sorted(PARAM_FROM)}")
        if src == "default" and "default" not in param:
            errors.append(f"{path}: params[{i}] from default needs a default value")
        if "product_key" in param and src != "product":
            errors.append(f"{path}: params[{i}].product_key only goes with from: product")


def _check_policy(policy: Any, path: Path, errors: list[str]) -> None:
    if policy is None:
        return
    if not isinstance(policy, dict):
        errors.append(f"{path}: policy must be a mapping")
        return
    for key, value in policy.items():
        rule = POLICY.get(key)
        if rule is None:
            errors.append(f"{path}: unknown policy {key!r}")
        elif rule is bool:
            if not isinstance(value, bool):
                errors.append(f"{path}: policy.{key} must be true or false")
        elif rule is int:
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                errors.append(f"{path}: policy.{key} must be a positive integer")
        elif value not in rule:
            errors.append(f"{path}: policy.{key} must be one of {sorted(rule)}")


def check_run(data: Any, path: Path, errors: list[str]) -> None:
    if not isinstance(data, dict):
        errors.append(f"{path}: not a mapping")
        return
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{path}: schema_version must be {SCHEMA_VERSION}")
    if not data.get("workflow_id"):
        errors.append(f"{path}: missing workflow_id")
    if not data.get("feature"):
        errors.append(f"{path}: missing feature")
    st = data.get("status")
    if st not in RUN_STATUS:
        errors.append(f"{path}: bad status {st!r}")
    steps = data.get("steps")
    if not isinstance(steps, list):
        errors.append(f"{path}: steps must be list")
        return
    seen: set[str] = set()
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"{path}: steps[{i}] not a mapping")
            continue
        sid = step.get("id")
        if sid in seen:
            errors.append(f"{path}: duplicate step id {sid}")
        seen.add(sid)
        ss = step.get("status")
        if ss is not None and ss not in STEP_STATUS:
            errors.append(f"{path}: steps[{i}].status bad {ss!r}")
        kind = step.get("kind")
        if kind in FORBIDDEN:
            errors.append(f"{path}: steps[{i}] forbidden kind {kind}")
        elif kind and kind not in KINDS:
            errors.append(f"{path}: steps[{i}] unknown kind {kind}")
        if kind == "human.gate" and ss == "PASS":
            sign = step.get("signoff") if isinstance(step.get("signoff"), dict) else {}
            if not is_confirm(str(sign.get("quote") or "")) or not is_human(str(sign.get("by") or "")):
                errors.append(f"{path}: steps[{i}] human.gate PASS needs signoff.by (a person) and a confirm quote")


def is_confirm(quote: str) -> bool:
    low = quote.strip().strip("。.!！ ").lower()
    return any(low.startswith(word) for word in CONFIRM_WORDS)


def is_human(by: str) -> bool:
    name = by.strip()
    return bool(name) and name.lower() not in AGENT_NAMES
