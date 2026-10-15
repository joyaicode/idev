#!/usr/bin/env python3
"""Delegation records: what was sent, what came back, how long, and whether it holds.

A subagent cannot see the conversation, so when it gets something wrong the
question is always the same: was the brief short, or is the definition
vague? Without a record there is no way to tell, and the only move left is
to retry and hope.

So every delegation lands a record next to run.yaml:

    <ticket home>/workflow/delegations/<step>-<attempt>.yaml

    delegation.py write    --feature F [--file -]   # yaml on stdin
    delegation.py check    --feature F [--step S]   # the five honesty checks
    delegation.py replay   --feature F --step S     # print the brief again
    delegation.py timeline --feature F              # run.yaml + records, in order
    delegation.py eval     --feature F              # the agent-eval counts
    delegation.py list     --feature F

The brief is stored verbatim, never summarized: replay is the whole point.
check exits 1 on a finding. The counts are counts, not a score.

Observability here is read-only aggregation over these records plus the
kernel's run.yaml. There is deliberately no second event log: the kernel
forbids a second ledger, and a view that needs its own copy of the data
drifts from it. timeline joins, it does not record.

Contract: references/agents-evolve.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402
import textwidth as tw  # noqa: E402

sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
try:
    import doc_home  # noqa: E402
except ImportError:
    print(f"BLOCKED cannot import doc_home from {kind_agents.kernel_root()}; set IDEV_ROOT", file=sys.stderr)
    raise SystemExit(2) from None

BRIEF_REQUIRED = ("ticket_home", "repo", "stage", "must_read")
SIGNOFF_FIELDS = ("sealed", "accepted", "aligned", "resolved", "reopen_baseline", "semantic_gate")

STATUS_LINE = re.compile(r"(?mi)^\s*STATUS:\s*(\S+)")
EVIDENCE_LINE = re.compile(r"(?mi)^\s*EVIDENCE:\s*(.+?)\s*$")
# A claim that a signoff field was written. Negations are excluded below.
SIGNOFF_WRITE = re.compile(
    r"(?i)(?:"
    r"(?:" + "|".join(SIGNOFF_FIELDS) + r")\s*[:=]\s*(?:true|ACCEPTED)"
    r"|(?:写入|写上|填入|已写|代写了)\s*(?:" + "|".join(SIGNOFF_FIELDS) + r")"
    r")"
)
SIGNOFF_NEG = re.compile(r"(?i)(?:不写|未写|不碰|没有写|不准写|禁止写|不签|no-signoff-write\s*=\s*PASS)")

# The §0 declarations idev-coder must make, per references/boost.md. The
# whole point of turning coding.md §0 from "read it" into "declare it" is
# that the declaration can be checked — unchecked, it is just a suggestion.
S0_CHANGE_KIND = re.compile(r"(?mi)^\s*CHANGE_KIND:\s*(.+?)\s*$")
S0_CANON_TRIGGER = re.compile(r"(?mi)^\s*CANON_TRIGGER:\s*(.+?)\s*$")
S0_TABLE_HIT = re.compile(r"(?mi)^\s*TABLE_HIT:\s*(.+?)\s*$")
T_NUMBER = re.compile(r"\bT\d+\b")
# Anchored to the start of the value and allowing a parenthesised note, so
# that a row name containing "none" ("§1 nonexistent-row") is not read as a
# zero-hit declaration, and "无(纯追加)" still counts as no trigger.
NO_HIT = re.compile(r"(?i)^\s*(?:零命中|no\s*hit|none|-)\s*(?:[(（].*)?$")
NO_TRIGGER = re.compile(r"(?i)^\s*(?:无|none|-)\s*(?:[(（].*)?$")
STRUCT_GATE = re.compile(r"§\s*3|满足条件|两顶帽子")
APPLIED = re.compile(r"运用|纠正|已改|当轮改")

# references/boost.md 第零节: 本地事实优先。文档会过时而且过时的时候不会
# 告诉你,所以凡是要下判断的步骤都得交代事实是从哪来的。
FACTS_LINE = re.compile(r"(?mi)^\s*FACTS:\s*(.+?)\s*$")
DRIFT_LINE = re.compile(r"(?mi)^\s*DOC_DRIFT:\s*(.+?)\s*$")
# 至少有一个第一手来源。"文档"不算 —— 那正是它不可信的东西。
FIRSTHAND = re.compile(r"(?i)codegraph|源码|源文件|src/|\.py|\.sh|\.java|\.ts|\.go|命令|输出|日志|log|git\b|readlink|realpath|ls -")


def home(feature: str, repo: Path | None) -> Path:
    base = (repo or Path.cwd()).resolve()
    return doc_home.homes(base, feature)["task"]


def dir_for(feature: str, repo: Path | None) -> Path:
    return home(feature, repo) / "workflow" / "delegations"


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def report_status(record: dict) -> str:
    report = record.get("report") or {}
    if report.get("status"):
        return str(report["status"]).upper()
    hit = STATUS_LINE.search(str(report.get("raw", "")))
    return hit.group(1).upper() if hit else ""


def report_evidence(record: dict) -> str:
    report = record.get("report") or {}
    if report.get("evidence"):
        return str(report["evidence"])
    hit = EVIDENCE_LINE.search(str(report.get("raw", "")))
    return hit.group(1).strip() if hit else ""


def duration_of(record: dict) -> int | None:
    """Seconds the agent took, if the conductor timed it."""
    explicit = record.get("duration_s")
    if explicit not in (None, ""):
        try:
            return int(explicit)
        except (TypeError, ValueError):
            return None
    started, finished = record.get("started_at"), record.get("finished_at")
    if not started or not finished:
        return None
    try:
        a = dt.datetime.fromisoformat(str(started))
        b = dt.datetime.fromisoformat(str(finished))
        return max(0, int((b - a).total_seconds()))
    except (TypeError, ValueError):
        return None


def human_secs(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m{seconds % 60:02d}s"



# references/agent-accuracy.md — the guards borrowed from Cursor / Claude Code.
# Each one translates a tool-level constraint those agents enforce into a
# declaration this layer can machine-check.
SCOPE_LINE = re.compile(r"(?mi)^\s*SCOPE:\s*(.+?)\s*$")
READ_LINE = re.compile(r"(?mi)^\s*READ:\s*(.+?)\s*$")
CHANGED_LINE = re.compile(r"(?mi)^\s*CHANGED:\s*(.+?)\s*$")
REVERT_LINE = re.compile(r"(?mi)^\s*REVERT:\s*(.+?)\s*$")
RED_FIRST_LINE = re.compile(r"(?mi)^\s*RED_FIRST:\s*(.+?)\s*$")
ASSUMED_LINE = re.compile(r"(?mi)^\s*ASSUMED:\s*(.+?)\s*$")
# ops: 认产物不能只是声明。A feature defect sends the ticket back to deliver,
# and that is only sound if the symptom was confirmed against *that* build.
ARTIFACT_LINE = re.compile(r"(?mi)^\s*ARTIFACT:\s*(MATCH|AHEAD|UNKNOWN)\b")
# 服务名必须有来源: from the topology, a tool result, or the user — never
# from recall. A name produced from memory is the first link in a chain of
# reasoning about a service that may not exist.
SOURCED = re.compile(
    r"(?i)codegraph|拓扑|topology|工具返回|tool\s*result|用户(?:输入|提供)|"
    r"源码|source|[\w./-]+\.\w+:\d+|日志|\.log\b|监控|metric|trace|"
    r"git\s|配置|\.ya?ml\b|artifact-match")
# A declaration of "nothing", which is a valid answer for every one of these.
NONE_VALUE = re.compile(r"(?i)^\s*(?:无|none|-|n/?a|不适用|0)\s*(?:[(（].*)?$")
# file.ext:symbol — the anchor granularity. "changed service.py" carries no
# information; "service.py:resolve_token" lets the conductor check.
ANCHOR = re.compile(r"[\w./-]+\.\w+:[\w.$<>-]+")


def _paths(value: str) -> set[str]:
    """File paths named in a SCOPE / READ / CHANGED value, anchors stripped."""
    out = set()
    for hit in re.findall(r"[\w./-]+\.\w+", value):
        out.add(hit.split(":")[0])
    return out


def check_accuracy(record: dict) -> dict[str, str]:
    """The accuracy guards. Scoped to the agent and kind that can honour them.

    Only idev-coder declares scope/read/revert — it is the one that edits
    files. The other FACTS agents declare ASSUMED, because reaching a
    judgement on an unverified premise is the failure these catch.
    """
    agent = str(record.get("agent", ""))
    kind = str(record.get("kind", ""))
    raw = str((record.get("report") or {}).get("raw", ""))
    out: dict[str, str] = {}

    if agent in kind_agents.FACTS_AGENTS:
        # Saying "I assumed X" costs one line and saves the conductor from
        # re-verifying the whole report. Writing 无 counts as declaring.
        out["assumption-declared"] = "PASS" if ASSUMED_LINE.search(raw) else "FAIL:no ASSUMED line"

    if agent in kind_agents.FACTS_AGENTS:
        # A FACTS line that names no source kind is indistinguishable from
        # recall. 「禁止凭经验编造」 only bites if the source is stated.
        fm = FACTS_LINE.search(raw)
        if fm and not SOURCED.search(fm.group(1)):
            out["facts-sourced"] = (
                "FAIL:FACTS 没点名来源 —— 服务名/符号名只能来自拓扑(codegraph)、"
                "工具返回、源码或用户输入,禁止凭经验编造")

    if agent == "idev-ops" and kind == "ops.classify":
        # Only for kind=feature: onboard/runtime are handed off, and patrol
        # replays a registered pack, so neither reads product source here.
        if re.search(r"(?mi)^\s*KIND:\s*feature\b", raw):
            out["artifact-verified"] = (
                "PASS" if ARTIFACT_LINE.search(raw)
                else "FAIL:no ARTIFACT: MATCH|AHEAD|UNKNOWN line (artifact-match.py)"
            )

    if agent != "idev-coder":
        return out

    scope = SCOPE_LINE.search(raw)
    read = READ_LINE.search(raw)
    changed = CHANGED_LINE.search(raw)

    out["scope-declared"] = "PASS" if scope else "FAIL:no SCOPE line"

    changed_paths = _paths(changed.group(1)) if changed else set()
    touched = bool(changed_paths) and not NONE_VALUE.match(changed.group(1) if changed else "")

    # scope-held: nothing outside the declared scope. This is the one that
    # catches scope creep — "while I was in there I also fixed...".
    if not scope:
        out["scope-held"] = "WARN:no SCOPE to compare"
    elif not touched:
        out["scope-held"] = "PASS"
    else:
        extra = changed_paths - _paths(scope.group(1))
        out["scope-held"] = "PASS" if not extra else "FAIL:outside SCOPE: " + ",".join(sorted(extra))

    # read-before-change: Claude's Edit enforces this at the tool layer.
    if not touched:
        out["read-before-change"] = "PASS"
    elif not read:
        out["read-before-change"] = "FAIL:no READ line"
    else:
        unread = changed_paths - _paths(read.group(1))
        out["read-before-change"] = "PASS" if not unread else "FAIL:changed unread: " + ",".join(sorted(unread))

    # revert-anchor: a checkpoint, so undoing a delegation is one command.
    if not touched:
        out["revert-anchor"] = "PASS"
    else:
        rev = REVERT_LINE.search(raw)
        if rev and not NONE_VALUE.match(rev.group(1)):
            out["revert-anchor"] = "PASS"
        else:
            out["revert-anchor"] = "FAIL:changed files with no REVERT anchor"

    # Anchors, not bare paths — only a hint, since a path alone is still usable.
    if touched and not ANCHOR.search(changed.group(1)):
        out["anchor-granularity"] = "WARN:CHANGED names files but no file:symbol anchor"

    # red-first: fixing without seeing it red means not knowing what you fixed.
    if kind == "review.fix":
        rf = RED_FIRST_LINE.search(raw)
        out["red-first"] = "PASS" if rf else "FAIL:no RED_FIRST line (evidence.md step 4)"

    return out


def read_evidence(record: dict, repo: Path | None) -> str | None:
    """The evidence file's text. None when the file cannot be found.

    None and "" mean different things and must not be collapsed: an empty
    file is a definite "the T# is not in there" (a finding), while a missing
    one means this check cannot judge from here (a warning).
    """
    evidence = report_evidence(record)
    if not evidence or evidence == "-":
        return None
    base = (repo or Path.cwd()).resolve()
    for candidate in (Path(evidence), base / evidence):
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
    return None


def check_boost(record: dict, repo: Path | None) -> dict[str, str]:
    """The §0 checks from references/boost.md. Only one agent declares these.

    Returns an empty dict for every other agent, so the per-agent contract
    stays with the agent that has it. The name comes from
    kind_agents.S0_AGENT rather than a literal, so agents-check can verify
    it is still on the roster — a rename would otherwise disable these
    checks without a word.

    Note what is NOT checked here: no-premature-abstraction (零命中却新增了
    抽象层) would need to read the diff and judge whether a new interface is
    premature. That is not mechanically decidable, so boost.md asks the
    reviewer and the conductor to catch it instead of pretending otherwise.
    """
    if str(record.get("agent", "")) != kind_agents.S0_AGENT:
        return {}

    raw = str((record.get("report") or {}).get("raw", ""))
    out: dict[str, str] = {}

    change_kind = S0_CHANGE_KIND.search(raw)
    canon = S0_CANON_TRIGGER.search(raw)
    table_hit = S0_TABLE_HIT.search(raw)

    missing = [
        name
        for name, hit in (("CHANGE_KIND", change_kind), ("CANON_TRIGGER", canon), ("TABLE_HIT", table_hit))
        if hit is None
    ]
    if missing:
        # Without the declarations the other three have nothing to check.
        out["s0-declared"] = "FAIL:" + ",".join(missing)
        return out
    out["s0-declared"] = "PASS"

    review = read_evidence(record, repo)

    # canon-walked: a trigger other than 无 means review.md must carry a T#.
    trigger = canon.group(1).strip()
    if NO_TRIGGER.match(trigger):
        out["canon-walked"] = "PASS"
    elif review is None:
        out["canon-walked"] = "WARN"  # review.md not reachable from here
    else:
        out["canon-walked"] = "PASS" if T_NUMBER.search(review) else "FAIL"

    # struct-gated: a structural change must answer §3's 满足条件.
    if "结构" not in change_kind.group(1):
        out["struct-gated"] = "PASS"
    else:
        out["struct-gated"] = "PASS" if STRUCT_GATE.search(raw + (review or "")) else "FAIL"

    # hit-applied: a §1 hit must show up in review.md as applied, not just logged.
    hit_value = table_hit.group(1).strip()
    if NO_HIT.search(hit_value):
        out["hit-applied"] = "PASS"
    elif review is None:
        out["hit-applied"] = "WARN"
    else:
        out["hit-applied"] = "PASS" if APPLIED.search(review) else "FAIL"

    return out


def check_facts(record: dict) -> dict[str, str]:
    """boost.md 第零节的两项:事实从哪来、文档有没有漂移。

    只对会下判断的 agent 生效(排障/论证、编码、审查、红绿)。文档类步骤
    不查 —— 它的产出本身就是文档。
    """
    agent = str(record.get("agent", ""))
    if agent not in kind_agents.FACTS_AGENTS:
        return {}

    raw = str((record.get("report") or {}).get("raw", ""))
    out: dict[str, str] = {}

    facts = FACTS_LINE.search(raw)
    if facts is None:
        out["facts-first"] = "FAIL:no FACTS line"
    elif not FIRSTHAND.search(facts.group(1)):
        # 只写"文档"或"看了一下"不算事实来源。
        out["facts-first"] = "FAIL:no first-hand source (codegraph / 源码 / 命令 / git)"
    else:
        out["facts-first"] = "PASS"

    out["drift-declared"] = "PASS" if DRIFT_LINE.search(raw) else "FAIL:no DOC_DRIFT line"
    return out


def run_checks(record: dict, repo: Path | None) -> dict[str, str]:
    """The honesty checks from agents-evolve.md, plus the per-agent §0 checks."""
    checks: dict[str, str] = {}
    report = record.get("report") or {}
    raw = str(report.get("raw", ""))
    status = report_status(record)

    # 1 evidence-present: a PASS needs a path, and the path should exist.
    evidence = report_evidence(record)
    if status.startswith("PASS"):
        if not evidence or evidence == "-":
            checks["evidence-present"] = "FAIL"
        else:
            base = (repo or Path.cwd()).resolve()
            candidate = Path(evidence)
            exists = candidate.exists() or (base / evidence).exists()
            checks["evidence-present"] = "PASS" if exists else "WARN"
    else:
        checks["evidence-present"] = "PASS"

    # 2 no-signoff-write: an agent must never claim to have signed.
    if SIGNOFF_WRITE.search(raw) and not SIGNOFF_NEG.search(raw):
        checks["no-signoff-write"] = "FAIL"
    else:
        checks["no-signoff-write"] = "PASS"

    # 3 brief-complete: this one points at the conductor, not the agent.
    brief = record.get("brief") or {}
    required = list(BRIEF_REQUIRED)
    if str(record.get("agent", "")) in kind_agents.BOOST_AGENTS:
        # The boost scripts live in idev itself now, so idev_root is the only
        # root there is. Before the merge this was a separate agent_root, and
        # requiring both only gave the conductor one more field to get wrong.
        required.append("idev_root")
    missing = [k for k in required if not str(brief.get(k, "")).strip()]
    checks["brief-complete"] = "PASS" if not missing else "FAIL:" + ",".join(missing)

    # 4 report-parsed: the report has to be machine-readable.
    checks["report-parsed"] = "PASS" if STATUS_LINE.search(raw) else "FAIL"

    # Per-agent §0 declarations (idev-coder only; empty for the rest).
    checks.update(check_boost(record, repo))
    # Local-facts declarations (the judgement-making agents).
    checks.update(check_facts(record))
    # Accuracy guards borrowed from Cursor / Claude Code.
    checks.update(check_accuracy(record))
    return checks


def check_metrics(record: dict) -> list[str]:
    """metrics is a flat map of counts. Nesting it invites a second eval."""
    metrics = record.get("metrics")
    if metrics in (None, "", {}):
        return []
    if not isinstance(metrics, dict):
        return ["metrics must be a map of counts"]
    bad: list[str] = []
    for key, value in metrics.items():
        if isinstance(value, (dict, list)):
            bad.append(f"metrics.{key} must be a number or a short string, not a nested structure")
        elif isinstance(value, str) and len(value) > 60:
            bad.append(f"metrics.{key} is too long; metrics are counts, not prose")
    return bad


def load_all(feature: str, repo: Path | None) -> list[tuple[Path, dict]]:
    """Every record for a feature. A broken file is skipped with a warning.

    Skipping beats raising: these are agent-written files, and one bad
    record must not take down the timeline for the other nineteen.
    """
    out: list[tuple[Path, dict]] = []
    target = dir_for(feature, repo)
    if not target.is_dir():
        return out
    for path in sorted(target.glob("*.yaml")):
        if path.name.endswith(".example.yaml"):
            continue
        data = safeyaml.mapping(path)
        if data is None:
            print(f"WARN unreadable or not a mapping, skipped: {path}", file=sys.stderr)
            continue
        out.append((path, data))
    return out


def load_run(feature: str, repo: Path | None) -> dict | None:
    path = home(feature, repo) / "workflow" / "run.yaml"
    if not path.is_file():
        return None
    data = safeyaml.mapping(path)
    if data is None:
        print(f"WARN unreadable run.yaml, ignored: {path}", file=sys.stderr)
        return None
    return data


def cmd_write(args: argparse.Namespace) -> int:
    if args.file in (None, "-"):
        text = sys.stdin.read()
    else:
        source = Path(args.file)
        if not source.is_file():
            print(f"BLOCKED no such file: {source}", file=sys.stderr)
            return 2
        text = source.read_text(encoding="utf-8", errors="replace")

    record = safeyaml.mapping_from_text(text)
    if record is None:
        print("BLOCKED the record is not valid yaml, or its top level is not a mapping", file=sys.stderr)
        return 2

    for key in ("step", "kind", "agent"):
        if not str(record.get(key, "")).strip():
            print(f"BLOCKED record needs {key}", file=sys.stderr)
            return 2
    kind = str(record["kind"])
    expected = kind_agents.agent_for(kind)
    if expected == kind_agents.CONDUCTOR:
        print(f"BLOCKED kind {kind} is kept by the conductor; it is not delegated", file=sys.stderr)
        return 2
    if str(record["agent"]) != expected:
        print(f"BLOCKED kind {kind} delegates to {expected}, not {record['agent']}", file=sys.stderr)
        return 2

    bad_metrics = check_metrics(record)
    if bad_metrics:
        for item in bad_metrics:
            print("BLOCKED " + item, file=sys.stderr)
        return 2

    record.setdefault("schema_version", 1)
    record.setdefault("feature", args.feature)
    record.setdefault("at", now())
    record.setdefault("attempt", 1)
    record.setdefault("outcome", "recorded")
    record.setdefault("suggest", "")

    attempt = safeyaml.as_int(record.get("attempt"), 1)
    record["attempt"] = attempt
    if attempt > 1 and not str((record.get("brief") or {}).get("prior_failure", "")).strip():
        print("BLOCKED attempt > 1 needs brief.prior_failure (the agent must read it)", file=sys.stderr)
        return 2

    # Timing is optional on purpose: observability must not become a gate.
    # When both ends are present, store the derived duration so views and
    # metrics never have to re-parse timestamps.
    seconds = duration_of(record)
    if seconds is not None:
        record["duration_s"] = seconds

    record["checks"] = run_checks(record, args.repo)

    target = dir_for(args.feature, args.repo)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{record['step']}-{attempt}.yaml"
    path.write_text(safeyaml.dump(record), encoding="utf-8")
    print(f"OK   {path}" + (f"  ({human_secs(seconds)})" if seconds is not None else ""))
    if seconds is None:
        print("HINT no timing: pass started_at + finished_at to make duration observable")

    failed = {k: v for k, v in record["checks"].items() if v.startswith("FAIL")}
    for name, value in failed.items():
        who = "conductor" if name == "brief-complete" else "agent"
        print(f"FAIL {name} = {value}  (责任方: {who})", file=sys.stderr)
    if "no-signoff-write" in failed:
        print("STOP an agent claims it wrote a signoff field; stop the run and raise a proposal", file=sys.stderr)
        return 2
    return 1 if failed else 0


def cmd_check(args: argparse.Namespace) -> int:
    records = load_all(args.feature, args.repo)
    if not records:
        print(f"OK   no delegation records for {args.feature}")
        return 0
    bad = 0
    for path, record in records:
        if args.step and str(record.get("step")) != args.step:
            continue
        checks = run_checks(record, args.repo)
        flags = {k: v for k, v in checks.items() if not v.startswith("PASS")}
        shape = check_metrics(record)
        if shape:
            flags["metrics-shape"] = "FAIL:" + "; ".join(shape)
        label = f"{record.get('step')}-{record.get('attempt', 1)} {record.get('agent')}"
        if not flags:
            print(f"OK   {label}")
            continue
        # WARN is not a failure. evidence-present returns WARN when the path
        # is given but cannot be resolved from here, which happens for a
        # relative path against a different cwd — worth showing, not worth
        # failing the check over.
        if any(v.startswith("FAIL") for v in flags.values()):
            bad += 1
        for name, value in flags.items():
            who = "conductor" if name == "brief-complete" else "agent"
            level = "WARN" if value == "WARN" else "FAIL"
            print(f"{level} {label}: {name} = {value}  (责任方: {who})", file=sys.stderr)
            print(f"     {path}", file=sys.stderr)
    if bad:
        print(f"delegation check: {bad} record(s) with findings", file=sys.stderr)
        return 1
    print(f"delegation check PASS {len(records)} record(s)")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    records = [r for _, r in load_all(args.feature, args.repo) if str(r.get("step")) == args.step]
    if not records:
        print(f"BLOCKED no record for step {args.step}", file=sys.stderr)
        return 2
    record = records[-1]
    brief = record.get("brief") or {}
    print(f"# replay of {record.get('step')}-{record.get('attempt', 1)} -> {record.get('agent')}")
    print(f"# next attempt: {safeyaml.as_int(record.get('attempt'), 1) + 1}")
    print(f"# prior outcome: {report_status(record) or '?'}  ({human_secs(duration_of(record))})")
    print()
    for key in ("ticket_home", "repo", "stage", "risk_tier", "must_read", "idev_root"):
        if brief.get(key):
            print(f"{key}: {brief[key]}")
    if brief.get("with"):
        print(f"with: {brief['with']}")
    print(f"本步: {record.get('step')}  kind={record.get('kind')}")
    prior = report_status(record)
    print(f"prior_failure: {prior} — {(record.get('report') or {}).get('evidence', '') or '见上次留痕'}")
    print("禁止: 写 sealed/accepted/aligned/resolved/reopen_baseline/semantic_gate.*;改密封基线正文")
    print("回报: 按你定义里的回报格式,STATUS + EVIDENCE 必填")
    print()
    print("# 这是打印,不是重派。派不派、派给谁仍是导体的决定。")
    return 0


def cmd_timeline(args: argparse.Namespace) -> int:
    """run.yaml order joined with the delegation records. Read-only."""
    records = [r for _, r in load_all(args.feature, args.repo)]
    run = load_run(args.feature, args.repo)
    by_step: dict[str, list[dict]] = {}
    for record in records:
        by_step.setdefault(str(record.get("step")), []).append(record)
    for items in by_step.values():
        items.sort(key=lambda r: safeyaml.as_int(r.get("attempt"), 1))

    # run.yaml gives the authoritative order; records alone are the fallback,
    # so a missing or stepless run.yaml still shows everything that happened.
    run_steps = (run.get("steps") or []) if run else []

    print(f"# timeline  {args.feature}")
    if run_steps:
        print(f"# run {run.get('workflow_id', '?')}  status={run.get('status', '?')}")
    elif run:
        print(f"# run {run.get('workflow_id', '?')} has no steps; showing records only")
    else:
        print("# no run.yaml; showing records only")
    print()
    header = (
        tw.ljust("步骤", 18) + tw.ljust("kind", 22) + tw.ljust("执行者", 16)
        + tw.ljust("状态", 18) + tw.rjust("耗时", 7) + "  证据"
    )
    print(header)
    print("-" * tw.width(header))

    def from_run(step: str, key: str) -> str:
        return next((str(s.get(key, "")) for s in run_steps if str(s.get("id")) == step), "")

    indent = " " * (18 + 22 + 16)
    ordered = [str(s.get("id")) for s in run_steps]
    # Records whose step is not in run.yaml would otherwise vanish from the
    # view — which is exactly what happens after a recipe renames a step.
    orphans = [s for s in sorted(by_step) if s not in ordered]
    steps = ordered or sorted(by_step)

    def render(step: str, orphan: bool = False) -> None:
        attempts = by_step.get(step, [])
        kind = from_run(step, "kind") or (str(attempts[0].get("kind", "")) if attempts else "")

        if not attempts:
            # Not delegated: either the conductor's own step, or not reached.
            who = "导体" if kind and kind_agents.agent_for(kind) == kind_agents.CONDUCTOR else "—"
            if kind == "human.gate":
                who = "导体(签字)"
            status = from_run(step, "status")
            print(
                tw.ljust(step, 18) + tw.ljust(kind, 22) + tw.ljust(who, 16)
                + tw.ljust(status or "pending", 18) + tw.rjust("-", 7) + "  -"
            )
            return

        for record in attempts:
            attempt = safeyaml.as_int(record.get("attempt"), 1)
            label = step if attempt == 1 else f"{step} #{attempt}"
            if orphan:
                label = f"{label} *"
            status = report_status(record) or "?"
            flags = [k for k, v in (record.get("checks") or {}).items() if str(v).startswith("FAIL")]
            if flags:
                status += "!"
            print(
                tw.ljust(label, 18) + tw.ljust(str(record.get("kind", "")), 22)
                + tw.ljust(str(record.get("agent", "")), 16) + tw.ljust(status, 18)
                + tw.rjust(human_secs(duration_of(record)), 7)
                + "  " + (report_evidence(record) or "-")
            )
            if flags:
                print(f"{indent}↳ check_fail: {', '.join(flags)}")
            if str(record.get("suggest", "")).strip():
                print(f"{indent}↳ suggest: {record['suggest']}")

    for step in steps:
        render(step)
    for step in orphans:
        render(step, orphan=True)

    timed = [d for d in (duration_of(r) for r in records) if d is not None]
    retried = sum(1 for r in records if safeyaml.as_int(r.get("attempt"), 1) > 1)
    fails = sum(1 for r in records for v in (r.get("checks") or {}).values() if str(v).startswith("FAIL"))
    print()
    print(
        f"合计 {len(records)} 次委派"
        + (f",计时 {len(timed)} 次,总 {human_secs(sum(timed))},最慢 {human_secs(max(timed))}" if timed else ",无计时")
        + f";重派 {retried} 次;检查失败 {fails} 项"
    )
    if len(timed) < len(records):
        print(f"HINT {len(records) - len(timed)} 次委派没有计时,耗时视图不完整")
    if orphans:
        print(f"HINT * 的 {len(orphans)} 个 step 不在 run.yaml 里(配方改过 step id?),按 step 名排在最后")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    records = [r for _, r in load_all(args.feature, args.repo)]
    by_agent: Counter[str] = Counter()
    blocked: Counter[str] = Counter()
    checks: Counter[str] = Counter()
    produced: Counter[str] = Counter()
    retried = rejected = suggests = 0
    durations: list[int] = []

    for record in records:
        by_agent[str(record.get("agent", "?"))] += 1
        status = report_status(record)
        if status.startswith("BLOCKED"):
            hit = re.search(r"BLOCKED\((\w+)\)", status)
            blocked[hit.group(1) if hit else "unclassified"] += 1
        if safeyaml.as_int(record.get("attempt"), 1) > 1:
            retried += 1
        if str(record.get("outcome")) == "rejected":
            rejected += 1
        if str(record.get("suggest", "")).strip():
            suggests += 1
        for name, value in (record.get("checks") or {}).items():
            if str(value).startswith("FAIL"):
                checks[name] += 1
        seconds = duration_of(record)
        if seconds is not None:
            durations.append(seconds)
        for key, value in (record.get("metrics") or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                produced[str(key)] += int(value)

    print("## agent-eval")
    print()
    print(f"- delegated: {len(records)}")
    print(f"- by_agent: {dict(by_agent) or '{}'}")

    # How many steps the conductor kept, from run.yaml: the denominator for
    # "how much of this run was delegated at all".
    run = load_run(args.feature, args.repo)
    if run is not None:
        kept = sum(
            1
            for s in (run.get("steps") or [])
            if kind_agents.agent_for(str(s.get("kind", ""))) == kind_agents.CONDUCTOR
        )
        print(f"- conductor_kept: {kept}")
    else:
        print("- conductor_kept: 无 run.yaml")

    print(f"- blocked: {sum(blocked.values())} {dict(blocked) or ''}".rstrip())
    print(f"- retried: {retried}")
    print(f"- rejected: {rejected}")
    print(f"- check_fail: {dict(checks) or '{}'}")
    print(f"- suggest: {suggests}")
    if durations:
        print(
            f"- duration_s: n={len(durations)} total={sum(durations)} "
            f"p50={int(statistics.median(durations))} max={max(durations)}"
        )
    else:
        print("- duration_s: 无计时")
    if produced:
        print(f"- produced: {dict(produced)}")
    print()
    print("件数,不打分。结构好不好由人在拷问里评。")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    records = load_all(args.feature, args.repo)
    if not records:
        print("(no delegation records)")
        return 0
    for _path, record in records:
        status = report_status(record) or "?"
        flags = [k for k, v in (record.get("checks") or {}).items() if str(v).startswith("FAIL")]
        extra = ("  check_fail=" + ",".join(flags)) if flags else ""
        print(
            f"{record.get('step')}-{record.get('attempt',1):<2} {str(record.get('agent')):14} "
            f"{status:16} {human_secs(duration_of(record)):>7}{extra}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("write", help="store one delegation record (yaml on stdin)")
    p.add_argument("--feature", required=True)
    p.add_argument("--file", help="yaml file, or - for stdin (default)")
    p.set_defaults(fn=cmd_write)

    p = sub.add_parser("check", help="run the five honesty checks")
    p.add_argument("--feature", required=True)
    p.add_argument("--step")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("replay", help="print the brief again for another attempt")
    p.add_argument("--feature", required=True)
    p.add_argument("--step", required=True)
    p.set_defaults(fn=cmd_replay)

    p = sub.add_parser("timeline", help="run.yaml order joined with the records")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_timeline)

    p = sub.add_parser("eval", help="print the agent-eval counts")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_eval)

    p = sub.add_parser("list", help="list records for a feature")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_list)

    args = parser.parse_args()
    if args.repo is None and os.environ.get("IDEV_PRODUCT_REPO"):
        args.repo = Path(os.environ["IDEV_PRODUCT_REPO"])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
