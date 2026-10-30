#!/usr/bin/env python3
"""Validate, store, and render idev routing traces. No scores."""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from kind_agents import AGENTS  # noqa: E402
from product_sink import product_repo, sink_dir  # noqa: E402


MODULES = ("conventions", "deliver", "verify", "ops", "handoff")
CLASSES = (
    "",
    "evidence",
    "coding",
    "java",
    "identity",
    "config",
    "frontend",
    "landing",
    "docs",
    "specials",
)
STAGES = (
    "",
    "req-review",
    "req",
    "arch",
    "code",
    "test",
    "done",
    "ops",
    "verify-plan",
)
TIERS = ("", "P0", "P1", "P2")
SCENARIOS = ("", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")
SHORT_SCENARIOS = ("S2", "S3", "S5", "S8")
CHECKS = ("", "PASS", "FAIL", "skipped")
KINDS = ("route", "gate", "stop", "refuse", "handoff", "call", "open", "delegate", "model")
CALL_KINDS = ("script", "module", "skill", "repo", "tool", "agent", "model")
# Conductor-kept steps use the same word workflow.py prints: "DELEGATE none".
DELEGATE_CHOICES = AGENTS + ("none", "-")
INVOKE_HOW = ("explicit", "alias", "implicit", "continuation")
DURATION = re.compile(r"^\d+(\.\d+)?$")
ITEM_KEYS = (
    "kind",
    "module",
    "chose",
    "why",
    "name",
    "path",
    "args",
    "result",
    "target",
    "model",
    "from",
    "to",
    "thinking",
    "duration_s",
    "n",
    "do",
    "so",
)


def field(text: str, key: str) -> str:
    m = re.search(r"^[ \t]*" + re.escape(key) + r":\s*(.*)$", text, re.M)
    if not m:
        return ""
    return m.group(1).strip().strip('"').strip("'")


def block(text: str, heading: str) -> str:
    m = re.search(
        r"^" + re.escape(heading) + r":\s*(?:\[\]\s*)?\n(?P<body>(?:[ \t].*\n)*)",
        text,
        re.M,
    )
    return m.group("body") if m else ""


def maps_from_body(body: str) -> list[dict[str, str]]:
    if not body:
        return []
    chunks = re.split(r"(?m)^\s+-\s+", body)
    out: list[dict[str, str]] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        item: dict[str, str] = {}
        for key in ITEM_KEYS:
            m = re.search(r"(?:^|[ \t])" + re.escape(key) + r":\s*(.*)$", chunk, re.M)
            if m:
                item[key] = m.group(1).strip().strip('"').strip("'")
        if item:
            out.append(item)
    return out


def dash_maps(text: str, heading: str) -> list[dict[str, str]]:
    return maps_from_body(block(text, heading))


def nested_block(text: str, heading: str) -> str:
    """Body under a nested key, stopping when indentation returns."""
    m = re.search(
        r"^(?P<indent>[ \t]*)" + re.escape(heading) + r":[ \t]*(?:\[\][ \t]*)?\s*$",
        text,
        re.M,
    )
    if not m:
        return ""
    base = len(m.group("indent"))
    rest = text[m.end() :]
    if rest.startswith("\n"):
        rest = rest[1:]
    lines: list[str] = []
    for line in rest.splitlines(keepends=True):
        if line.strip() == "":
            lines.append(line)
            continue
        lead = len(line) - len(line.lstrip(" \t"))
        if lead <= base:
            break
        lines.append(line)
    return "".join(lines)


def nested_maps(text: str, heading: str) -> list[dict[str, str]]:
    return maps_from_body(nested_block(text, heading))


def list_scalars(text: str, heading: str) -> list[str]:
    """Parse YAML list of scalars under heading (string items or - key: val maps skipped)."""
    body = block(text, heading)
    if not body:
        return []
    out: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^\s+-\s+(.*)$", line)
        if not m:
            continue
        raw = m.group(1).strip()
        if re.match(r"^[A-Za-z_][\w]*:", raw):
            # map item handled elsewhere
            continue
        out.append(raw.strip('"').strip("'"))
    return out


def default_dir() -> Path:
    override = os.environ.get("IDEV_TRACE_DIR")
    if override:
        return Path(override)
    return sink_dir("traces", mkdir=True)


def read_text(src: str) -> str:
    if src == "-":
        return sys.stdin.read()
    return Path(src).read_text(encoding="utf-8")


def validate(text: str, *, for_append: bool = False) -> list[str]:
    errors: list[str] = []
    ver = field(text, "schema_version")
    if ver not in ("1", "2"):
        errors.append("schema_version must be 1 or 2")
    if for_append and ver == "1":
        errors.append("new traces must use schema_version 2 (v1 is read-only)")
    if not field(text, "at"):
        errors.append("at empty")
    if not field(text, "intent"):
        errors.append("intent empty")
    route = block(text, "route")
    if not route:
        errors.append("route block missing")
        return errors
    module = field(route, "module")
    if module not in MODULES:
        errors.append("route.module unknown: %s" % (module or "empty"))
    if not field(route, "why"):
        errors.append("route.why empty")
    klass = field(route, "convention_class")
    if klass not in CLASSES:
        errors.append("route.convention_class unknown: %s" % klass)
    stage = field(route, "stage")
    if stage not in STAGES:
        errors.append("route.stage unknown: %s" % stage)
    tier = field(route, "risk_tier")
    if tier not in TIERS:
        errors.append("route.risk_tier unknown: %s" % tier)
    scenario = field(route, "scenario")
    if scenario not in SCENARIOS:
        errors.append("route.scenario unknown: %s" % scenario)
    check = field(text, "check_feature")
    if check not in CHECKS:
        errors.append("check_feature unknown: %s" % check)
    for item in dash_maps(text, "rejected"):
        if item.get("module") and item["module"] not in MODULES:
            errors.append("rejected.module unknown: %s" % item["module"])
        if not item.get("why"):
            errors.append("rejected item missing why")
    for item in dash_maps(text, "decisions"):
        if item.get("kind") not in KINDS:
            errors.append("decisions.kind unknown: %s" % (item.get("kind") or "empty"))
        if not item.get("why"):
            errors.append("decisions item missing why")
        if not item.get("chose"):
            errors.append("decisions item missing chose")
        if item.get("kind") == "delegate" and item.get("chose") not in DELEGATE_CHOICES:
            errors.append("decisions.delegate unknown: %s" % (item.get("chose") or "empty"))

    if ver == "2":
        invoke = block(text, "invoke")
        if not invoke:
            errors.append("invoke block missing")
        else:
            if not field(invoke, "trigger"):
                errors.append("invoke.trigger empty")
            if not field(invoke, "matched"):
                errors.append("invoke.matched empty")
            how = field(invoke, "how")
            if how and how not in INVOKE_HOW:
                errors.append("invoke.how unknown: %s" % how)
            skills_body = nested_block(invoke, "skills")
            if skills_body.strip():
                skills = maps_from_body(skills_body)
                n_raw = len(re.findall(r"(?m)^\s+-\s+\S", skills_body))
                if n_raw != len(skills) or any(not s.get("name") for s in skills):
                    errors.append("invoke.skills item missing name")
        thinking = block(text, "thinking")
        if not thinking:
            errors.append("thinking block missing")
        else:
            if not field(thinking, "summary"):
                errors.append("thinking.summary empty")
        for item in dash_maps(text, "calls"):
            if item.get("kind") not in CALL_KINDS:
                errors.append("calls.kind unknown: %s" % (item.get("kind") or "empty"))
            if not item.get("name"):
                errors.append("calls item missing name")
            if item.get("duration_s") and not DURATION.match(item["duration_s"]):
                errors.append("calls.duration_s not a number: %s" % item["duration_s"])
            if ("from" in item or "to" in item) and not (item.get("from") and item.get("to")):
                errors.append("calls.from and calls.to must both be set")
            if "model" in item and not item.get("model"):
                errors.append("calls.model empty")
            if "thinking" in item and not item.get("thinking"):
                errors.append("calls.thinking empty")
        if thinking:
            steps_body_m = re.search(
                r"^[ \t]*steps:\s*(?:\[\]\s*)?\n(?P<body>(?:[ \t].*\n)*)",
                thinking,
                re.M,
            )
            if steps_body_m:
                fake = "steps:\n" + steps_body_m.group("body")
                for item in dash_maps(fake, "steps"):
                    if not item.get("do"):
                        errors.append("thinking.steps item missing do")
                    if not item.get("so"):
                        errors.append("thinking.steps item missing so")

    if ver == "2" and for_append:
        errors.extend(signoff_errors(text))
    return errors


MARKS = ("sealed", "accepted", "aligned", "resolved")
# A repo call's result says what it read as often as what it wrote; only a write verb counts.
WRITE_MARK = re.compile(
    r"(?:写入|写上|填入|签入)\s*(?:sealed|accepted|aligned|resolved)\b"
    r"|\b(?:set|wrote|write|writes)\s+(?:sealed|accepted|aligned|resolved)\b",
    re.I,
)
GATE_MARK = {"accepted_req": "accepted", "accepted_arch": "accepted", "accepted_plan": "accepted",
             "aligned": "aligned", "resolved": "resolved"}


def machine_items(text: str, heading: str) -> list[dict[str, str]]:
    """Items of a block trace.py writes itself, every `key: value` kept."""
    out: list[dict[str, str]] = []
    for chunk in re.split(r"(?m)^\s+-\s+", block(text, heading)):
        item = {}
        for key, value in re.findall(r"(?m)^\s*([A-Za-z_]+):\s*(.*)$", chunk):
            item[key] = value.strip().strip('"').strip("'")
        if item:
            out.append(item)
    return out


def signoff_marks(text: str) -> list[str]:
    so = block(text, "signoff")
    if not so:
        return []
    listed = field(so, "marks") + " " + nested_block(so, "marks")
    return [m for m in MARKS if re.search(r"\b%s\b" % m, listed, re.I)]


def chat_confirmed(text: str) -> bool:
    return any(item.get("kind") == "call" and item.get("chose") == "chat-confirm-signoff"
               for item in dash_maps(text, "decisions"))


def mark_writes(text: str) -> list[str]:
    """Where the trace records that this round wrote a signoff mark.

    Only the parts that say what the round did count: a repo call whose
    result names a write of a mark, signoff.marks, and a gate the round
    recorded. A refusal, an excluded option, a reason that names a mark or a
    state read back is not a write, and no word elsewhere switches the check
    off.
    """
    found = []
    for item in dash_maps(text, "calls"):
        if item.get("kind") == "repo" and WRITE_MARK.search(item.get("result") or ""):
            found.append("calls: %s → %s" % (item.get("name") or "?", item["result"][:40]))
    marks = signoff_marks(text)
    if marks:
        found.append("signoff.marks: " + ",".join(marks))
    for item in machine_items(text, "recorded"):
        if item.get("mark"):
            found.append("recorded: %s %s" % (item.get("step") or "?", item["mark"]))
    return found


def signoff_errors(text: str) -> list[str]:
    """A round that wrote a mark, or took a chat confirmation, says who and with what words.

    A chat confirmation that ended up writing nothing keeps status none; the
    block still names the person and their words.
    """
    writes = mark_writes(text)
    asked = chat_confirmed(text)
    if not writes and not asked:
        return []
    so = block(text, "signoff")
    if not so and writes:
        return ["signoff block required when writing sealed/accepted/aligned/resolved (%s)" % "; ".join(writes)]
    if not so:
        return ["signoff block required after chat-confirm-signoff: by is the person, evidence their words;"
                " status: none if no field was written"]
    errors = []
    if writes and field(so, "status") not in ("recorded", "pending"):
        errors.append("signoff.status must be recorded|pending when writing marks (%s)" % "; ".join(writes))
    by = field(so, "by")
    if not by or by.lower() in ("agent", "ai", "idev", "bot") or by in AGENTS:
        errors.append("signoff.by must be a human id (not agent/ai)")
    if not field(so, "evidence"):
        errors.append("signoff.evidence empty")
    return errors


def _join(items, empty: str = "—") -> str:
    seq = list(items) if items is not None else []
    return "; ".join(seq) if seq else empty



def skills_line(invoke: str) -> str:
    if not invoke:
        return ""
    how = field(invoke, "how")
    parts = []
    for item in nested_maps(invoke, "skills"):
        bit = item.get("name") or "?"
        if item.get("why"):
            bit += "（%s）" % item["why"][:60]
        parts.append(bit)
    body = " · ".join(parts)
    if how and body:
        return "%s: %s" % (how, body)
    return body or how


def choices_line(text: str) -> str:
    parts = []
    for item in dash_maps(text, "decisions"):
        if item.get("kind") in ("delegate", "model"):
            parts.append("%s→%s" % (item.get("kind"), item.get("chose") or "?"))
    return " · ".join(parts)


def hops_line(calls: list[dict[str, str]]) -> str:
    parts = []
    n = 0
    for item in calls:
        if not (item.get("from") and item.get("to")):
            continue
        n += 1
        bit = "%s→%s" % (item["from"], item["to"])
        model = item.get("model") or (item.get("name") if item.get("kind") == "model" else "")
        if model:
            bit += " model=%s" % model[:40]
        note = item.get("thinking") or item.get("why") or ""
        if note:
            bit += " 「%s」" % str(note)[:50]
        if item.get("duration_s"):
            bit += " %ss" % item["duration_s"]
        if item.get("result"):
            bit += " → %s" % item["result"][:40]
        parts.append("%d.%s" % (n, bit))
    return " → ".join(parts)


def hop_rows(calls: list[dict[str, str]]) -> list[str]:
    """One block per hop so Thought and Observation stay readable."""
    rows = []
    n = 0
    for item in calls:
        if not (item.get("from") and item.get("to")):
            continue
        n += 1
        rows.extend(_one_hop(n, item))
    return rows


def _one_hop(n: int, item: dict[str, str]) -> list[str]:
    rows = ["%d. %s → %s" % (n, item["from"], item["to"])]
    note = " ".join(str(item.get("thinking") or item.get("why") or "").split())
    result = " ".join(str(item.get("result") or "").split())
    if note:
        rows.append("   why: %s" % note[:160])
    if result:
        rows.append("   result: %s" % result[:160])
    if item.get("duration_s"):
        rows.append("   %ss" % item["duration_s"])
    return rows


def _top(text: str, key: str) -> str:
    found = re.search(r"^" + re.escape(key) + r":\s*(.*)$", text, re.M)
    if not found:
        return ""
    return found.group(1).strip().strip('"').strip("'")


def path_segments(text: str) -> dict[str, str]:
    """Extract the actual runtime path pieces from one trace (no scores)."""
    route = block(text, "route")
    invoke = block(text, "invoke")
    thinking = block(text, "thinking")
    scenario = field(route, "scenario") or "S1"
    module = field(route, "module") or "?"
    stage = field(route, "stage")
    tier = field(route, "risk_tier")
    route_bits = [scenario, module]
    if stage:
        route_bits.append(stage)
    if tier:
        route_bits.append(tier)
    calls = dash_maps(text, "calls")
    call_parts = []
    for i, c in enumerate(calls, 1):
        bit = "%s:%s" % (c.get("kind") or "?", c.get("name") or "?")
        if c.get("args"):
            bit += "(%s)" % c["args"][:60]
        if c.get("result"):
            bit += "→%s" % c["result"][:40]
        call_parts.append("%d.%s" % (i, bit))
    step_parts = []
    if thinking:
        dos = re.findall(r"(?m)^[ \t]+do:\s*(.*)$", thinking)
        sos = re.findall(r"(?m)^[ \t]+so:\s*(.*)$", thinking)
        for i, do in enumerate(dos):
            so = sos[i] if i < len(sos) else ""
            do = do.strip().strip('"').strip("'")
            so = so.strip().strip('"').strip("'")
            step_parts.append("%d.%s→%s" % (i + 1, do[:50], so[:40] if so else ""))
    opened = list_scalars(text, "opened")
    rejected = dash_maps(text, "rejected")
    rej = ", ".join(i.get("module") or "?" for i in rejected)
    delegated = " · ".join(
        "%s %s#%s%s" % (d.get("agent") or "?", d.get("step") or "?", d.get("attempt") or "1",
                        " verify" if d.get("role") == "verifier" else "")
        for d in machine_items(text, "delegations")
    )
    return {
        "delegated": delegated,
        "feature": field(text, "feature") or "-",
        "trigger": field(invoke, "trigger") if invoke else "",
        "matched": field(invoke, "matched") if invoke else "",
        "route": " → ".join(route_bits),
        "why": field(route, "why") or "",
        "steps": " → ".join(step_parts) if step_parts else "",
        "calls": " → ".join(call_parts) if call_parts else "(none)",
        "skills": skills_line(invoke),
        "choices": choices_line(text),
        "hops": hops_line(calls),
        "react": _top(text, "react"),
        "opened": " · ".join(opened[:8]) if opened else "(none)",
        "rejected": rej or "(none)",
        "next": field(text, "next") or "",
        "stop": field(text, "stop") or "",
        "skeleton": "%s/%s" % (scenario, module) + (("/%s" % stage) if stage else ""),
    }


def path_oneline(seg: dict[str, str]) -> str:
    parts = []
    if seg.get("trigger"):
        parts.append("「%s」" % seg["trigger"][:40])
    parts.append(seg.get("route") or "?")
    if seg.get("choices"):
        parts.append(seg["choices"][:80])
    if seg.get("hops"):
        short = seg["hops"]
        if len(short) > 120:
            short = short[:117] + "..."
        parts.append("hops[%s]" % short)
    elif seg.get("calls") and seg["calls"] != "(none)":
        short = seg["calls"]
        if len(short) > 120:
            short = short[:117] + "..."
        parts.append("calls[%s]" % short)
    if seg.get("next"):
        parts.append("next:%s" % seg["next"][:40])
    return " → ".join(parts)


def render_path(text: str, *, name: str = "") -> str:
    seg = path_segments(text)
    lines = ["## 运行路径"]
    if name:
        lines.append("trace:    %s" % name)
    lines.append("feature:  %s" % seg["feature"])
    if seg["trigger"]:
        lines.append("trigger:  %s" % seg["trigger"])
    if seg["matched"]:
        lines.append("matched:  %s" % seg["matched"])
    lines.append("route:    %s" % seg["route"])
    if seg["why"]:
        lines.append("why:      %s" % seg["why"])
    lines.append("skills:   %s" % (seg["skills"] or "(none)"))
    lines.append("choices:  %s" % (seg["choices"] or "(none)"))
    lines.append("hops:     %s" % (seg["hops"] or "(none)"))
    if seg.get("react"):
        lines.append("react:    %s" % seg["react"])
    traced = hop_rows(dash_maps(text, "calls"))
    if traced:
        lines.append("追踪:")
        lines.extend("  " + row for row in traced)
    if seg["steps"]:
        lines.append("steps:    %s" % seg["steps"])
    lines.append("calls:    %s" % seg["calls"])
    if seg["delegated"]:
        lines.append("delegated: %s" % seg["delegated"])
    lines.append("opened:   %s" % seg["opened"])
    if seg["rejected"] and seg["rejected"] != "(none)":
        lines.append("rejected: %s" % seg["rejected"])
    if seg["stop"]:
        lines.append("stop:     %s" % seg["stop"])
    if seg["next"]:
        lines.append("next:     %s" % seg["next"])
    lines.append("")
    lines.append("一行: %s" % path_oneline(seg))
    return "\n".join(lines)


def cmd_path(path: str | None) -> int:
    if path:
        pth = Path(path)
        text = read_text(str(pth))
        name = pth.name
    else:
        files = listed_traces(default_dir())
        if not files:
            print("no traces", file=sys.stderr)
            return 1
        pth = files[-1]
        text = pth.read_text(encoding="utf-8")
        name = pth.name
    errors = validate(text)
    if errors:
        for e in errors:
            print("FAIL  " + e, file=sys.stderr)
        return 1
    print(render_path(text, name=name))
    return 0


def cmd_paths(limit: int) -> int:
    files = listed_traces(default_dir())
    if not files:
        print("no traces")
        return 0
    print("| trace | skeleton | 一行路径 |")
    print("|-------|----------|----------|")
    for path in files[-limit:]:
        text = path.read_text(encoding="utf-8")
        seg = path_segments(text)
        one = path_oneline(seg).replace("|", "/")
        print("| %s | %s | %s |" % (path.name, seg["skeleton"], one))
    return 0


def cmd_path_stats(limit: int) -> int:
    from collections import Counter

    files = listed_traces(default_dir())[-limit:]
    if not files:
        print("no traces")
        return 0
    skel = Counter()
    call0 = Counter()
    hows = Counter()
    deleg = Counter()
    issued = Counter()
    models = Counter()
    handoff = Counter()
    tools = Counter()
    for path in files:
        text = path.read_text(encoding="utf-8")
        seg = path_segments(text)
        skel[seg["skeleton"]] += 1
        calls = dash_maps(text, "calls")
        if calls:
            c0 = "%s:%s" % (calls[0].get("kind") or "?", calls[0].get("name") or "?")
            call0[c0] += 1
        else:
            call0["(none)"] += 1
        how = field(block(text, "invoke"), "how")
        if how:
            hows[how] += 1
        for item in dash_maps(text, "decisions"):
            if item.get("kind") == "delegate":
                deleg[item.get("chose") or "?"] += 1
        for item in machine_items(text, "delegations"):
            issued[item.get("agent") or "?"] += 1
        for item in calls:
            if item.get("kind") == "model":
                models[item.get("model") or item.get("name") or "?"] += 1
            if item.get("from") and item.get("to"):
                handoff["%s→%s" % (item["from"], item["to"])] += 1
                if str(item.get("from")).startswith("react:"):
                    tools[str(item.get("to") or "?")] += 1
    print("## path-stats (last %d)" % len(files))
    print("### route skeleton")
    for k, n in skel.most_common():
        print("- %s × %d" % (k, n))
    print("### first call")
    for k, n in call0.most_common(15):
        print("- %s × %d" % (k, n))
    print("### skill how")
    _print_counts(hows)
    print("### delegate")
    _print_counts(deleg)
    print("### delegated (from records)")
    _print_counts(issued)
    print("### model call")
    _print_counts(models)
    print("### handoff")
    _print_counts(handoff, limit=15)
    print("### tool hop")
    _print_counts(tools, limit=15)
    print("")
    print("用途: 看哪条场景/模块/首调用最热，以及技能入口、委派、模型与组件跳有没有被记下来。无分数。")
    return 0


def _print_counts(counter, limit: int = 10) -> None:
    if not counter:
        print("- (none)")
        return
    for k, n in counter.most_common(limit):
        print("- %s × %d" % (k, n))


def render(text: str) -> str:
    route = block(text, "route")
    bits = [field(route, "module"), field(route, "stage"), field(route, "risk_tier")]
    route_line = " / ".join(b for b in bits if b)
    invoke = block(text, "invoke")
    scenario = field(route, "scenario") or "S1"
    if scenario in SHORT_SCENARIOS:
        rows = [
            ("trigger", field(invoke, "trigger") if invoke else "—"),
            ("route", route_line or "—"),
            ("stop", field(text, "stop") or "—"),
            ("next", field(text, "next") or "—"),
        ]
    else:
        rejected = dash_maps(text, "rejected")
        rej = _join(
            "%s（%s）" % (i.get("module") or "?", i.get("why") or "") for i in rejected
        )
        decs = dash_maps(text, "decisions")
        dec = _join("%s→%s" % (i.get("kind"), i.get("chose")) for i in decs)
        thinking = block(text, "thinking")
        calls = dash_maps(text, "calls")
        call_line = _join(
            "%s:%s" % (i.get("kind") or "?", i.get("name") or "?") for i in calls
        )
        opened = list_scalars(text, "opened")
        opened_line = _join(opened)
        seg = path_segments(text)
        rows = [
            ("intent", field(text, "intent") or "—"),
            ("feature", field(text, "feature") or "—"),
            ("trigger", field(invoke, "trigger") if invoke else "—"),
            ("matched", field(invoke, "matched") if invoke else "—"),
            ("skills", seg["skills"] or "—"),
            ("route", route_line or "—"),
            ("why", field(route, "why") or "—"),
            ("rejected", rej),
            ("thinking", field(thinking, "summary") if thinking else "—"),
            ("calls", call_line),
            ("hops", seg["hops"] or "—"),
            ("opened", opened_line),
            ("conventions", field(route, "convention_class") or "—"),
            ("decisions", dec),
            ("stop", field(text, "stop") or "—"),
            ("check", field(text, "check_feature") or "skipped"),
            ("next", field(text, "next") or "—"),
        ]
    lines = ["## idev-trace", "| 项 | 值 |", "|----|----|"]
    for k, v in rows:
        lines.append("| %s | %s |" % (k, (v or "—").replace("|", "/")))
    return "\n".join(lines)


def next_path(folder: Path, when: dt.datetime, tries: int = 999) -> Path:
    """Reserve the next free YYYYMMDD-NNN name, atomically.

    Globbing for the highest number and adding one is a race: two rounds
    appended in the same moment both saw 002, both computed 003, and the
    second write erased the first — silently, because each one reported the
    name it thought it had written. O_EXCL makes the reservation the same
    operation as the check, so the loser gets 004 instead of nothing.

    The file is created empty; the caller writes into the reserved name.
    """
    folder.mkdir(parents=True, exist_ok=True)
    prefix = when.strftime("%Y%m%d")
    existing = sorted(folder.glob(prefix + "-*.yaml"))
    n = 1
    if existing:
        last = existing[-1].stem.split("-")[-1]
        try:
            n = int(last) + 1
        except ValueError:
            n = len(existing) + 1
    for _ in range(tries):
        candidate = folder / ("%s-%03d.yaml" % (prefix, n))
        try:
            os.close(os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
            return candidate
        except FileExistsError:
            n += 1
    raise SystemExit(f"BLOCKED no free trace name under {folder} after {tries} tries")


def cmd_check(path: str) -> int:
    text = read_text(path)
    errors = validate(text)
    if field(text, "schema_version") == "2":
        errors += signoff_errors(text)
    if errors:
        for e in errors:
            print("FAIL  " + e)
        print("%d FAIL" % len(errors))
        return 1
    print("PASS  trace schema")
    print("0 FAIL")
    return 0


def cmd_render(path: str) -> int:
    text = read_text(path)
    errors = validate(text)
    if errors:
        for e in errors:
            print("FAIL  " + e, file=sys.stderr)
        return 1
    print(render(text))
    return 0


def _quote(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return '"%s"' % escaped


def _format_calls(items: list[dict[str, str]]) -> str:
    lines = ["calls:"]
    for item in items:
        lines.append("  - kind: %s" % (item.get("kind") or "tool"))
        for key in ITEM_KEYS:
            if key != "kind" and item.get(key):
                lines.append("    %s: %s" % (key, _quote(item[key])))
    return "\n".join(lines) + "\n"


def _replace_calls(text: str, block: str) -> str:
    pattern = re.compile(r"^calls:\s*(?:\[\]\s*)?\n(?:[ \t].*\n)*", re.M)
    if pattern.search(text):
        return pattern.sub(block, text, count=1)
    if not text.endswith("\n"):
        text += "\n"
    return text + block


def merge_react(text: str) -> tuple[str, str]:
    """Copy hops from a loop file named by a top-level `react:` path into calls."""
    found = re.search(r"^react:\s*(.+)$", text, re.M)
    if not found:
        return text, ""
    raw = found.group(1).strip().strip('"').strip("'")
    path = Path(raw)
    if not path.is_file():
        return text, "react file missing: %s" % raw
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from react_loop import calls_from_file

    fresh = calls_from_file(path)
    have = {(item.get("name"), item.get("why"), item.get("result")) for item in dash_maps(text, "calls")}
    added = [item for item in fresh if (item.get("name"), item.get("why"), item.get("result")) not in have]
    if not added:
        return text, ""
    merged = list(dash_maps(text, "calls")) + added
    return _replace_calls(text, _format_calls(merged)), ""


def _idev_bin() -> str:
    import idev_bin

    return idev_bin.path() or ""


def merge_audit_export(text: str) -> tuple[str, str]:
    """Attach run→step→delegation actions from the audit chain when IDEV_RUN_ID is set.

    The audit row is the source of truth (written in the same TX as Apply).
    This only annotates the YAML projection; failure is a warning, not a block.
    """
    run_id = (os.environ.get("IDEV_RUN_ID") or "").strip()
    if not run_id:
        return text, ""
    idev = _idev_bin()
    if not idev:
        return text, "idev binary missing; skipped audit export merge"
    import subprocess

    try:
        proc = subprocess.run(
            [idev, "audit", "export", "--run", run_id, "--format", "jsonl"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return text, "audit export failed: %s" % exc
    if proc.returncode != 0:
        return text, "audit export exit %s: %s" % (
            proc.returncode,
            (proc.stderr or proc.stdout or "").strip()[:200],
        )
    actions: list[str] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            import json

            row = json.loads(line)
        except ValueError:
            continue
        act = str(row.get("action") or "")
        step = str(row.get("step_id") or "")
        if act:
            actions.append("%s%s" % (act, ("@" + step) if step else ""))
    if not actions:
        return text, ""
    note = "audit_export: " + " → ".join(actions)
    if "audit_export:" in text:
        return text, ""
    if not text.endswith("\n"):
        text += "\n"
    text += "notes:\n  - %s\n" % note
    return text, ""


def _when(value) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.astimezone()
    try:
        when = dt.datetime.fromisoformat(str(value or "").strip())
    except ValueError:
        return None
    return when if when.tzinfo else when.astimezone()


def previous_until(folder: Path) -> dt.datetime | None:
    """Where the last stored trace's round ended, so no record lands in two traces."""
    for path in reversed(listed_traces(folder)):
        text = path.read_text(encoding="utf-8", errors="replace")
        when = _when(field(block(text, "round"), "until")) or _when(field(text, "at"))
        if when is not None:
            return when
    return None


def round_facts(repo: Path, since: dt.datetime | None, until: dt.datetime) -> tuple[list[dict], list[dict]]:
    """The delegation records and step records that landed in (since, until]."""
    import yaml  # noqa: PLC0415 - only append reads records
    import record_paths  # noqa: PLC0415
    from workflow_spec import gate_type  # noqa: PLC0415

    def inside(when: dt.datetime | None) -> bool:
        return when is not None and (since is None or when > since) and when <= until

    def load(path: Path) -> dict | None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return None
        return data if isinstance(data, dict) else None

    pairs = []
    for pattern in record_paths.REPO_GLOBS:
        for path in repo.glob(pattern):
            record = None if path.name.endswith(".example.yaml") else load(path)
            if record is not None:
                pairs.append((path, record))
    delegations = []
    for path, record in record_paths.distinct(pairs):
        when = _when(record.get("at")) or dt.datetime.fromtimestamp(path.stat().st_mtime).astimezone()
        if inside(when):
            delegations.append((when, {
                "agent": str(record.get("agent") or ""),
                "feature": str(record.get("feature") or ""),
                "step": str(record.get("step") or ""),
                "attempt": str(record.get("attempt") or 1),
                "role": "verifier" if record_paths.is_verification(record) else "writer",
                "status": str((record.get("report") or {}).get("status") or ""),
                "record": path.relative_to(repo).as_posix(),
            }))
    recorded = []
    for run_path in sorted([*repo.glob("docs/task/*/workflow/run.yaml"), *repo.glob(".idev/task/*/workflow/run.yaml")]):
        run = load(run_path) or {}
        for step in run.get("steps") or []:
            if not isinstance(step, dict) or not step.get("status") or not inside(_when(step.get("at"))):
                continue
            signed = step.get("signoff") if isinstance(step.get("signoff"), dict) else {}
            delegated = step.get("delegated") if isinstance(step.get("delegated"), dict) else {}
            gate = step.get("kind") == "human.gate" and step.get("status") == "PASS" and signed.get("by")
            verification = step.get("verification") if isinstance(step.get("verification"), dict) else {}
            recorded.append((_when(step.get("at")), {
                "feature": str(run.get("feature") or run_path.parent.parent.name),
                "step": str(step.get("id") or ""),
                "kind": str(step.get("kind") or ""),
                "status": str(step["status"]),
                "evidence": str(step.get("evidence") or "").strip(),
                "verify_evidence": str(verification.get("evidence") or "").strip(),
                "by": str(signed.get("by") or delegated.get("agent") or "conductor"),
                "mark": GATE_MARK.get(gate_type(step), "") if gate else "",
                "run": run_path.relative_to(repo).as_posix(),
            }))
    by_time = lambda pair: pair[0]  # noqa: E731
    return [d for _, d in sorted(delegations, key=by_time)], [r for _, r in sorted(recorded, key=by_time)]


def _scalar(value: str) -> str:
    return value if re.fullmatch(r"[\w./@+-]+", value) else _quote(value)


DELEGATION_KEYS = ("agent", "feature", "step", "attempt", "role", "status", "record")
RECORDED_KEYS = (
    "feature", "step", "kind", "status", "evidence", "verify_evidence", "by", "mark", "run",
)


def _items_block(heading: str, items: list[dict], keys: tuple[str, ...]) -> str:
    if not items:
        return "%s: []\n" % heading
    lines = ["%s:" % heading]
    for item in items:
        lead = "  - "
        for key in keys:
            if item.get(key):
                lines.append("%s%s: %s" % (lead, key, _scalar(str(item[key]))))
                lead = "    "
    return "\n".join(lines) + "\n"


def _replace_block(text: str, heading: str, body: str) -> str:
    pattern = re.compile(r"^%s:.*\n(?:[ \t].*\n)*" % re.escape(heading), re.M)
    if pattern.search(text):
        return pattern.sub(lambda _: body, text, count=1)
    return text + body


def attach_round(text: str, folder: Path) -> tuple[str, str]:
    """Write what the round delegated and recorded, from the records themselves.

    The conductor writes intent, why and thinking. Delegations come from the
    delegation records and recorded steps from run.yaml, over the time since
    the last trace, so a round with no trace of its own is not lost: the next
    trace carries it. A gate the round recorded fills an absent signoff.
    """
    repo = product_repo()
    if repo is None:
        return text, ""
    since, until = previous_until(folder), dt.datetime.now().astimezone()
    try:
        delegations, recorded = round_facts(repo, since, until)
    except ImportError as exc:
        return text, "delegations and recorded steps not attached: %s" % exc
    window = "round:\n%s  until: %s\n" % (
        "  since: %s\n" % _quote(since.isoformat(timespec="seconds")) if since else "",
        _quote(until.isoformat(timespec="seconds")),
    )
    text = _replace_block(text, "round", window)
    text = _replace_block(text, "delegations", _items_block("delegations", delegations, DELEGATION_KEYS))
    text = _replace_block(text, "recorded", _items_block("recorded", recorded, RECORDED_KEYS))
    gates = [r for r in recorded if r.get("mark")]
    if gates and field(block(text, "signoff"), "status") in ("", "none"):
        text = _replace_block(text, "signoff", "signoff:\n  status: recorded\n  marks: [%s]\n  by: %s\n  evidence: %s\n" % (
            ", ".join(sorted({g["mark"] for g in gates})),
            _scalar(", ".join(sorted({g["by"] for g in gates}))),
            _scalar("; ".join("%s#%s.signoff" % (g["run"], g["step"]) for g in gates)),
        ))
    return text, ""


def cmd_append(path: str) -> int:
    """Write a round YAML projection. Audit spans live in the DB; this file is
    an export. A write miss prints WARN and exits 0 so it cannot unwind a
    committed Apply (E5.4).
    """
    text = read_text(path)
    if not text.endswith("\n"):
        text += "\n"
    text, react_error = merge_react(text)
    if react_error:
        print("FAIL  " + react_error, file=sys.stderr)
        return 1
    text, audit_warn = merge_audit_export(text)
    if audit_warn:
        print("WARN  " + audit_warn, file=sys.stderr)
    folder = default_dir()
    text, round_warn = attach_round(text, folder)
    if round_warn:
        print("WARN  " + round_warn, file=sys.stderr)
    errors = validate(text, for_append=True)
    if errors:
        for e in errors:
            print("FAIL  " + e, file=sys.stderr)
        return 1
    dest = next_path(folder, dt.datetime.now())
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(
            "WARN  trace export write failed: %s (audit chain is source of truth)"
            % exc,
            file=sys.stderr,
        )
        print(render(text))
        return 0
    print("wrote %s" % dest)
    print(render(text))
    print(render_path(text, name=dest.name))
    return 0


def listed_traces(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        p
        for p in folder.glob("????????-???.yaml")
        if p.is_file() and re.match(r"^\d{8}-\d{3}\.yaml$", p.name)
    )


def cmd_list(limit: int) -> int:
    files = listed_traces(default_dir())
    if not files:
        print("no traces")
        return 0
    for path in files[-limit:]:
        text = path.read_text(encoding="utf-8")
        route = block(text, "route")
        ver = field(text, "schema_version") or "?"
        print(
            "%s\tv%s\t%s\t%s\t%s"
            % (
                path.name,
                ver,
                field(route, "module") or "-",
                field(text, "feature") or "-",
                field(text, "intent") or "-",
            )
        )
    return 0


def cmd_last() -> int:
    files = listed_traces(default_dir())
    if not files:
        print("no traces", file=sys.stderr)
        return 1
    path = files[-1]
    print(path)
    rc = cmd_render(str(path))
    if rc == 0:
        print(render_path(path.read_text(encoding="utf-8"), name=path.name))
    return rc


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("file")
    r = sub.add_parser("render")
    r.add_argument("file")
    a = sub.add_parser("append")
    a.add_argument("file", nargs="?", default="-")
    lst = sub.add_parser("list")
    lst.add_argument("-n", type=int, default=20)
    sub.add_parser("last")
    path_p = sub.add_parser("path", help="show actual runtime path for last or given trace")
    path_p.add_argument("file", nargs="?", default=None)
    paths_p = sub.add_parser("paths", help="table of runtime paths for last N traces")
    paths_p.add_argument("-n", type=int, default=20)
    stats_p = sub.add_parser("path-stats", help="frequency of route skeletons / first calls")
    stats_p.add_argument("-n", type=int, default=50)
    args = p.parse_args()
    if args.cmd == "check":
        return cmd_check(args.file)
    if args.cmd == "render":
        return cmd_render(args.file)
    if args.cmd == "append":
        return cmd_append(args.file)
    if args.cmd == "list":
        return cmd_list(args.n)
    if args.cmd == "last":
        return cmd_last()
    if args.cmd == "path":
        return cmd_path(args.file)
    if args.cmd == "paths":
        return cmd_paths(args.n)
    if args.cmd == "path-stats":
        return cmd_path_stats(args.n)
    return 2


if __name__ == "__main__":
    sys.exit(main())
