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
from product_sink import sink_dir  # noqa: E402


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
KINDS = ("route", "gate", "stop", "refuse", "handoff", "call", "open")
CALL_KINDS = ("script", "module", "skill", "repo", "tool")
ITEM_KEYS = (
    "kind",
    "module",
    "chose",
    "why",
    "name",
    "args",
    "result",
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


def dash_maps(text: str, heading: str) -> list[dict[str, str]]:
    body = block(text, heading)
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

    if ver == "2":
        invoke = block(text, "invoke")
        if not invoke:
            errors.append("invoke block missing")
        else:
            if not field(invoke, "trigger"):
                errors.append("invoke.trigger empty")
            if not field(invoke, "matched"):
                errors.append("invoke.matched empty")
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

    # signoff required when this turn claims to write seal/accept marks
    if ver == "2" and for_append:
        write_seal = re.search(
            r"(写入|写上|填入|set|write|mark).{0,16}(sealed|accepted|aligned|resolved)"
            r"|(sealed|accepted|aligned|resolved)\s*:\s*true"
            r"|(status|stage_status)\s*:\s*(sealed|accepted|aligned)",
            text,
            re.I,
        )
        neg = re.search(
            r"(不写|勿写|禁止|do\s*not|don't|refuse|伪造|forge|aligned\s*=\s*false)",
            text,
            re.I,
        )
        if write_seal and not neg:
            so = block(text, "signoff")
            if not so:
                errors.append("signoff block required when writing sealed/accepted/aligned/resolved")
            else:
                st = field(so, "status")
                if st not in ("recorded", "pending"):
                    errors.append("signoff.status must be recorded|pending when writing marks")
                by = field(so, "by")
                if not by or by.lower() in ("agent", "ai", "idev", "bot"):
                    errors.append("signoff.by must be a human id (not agent/ai)")
                if not field(so, "evidence"):
                    errors.append("signoff.evidence empty")


    return errors


def _join(items, empty: str = "—") -> str:
    seq = list(items) if items is not None else []
    return "; ".join(seq) if seq else empty



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
    return {
        "feature": field(text, "feature") or "-",
        "trigger": field(invoke, "trigger") if invoke else "",
        "matched": field(invoke, "matched") if invoke else "",
        "route": " → ".join(route_bits),
        "why": field(route, "why") or "",
        "steps": " → ".join(step_parts) if step_parts else "",
        "calls": " → ".join(call_parts) if call_parts else "(none)",
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
    if seg.get("calls") and seg["calls"] != "(none)":
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
    if seg["steps"]:
        lines.append("steps:    %s" % seg["steps"])
    lines.append("calls:    %s" % seg["calls"])
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
    print("## path-stats (last %d)" % len(files))
    print("### route skeleton")
    for k, n in skel.most_common():
        print("- %s × %d" % (k, n))
    print("### first call")
    for k, n in call0.most_common(15):
        print("- %s × %d" % (k, n))
    print("")
    print("用途: 看哪条场景/模块/首调用最热，便于减负与 shortcut。无分数。")
    return 0


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
        rows = [
            ("intent", field(text, "intent") or "—"),
            ("feature", field(text, "feature") or "—"),
            ("trigger", field(invoke, "trigger") if invoke else "—"),
            ("matched", field(invoke, "matched") if invoke else "—"),
            ("route", route_line or "—"),
            ("why", field(route, "why") or "—"),
            ("rejected", rej),
            ("thinking", field(thinking, "summary") if thinking else "—"),
            ("calls", call_line),
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


def next_path(folder: Path, when: dt.datetime) -> Path:
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
    return folder / ("%s-%03d.yaml" % (prefix, n))


def cmd_check(path: str) -> int:
    text = read_text(path)
    errors = validate(text)
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


def cmd_append(path: str) -> int:
    text = read_text(path)
    if not text.endswith("\n"):
        text += "\n"
    errors = validate(text, for_append=True)
    if errors:
        for e in errors:
            print("FAIL  " + e, file=sys.stderr)
        return 1
    dest = next_path(default_dir(), dt.datetime.now())
    dest.write_text(text, encoding="utf-8")
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
