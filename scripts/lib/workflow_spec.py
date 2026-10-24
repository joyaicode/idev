#!/usr/bin/env python3
"""Workflow syntax (schema_version 1) as code.

references/workflow-schema.md is the prose. This module is the same contract
for tools: workflow-check validates with it, workflow.py drives runs with it.
selfcheck keeps the kind table in the prose equal to KINDS here.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any, NamedTuple

SCHEMA_VERSION = 1

try:
    import _generated_kinds as _gen
except ImportError:  # loaded as lib.<module>, with scripts/ on the path
    from lib import _generated_kinds as _gen  # type: ignore[no-redef]

# The kind table is generated from registry/kinds.yaml; see scripts/gen-kinds.py.
# These were three hand-maintained copies of data that also lived in
# kind_agents, workflow_defaults and two prose tables.
KINDS: dict[str, str] = _gen.KINDS
LEGACY_KINDS = _gen.LEGACY_KINDS
FORBIDDEN = _gen.FORBIDDEN

TOP_FIELDS = {
    "schema_version", "id", "aliases", "summary", "doc", "risk_tier",
    "needs_ticket", "params", "policy", "steps", "roles", "rules",
}
PARAM_FIELDS = {"name", "required", "from", "default", "product_key"}
PARAM_FROM = {"user", "deliver.yaml", "default", "product"}
STEP_FIELDS = {"id", "kind", "label", "with", "group", "writes"}
RISK_TIERS = {"P0", "P1", "P2"}
POLICY: dict[str, Any] = {
    "on_fail": {"stop", "ask"},
    "on_gate": {"stop"},
    "on_case_fail": {"stop_fix_continue"},
    "require_clean_pass": bool,
    "max_clean_attempts": int,
}

RUN_STATUS = {"pending", "running", "blocked", "done", "aborted"}
STEP_STATUS = {"PASS", "FAIL", "UNPROVEN", "SKIPPED", "BLOCKED", "AUTO"}
STEP_DONE = {"PASS", "SKIPPED", "UNPROVEN", "AUTO"}
STEP_STOP = {"FAIL", "BLOCKED"}

# A decision answer that answers nothing. 继续 moves on without choosing, so
# the conductor asks again rather than recording it as the person's choice.
NON_ANSWERS = frozenset({"继续", "continue", "ok", "okay", "好", "好的", "嗯", "收到", "go", "next"})

CONFIRM_WORDS = ("确认", "全签", "同意", "lgtm")
AGENT_NAMES = {"agent", "ai", "cursor", "assistant"}

# --- signoff grammar -------------------------------------------------------
# `is_confirm` used to be `low.startswith(word)`. That accepted 确认不了,
# 同意吗 and "LGTM but wait" — a refusal, a question and a hesitation, all
# recorded as a person signing off. A prefix test cannot tell a sentence
# from its first two characters, so the whole sentence is parsed instead and
# anything left over is a rejection.
REJECT_WORDS = ("驳回",)

# A confirmation may carry qualifiers, but only these. An unknown word means
# the person wrote a sentence, not a signoff.
CONFIRM_SEPS = (" ", "，", ",", "：", ":")
CONFIRM_TOKENS = (
    "origin=req",
    "origin=arch",
    "origin=code",
    "解除密封",
    "reopen",
    "sealed",
    "accepted",
    "aligned",
    "resolved",
    "plan",
    "方案",
    "拆解",
    "基线",
    "提测",
)

# Second line of defence. A hit is a refusal with a reason, so the conductor
# can quote back why rather than just failing.
QUESTION_MARKS = ("?", "？", "吗", "么", "嘛", "呢", "是否", "能否", "可否", "要不要")
NEGATION_CJK = ("不", "没", "别", "未", "否", "勿")
NEGATION_ASCII = ("not", "no", "don't", "wait", "but", "hold", "later")
HESITATION = ("先", "等", "再说", "待定", "也许", "可能", "吧")

# Names that are never a person. The `idev-` prefix and the `agent`/`assistant`
# substrings cover the five kernel agents and anything added later; the list
# is for models that sign under their own product name.
AGENT_WORDS = frozenset(AGENT_NAMES) | frozenset(
    {
        "claude",
        "gpt",
        "chatgpt",
        "codex",
        "gemini",
        "grok",
        "copilot",
        "composer",
        "sonnet",
        "opus",
        "deepseek",
        "glm",
        "qwen",
        "kimi",
        "llm",
        "bot",
        "model",
        "subagent",
        "conductor",
        "system",
        "root",
        "human",
    }
)

# A name is matched token by token as well as whole, so "glm-4.6" and
# "Grok Bot" cannot slip past the whole-string set. Any [a-z0-9]+ run hits.
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _names_an_agent(low: str) -> bool:
    """True when the lowercased name names an agent or a model, in whole or
    in any one of its word tokens."""
    if low in AGENT_WORDS:
        return True
    return any(tok in AGENT_WORDS for tok in _TOKEN_RE.findall(low))


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
    _check_parallel(steps, path, errors)


def _writes_overlap(a: str, b: str) -> bool:
    """True when two ticket-relative paths name the same file or one contains the other."""
    if a == b:
        return True
    left, right = a.rstrip("/") + "/", b.rstrip("/") + "/"
    return left.startswith(right) or right.startswith(left)


def _check_parallel(steps: list, path: Path, errors: list[str]) -> None:
    """A group is one wave: contiguous, verify-only, and the write paths do not overlap.

    A human gate and a write lease stay one step at a time. Two members that
    can both rewrite the same file are not a locked interface.
    """
    members: dict[str, list[int]] = {}
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        group = step.get("group")
        writes = step.get("writes")
        where = f"{path}: steps[{i}]"
        if group is not None:
            if not isinstance(group, str) or re.fullmatch(r"[a-z][a-z0-9-]*", group) is None:
                errors.append(f"{where} group must be a slug")
            kind = step.get("kind")
            if kind == "human.gate":
                errors.append(f"{where} a human.gate stays one step at a time")
            if _gen.KIND_LEASE.get(kind) == "write":
                errors.append(f"{where} a write lease stays one step at a time")
            if "writes" not in step:
                errors.append(f"{where} a group needs writes")
        if writes is not None and group is None:
            errors.append(f"{where} writes only goes with a group")
        if writes is not None:
            if not isinstance(writes, list) or not writes or not all(isinstance(w, str) and w for w in writes):
                errors.append(f"{where} writes must be a non-empty list of paths")
            else:
                for w in writes:
                    if not isinstance(w, str) or w.startswith("/") or ".." in Path(w).parts:
                        errors.append(f"{where} writes path {w!r} must stay inside the ticket")
        if isinstance(group, str) and group:
            members.setdefault(group, []).append(i)
    for name, idxs in members.items():
        if idxs[-1] - idxs[0] + 1 != len(idxs):
            errors.append(f"{path}: group {name} must be contiguous")
            continue
        owned: list[tuple[int, str]] = []
        for i in idxs:
            for w in steps[i].get("writes") or []:
                if isinstance(w, str):
                    owned.append((i, w))
        for a in range(len(owned)):
            for b in range(a + 1, len(owned)):
                if _writes_overlap(owned[a][1], owned[b][1]):
                    errors.append(
                        f"{path}: group {name} writes overlap: "
                        f"steps[{owned[a][0]}] {owned[a][1]} and steps[{owned[b][0]}] {owned[b][1]}"
                    )


def _check_gate(step: dict, where: str, errors: list[str]) -> None:
    """A gate declares what it will write: with.will_write ([] = nothing) or 将代写 in label."""
    payload = step.get("with") or {}
    if "will_write" in payload:
        will = payload["will_write"]
        if not isinstance(will, list) or not all(isinstance(w, str) and w.strip() for w in will):
            errors.append(f"{where} human.gate with.will_write must be a list of non-empty strings ([] = 将代写: 无)")
    elif "将代写" not in str(step.get("label") or ""):
        errors.append(f"{where} human.gate needs with.will_write or 将代写 in label")
    if "auto_tiers" in payload:
        tiers = payload["auto_tiers"]
        if not isinstance(tiers, list) or not tiers or not set(tiers) <= RISK_TIERS:
            errors.append(f"{where} human.gate with.auto_tiers must be a non-empty list of {sorted(RISK_TIERS)}")
    if "gate_type" in payload and payload["gate_type"] not in GATE_TYPES:
        errors.append(f"{where} human.gate with.gate_type must be one of {sorted(GATE_TYPES)}")
    subject = payload.get("subject")
    if subject is not None and not (
        (isinstance(subject, str) and subject.strip())
        or (isinstance(subject, list) and subject and all(isinstance(s, str) and s.strip() for s in subject))
    ):
        errors.append(f"{where} human.gate with.subject must be a ticket-relative path or a list of them")


# internal/domain/gate.Type, less the three that need what a recipe cannot
# supply: sealed and reopen_baseline a baseline revision, defect_origin the
# origin being asked about.
GATE_TYPES = frozenset({
    "accepted_req", "accepted_arch", "accepted_plan", "aligned", "resolved", "step_confirm",
})


def auto_tiers(step: dict) -> set:
    """The risk tiers at which this gate may pass on machine checks alone."""
    tiers = (step.get("with") or {}).get("auto_tiers")
    return set(tiers) if isinstance(tiers, list) else set()


def is_answer(quote: str) -> bool:
    """True when a decision quote chooses something; 继续 / ok do not."""
    text = normalize_quote(quote)
    return bool(text) and text not in NON_ANSWERS


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
        if ss == "AUTO":
            if kind != "human.gate":
                errors.append(f"{path}: steps[{i}] AUTO is only for a human.gate that declares auto_tiers")
            elif not str(step.get("evidence") or "").strip():
                errors.append(f"{path}: steps[{i}] AUTO needs evidence of the machine checks")
            elif step.get("signoff"):
                errors.append(f"{path}: steps[{i}] AUTO must not carry a signoff; nobody signed")


class Confirm(NamedTuple):
    """Whether a quote is a signoff, and when it is not, why not."""

    ok: bool
    reason: str  # ok | no-verb | question | negation | hesitation | unparsed-tail | keyword-mismatch
    tokens: tuple  # the qualifiers the person wrote, e.g. ("origin=code",)


def normalize_quote(quote: str) -> str:
    """NFKC, trim, lowercase, drop trailing punctuation, collapse whitespace.

    NFKC folds the full-width forms (？！，：) onto ASCII, so the marker and
    separator tables below only need one spelling of each.
    """
    text = unicodedata.normalize("NFKC", str(quote or "")).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text.rstrip("。.!~ ")


def _parse_grammar(text: str, verbs: tuple) -> tuple:
    """(verb, tokens) for `VERB (SEP TOKEN)*`; tokens is None on a bad tail."""
    for verb in verbs:
        if not text.startswith(verb):
            continue
        rest = text[len(verb) :]
        tokens: list = []
        while rest:
            sep = next((s for s in CONFIRM_SEPS if rest.startswith(s)), None)
            if sep is None:
                return (verb, None)
            rest = rest[len(sep) :].lstrip()
            token = next((t for t in CONFIRM_TOKENS if rest.startswith(t)), None)
            if token is None:
                return (verb, None)
            tokens.append(token)
            rest = rest[len(token) :]
        return (verb, tuple(tokens))
    return (None, None)


_NEGATION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in NEGATION_ASCII) + r")\b"
)


def parse_confirm(quote: str, gate_type: str = "", origin: str = "") -> Confirm:
    """Parse a signoff quote as a whole sentence.

    `gate_type` and `origin` carry the destructive-gate keyword rules: a
    defect_origin signoff must name the same origin the gate is asking about,
    and reopening a sealed baseline must say so in words.
    """
    text = normalize_quote(quote)
    if not text:
        return Confirm(False, "no-verb", ())

    # Questions first, so 同意吗 and 确认？ report what is actually wrong with
    # them rather than the generic tail error.
    if any(mark in text for mark in QUESTION_MARKS):
        return Confirm(False, "question", ())

    verb, tokens = _parse_grammar(text, CONFIRM_WORDS)
    if verb is None:
        return Confirm(False, "no-verb", ())
    if tokens is None:
        return Confirm(False, "unparsed-tail", ())

    # Unreachable while every token above is free of these markers; kept so
    # that adding a token cannot quietly open a hole.
    if any(mark in text for mark in NEGATION_CJK) or _NEGATION_RE.search(text):
        return Confirm(False, "negation", ())
    if any(mark in text for mark in HESITATION):
        return Confirm(False, "hesitation", ())

    if gate_type == "defect_origin":
        wanted = f"origin={str(origin or '').strip().lower()}"
        if wanted not in tokens:
            return Confirm(False, "keyword-mismatch", tokens)
    elif gate_type == "reopen_baseline":
        if not ({"解除密封", "reopen"} & set(tokens)):
            return Confirm(False, "keyword-mismatch", tokens)

    return Confirm(True, "ok", tokens)


def is_confirm(quote: str) -> bool:
    """True when the quote is a signoff. The thin wrapper every caller uses."""
    return parse_confirm(quote).ok


def is_reject(quote: str) -> bool:
    """True when the quote refuses. 驳回 is the only verb that counts."""
    text = normalize_quote(quote)
    verb, tokens = _parse_grammar(text, REJECT_WORDS)
    return verb is not None and tokens is not None


def people_whitelist() -> set:
    """Names allowed to sign, or an empty set when no list is configured.

    Looked for in the data root first (the idevd layout), then the kernel,
    then the product checkout. Absent is a valid state — the blacklist still
    applies — and `people_warning()` says so, per the "blacklist-only" rule.

    Cached per (IDEV_ROOT, cwd) because is_human runs once per step of a run
    and the lookup walks the filesystem for the product checkout.
    """
    return _people_state()[0]


def people_warning() -> str:
    """Why the whitelist is not in force, or "" when it is."""
    return _people_state()[1]


_PEOPLE_CACHE: dict = {}


def _people_state() -> tuple:
    key = (os.environ.get("IDEV_ROOT", ""), str(Path.cwd()))
    if key in _PEOPLE_CACHE:
        return _PEOPLE_CACHE[key]
    names: set = set()
    broken: list = []
    found = False
    for path in _people_files():
        if not path.is_file():
            continue
        found = True
        parsed = _read_people(path)
        if parsed is None:
            broken.append(str(path))
        else:
            names |= parsed
    if broken:
        # A whitelist that cannot be parsed must not read as "no whitelist":
        # that is strictly more permissive than the person intended.
        warning = f"people.yaml unreadable ({', '.join(broken)}); blacklist-only"
    elif not found:
        warning = "people.yaml missing; blacklist-only"
    elif not names:
        warning = "people.yaml lists nobody; blacklist-only"
    else:
        warning = ""
    state = (names, warning)
    _PEOPLE_CACHE[key] = state
    return state


def _people_files() -> list:
    out = []
    env = os.environ.get("IDEV_ROOT", "").strip()
    if env:
        out.append(Path(env).expanduser() / "config" / "people.yaml")
    try:
        import roots  # noqa: PLC0415
    except ImportError:  # pragma: no cover - only when sys.path is unusual
        return out
    out.append(roots.kernel_root() / "config" / "people.yaml")
    try:
        import product_sink  # noqa: PLC0415

        repo = product_sink.product_repo()
    except Exception:  # pragma: no cover - the product layer is optional here
        repo = None
    if repo is not None:
        out.append(Path(repo) / ".idev" / "people.yaml")
    return out


def _read_people(path: Path):
    """The names in one file, or None when the file cannot be read."""
    try:
        import yaml  # noqa: PLC0415

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, dict):
        data = data.get("people") or data.get("humans") or []
    if data is None:
        data = []
    if not isinstance(data, list):
        return None
    return {str(x).strip().lower() for x in data if str(x).strip()}


def is_human(by: str) -> bool:
    """True when `by` may sign.

    Two gates. The blacklist refuses anything that names a model, an agent or
    a role; it always applies. The whitelist, when one exists, refuses
    everything it does not list — that is the half that stops a plausible
    invented name from signing.
    """
    name = str(by or "").strip()
    if not name:
        return False
    low = unicodedata.normalize("NFKC", name).strip().lower()
    if _names_an_agent(low):
        return False
    if re.match(r"^idev[-_]", low):
        return False
    if "agent" in low or "assistant" in low:
        return False
    try:
        import kind_agents  # noqa: PLC0415

        if low in {a.lower() for a in kind_agents.AGENTS}:
            return False
    except ImportError:  # pragma: no cover - prefix rule already covers these
        pass
    allowed = people_whitelist()
    if allowed:
        return low in allowed
    return True
