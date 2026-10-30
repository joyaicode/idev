#!/usr/bin/env python3
"""Delegation records: what was sent, what came back, how long, and whether it holds.

A subagent cannot see the conversation, so when it gets something wrong the
question is always the same: was the brief short, or is the definition
vague? Without a record there is no way to tell, and the only move left is
to retry and hope.

So every delegation lands a record next to run.yaml:

    <ticket home>/workflow/delegations/<run_id>/<step>-<attempt>.yaml
    A fanout shard uses <step>-<shard>-<attempt>.yaml so one step can keep
    every shard's brief. The step is still recorded once, after merge.
    Records from another run of the same feature stay in their own directory,
    so a new review does not collide with report-1.yaml from last time.
    A run without run_id still writes the flat delegations/ directory.
    The layout lives in lib/record_paths.py; every reader asks it too.

    delegation.py write    --feature F [--file -]   # yaml on stdin
    delegation.py dir      --feature F              # where this run's records go
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
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import delegation_return  # noqa: E402
import idev_bin  # noqa: E402
import java_hygiene  # noqa: E402
import kind_agents  # noqa: E402
import record_paths  # noqa: E402
import safeyaml  # noqa: E402
import textwidth as tw  # noqa: E402
import yaml_representers  # noqa: E402

sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
try:
    import doc_home  # noqa: E402
except ImportError:
    print(f"BLOCKED cannot import doc_home from {kind_agents.kernel_root()}; set IDEV_ROOT", file=sys.stderr)
    raise SystemExit(2) from None

BRIEF_REQUIRED = ("ticket_home", "repo", "stage", "must_read")
SIGNOFF_FIELDS = ("sealed", "accepted", "aligned", "resolved", "reopen_baseline", "semantic_gate")
# The agent writes SUGGEST: in the report body; everything downstream read a
# top-level `suggest` key that nothing ever set. This is the channel agents
# use to say "your definition is unclear here" — the input to improving it.
SUGGEST_LINE = delegation_return.line_field("SUGGEST")
# GUIDE is a domain constraint for another role. DOMAIN names who to consult
# when this step is BLOCKED(domain). Empty and 「无」 stay empty: neither is a gate.
GUIDE_LINE = delegation_return.line_field("GUIDE")
DOMAIN_LINE = delegation_return.line_field("DOMAIN")
# What the agent concluded. Kept apart from SUGGEST, which is advice about
# the layer itself and the only one of the two a weekly review turns into a proposal.
CONCLUSION_LINE = delegation_return.line_field("CONCLUSION")

STATUS_LINE = delegation_return.line_field("STATUS", r"(\S+)")
EVIDENCE_LINE = delegation_return.line_field("EVIDENCE")
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
S0_CHANGE_KIND = delegation_return.line_field("CHANGE_KIND")
S0_CANON_TRIGGER = delegation_return.line_field("CANON_TRIGGER")
S0_TABLE_HIT = delegation_return.line_field("TABLE_HIT")
T_NUMBER = re.compile(r"\bT\d+\b")
# Anchored to the start of the value and allowing a parenthesised note, so
# that a row name containing "none" ("§1 nonexistent-row") is not read as a
# zero-hit declaration, and "无(纯追加)" still counts as no trigger.
NO_HIT = re.compile(r"(?i)^\s*(?:零命中|无命中|无|no\s*hit|none|-)\s*(?:[(（].*)?$")
NO_TRIGGER = re.compile(r"(?i)^\s*(?:无|none|-)\s*(?:[(（].*)?$")
STRUCT_GATE = re.compile(r"§\s*3|满足条件|两顶帽子")
APPLIED = re.compile(r"运用|纠正|已改|当轮改")

# references/boost.md 第零节: 本地事实优先。文档会过时而且过时的时候不会
# 告诉你,所以凡是要下判断的步骤都得交代事实是从哪来的。
FACTS_LINE = delegation_return.line_field("FACTS")
DRIFT_LINE = delegation_return.line_field("DOC_DRIFT")
# 至少有一个第一手来源。"文档"不算 —— 那正是它不可信的东西。
FIRSTHAND = re.compile(r"(?i)codegraph|源码|源文件|src/|\.py|\.sh|\.java|\.ts|\.go|命令|输出|日志|log|git\b|readlink|realpath|ls -")


def home(feature: str, repo: Path | None) -> Path:
    base = (repo or Path.cwd()).resolve()
    return doc_home.homes(base, feature)["task"]


def dir_for(feature: str, repo: Path | None) -> Path:
    return home(feature, repo) / "workflow" / "delegations"


def record_dir(feature: str, repo: Path | None) -> Path:
    """Where this run's records go. A run_id gets its own directory."""
    return record_paths.run_dir(dir_for(feature, repo), load_run(feature, repo))


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def checker_version() -> str:
    """The ruler a record's checks were measured with: a digest of the checker's source."""
    lib = Path(__file__).resolve().parent / "lib"
    files = [Path(__file__).resolve()]
    files += [lib / name for name in ("kind_agents.py", "_generated_kinds.py", "delegation_return.py", "java_hygiene.py")]
    files += sorted(delegation_return.SCHEMA_DIR.glob("*.schema.json"))
    digest = hashlib.sha256()
    for path in files:
        if path.is_file():
            digest.update(path.name.encode("utf-8") + b"\0" + path.read_bytes())
    return digest.hexdigest()[:12]


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
SCOPE_LINE = delegation_return.line_field("SCOPE")
READ_LINE = delegation_return.line_field("READ")
CHANGED_LINE = delegation_return.line_field("CHANGED")
REVERT_LINE = delegation_return.line_field("REVERT")
RED_FIRST_LINE = delegation_return.line_field("RED_FIRST")
ASSUMED_LINE = delegation_return.line_field("ASSUMED")
# One assumption per ASSUMED line, tagged by whether the conclusion rests on
# it. Only a load-bearing one stops the run for a person's decision.
LOAD_BEARING = "[承重]"
NOT_LOAD_BEARING = "[非承重]"
# ops: 认产物不能只是声明。A feature defect sends the ticket back to deliver,
# and that is only sound if the symptom was confirmed against *that* build.
ARTIFACT_LINE = delegation_return.line_field("ARTIFACT", r"(MATCH|AHEAD|UNKNOWN)\b")
# 服务名必须有来源: from the topology, a tool result, or the user — never
# from recall. A name produced from memory is the first link in a chain of
# reasoning about a service that may not exist.
SOURCED = re.compile(
    r"(?i)codegraph|拓扑|topology|工具返回|tool\s*result|用户(?:输入|提供)|"
    r"源码|source|[\w./-]+\.\w+:\d+|日志|\.log\b|监控|metric|trace|"
    r"git\s|配置|\.ya?ml\b|artifact-match")
# A declaration of "nothing", which is a valid answer for every one of these.
NONE_VALUE = re.compile(r"(?i)^\s*(?:无|none|-|n/?a|不适用|0)\s*(?:[(（].*)?$")


def optional_line(raw: str, pattern: re.Pattern[str]) -> str:
    """A report line's value, or empty when the line is missing or explicitly none."""
    hit = pattern.search(raw)
    if not hit:
        return ""
    value = hit.group(1).strip()
    if not value or NONE_VALUE.match(value):
        return ""
    return value


def lift(raw: str) -> dict[str, str]:
    """The one-line fields a report carries beside its checks, each from its own line."""
    return {
        "suggest": optional_line(raw, SUGGEST_LINE),
        "guide": optional_line(raw, GUIDE_LINE),
        "domain": optional_line(raw, DOMAIN_LINE),
        "conclusion": optional_line(raw, CONCLUSION_LINE),
    }


SUGGEST_LABEL = delegation_return.line_field("SUGGEST", "")


def suggestion_of(record: dict) -> str:
    """SUGGEST as the current reader sees it.

    The stored field is only trusted when the report has no SUGGEST line:
    records written before the reader kept to its own line hold whatever
    came next (often CONCLUSION) there.
    """
    raw = str((record.get("report") or {}).get("raw", ""))
    if SUGGEST_LABEL.search(raw):
        return lift(raw)["suggest"]
    return str(record.get("suggest") or "").strip()


def has_telemetry(record: dict) -> bool:
    return all(
        isinstance(record.get(key), (int, float)) and not isinstance(record.get(key), bool)
        for key in ("duration_ms", "tool_call_count")
    )


# file.ext:symbol — the anchor granularity. "changed service.py" carries no
# information; "service.py:resolve_token" lets the conductor check.
ANCHOR = re.compile(r"[\w./-]+\.\w+:[\w.$<>-]+")


def _paths(value: str) -> set[str]:
    """File paths named in a SCOPE / READ / CHANGED value, anchors stripped."""
    out = set()
    for hit in re.findall(r"[\w./-]+\.\w+", value):
        out.add(hit.split(":")[0])
    return out


def _review_write(path: str) -> bool:
    """A reviewer may only name the review artifact, including a shard of it."""
    norm = path.replace("\\", "/")
    if norm == "review.md" or norm.endswith("/review.md"):
        return True
    return "/review/shards/" in f"/{norm}" and norm.endswith(".md")


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
        out["assumption-declared"] = (
            "PASS" if ASSUMED_LINE.search(raw)
            else "FAIL:ASSUMED 行缺失或为空 —— 列出这轮没验、但结论依赖的前提;"
                 "没有就写「无」。导体只需核那一条,比重验整份回报便宜")
        untagged = [
            value for value in ASSUMED_LINE.findall(raw)
            if not NONE_VALUE.match(value)
            and not value.startswith((LOAD_BEARING, NOT_LOAD_BEARING))
        ]
        out["assumption-tagged"] = (
            "PASS" if not untagged
            else "FAIL:ASSUMED 没标 [承重] / [非承重]:" + ";".join(untagged)[:120]
                 + " —— 一行一条,结论依赖它就标 [承重](会停下请人决定),否则标 [非承重]")

    if agent in kind_agents.FACTS_AGENTS:
        # A FACTS line that names no source kind is indistinguishable from
        # recall. 「禁止凭经验编造」 only bites if the source is stated.
        fm = FACTS_LINE.search(raw)
        if fm:
            # Explicit PASS: a check that only speaks when it fails makes
            # "checked and clean" indistinguishable from "never ran" in the
            # records — the false-green this layer keeps guarding against.
            out["facts-sourced"] = (
                "PASS" if SOURCED.search(fm.group(1))
                else "FAIL:FACTS 没点名来源 —— 服务名/符号名只能来自拓扑(codegraph)、"
                     "工具返回、源码或用户输入,禁止凭经验编造")
        # No FACTS line at all is facts-first's finding, not this one's.

    if agent == "idev-ops" and kind == "ops.classify":
        # Only for kind=feature: onboard/runtime are handed off, and patrol
        # replays a registered pack, so neither reads product source here.
        if re.search(r"(?mi)^\s*KIND:\s*feature\b", raw):
            out["artifact-verified"] = (
                "PASS" if ARTIFACT_LINE.search(raw)
                else "FAIL:no ARTIFACT: MATCH|AHEAD|UNKNOWN line (artifact-match.py)"
            )

    if agent == "idev-reviewer":
        # The reviewer reads independent evidence. Naming any other file in
        # CHANGED means they moved the gate (tests, plan, product code).
        # No CHANGED line stays silent: older reports did not have the field.
        changed = CHANGED_LINE.search(raw)
        if changed:
            text = changed.group(1).strip()
            paths = _paths(text)
            if NONE_VALUE.match(text) or not paths:
                out["gate-held"] = "PASS"
            else:
                extra = sorted(p for p in paths if not _review_write(p))
                out["gate-held"] = (
                    "PASS" if not extra
                    else "FAIL:审查者改了 " + ",".join(extra)
                         + " —— CHANGED 只许 review.md 和 review/shards/。"
                           "测试、用例门槛和产品代码留给生成者"
                )

    if agent != "idev-coder":
        return out

    scope = SCOPE_LINE.search(raw)
    read = READ_LINE.search(raw)
    changed = CHANGED_LINE.search(raw)

    out["scope-declared"] = (
        "PASS" if scope
        else "FAIL:没有 SCOPE 行 —— 动手前先写明这轮打算改哪些 file:symbol。"
             "它和 CHANGED 对照,挡的是「顺手又改了三处」")

    changed_paths = _paths(changed.group(1)) if changed else set()
    touched = bool(changed_paths) and not NONE_VALUE.match(changed.group(1) if changed else "")

    # scope-held: nothing outside the declared scope. This is the one that
    # catches scope creep — "while I was in there I also fixed...".
    if not scope:
        out["scope-held"] = "WARN:没有 SCOPE 可对照 —— 先补 SCOPE 行,这项才有意义"
    elif not touched:
        out["scope-held"] = "PASS"
    else:
        extra = changed_paths - _paths(scope.group(1))
        out["scope-held"] = (
            "PASS" if not extra
            else "FAIL:改了 SCOPE 之外的 " + ",".join(sorted(extra))
                 + " —— 要么把它们写进 SCOPE 并说明为什么本轮必须一起改,"
                   "要么撤掉这部分改动另开一轮。顺手改的那几处,正是别人假设没变的地方")

    # read-before-change: Claude's Edit enforces this at the tool layer.
    if not touched:
        out["read-before-change"] = "PASS"
    elif not read:
        out["read-before-change"] = (
            "FAIL:改了文件却没有 READ 行 —— 列出动手前读过的 file:symbol。"
            "改一个没读过的地方,多半是按名字猜它在干什么")
    else:
        unread = changed_paths - _paths(read.group(1))
        out["read-before-change"] = (
            "PASS" if not unread
            else "FAIL:改了没读过的 " + ",".join(sorted(unread))
                 + " —— 先读再改,然后把 file:symbol 补进 READ。"
                   "名字和文档都不可信,只有读过那段代码才知道它在干什么")

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

    # Phase 1 §4: when the subagentStop hook logged modified_files, CHANGED
    # must be a subset. No log → skip (fail open); the hook is best-effort.
    if touched:
        actual = _recent_modified_files()
        if actual is not None:
            extra = changed_paths - actual
            out["changed-within-actual"] = (
                "PASS" if not extra
                else "FAIL:CHANGED names " + ",".join(sorted(extra))
                     + " but subagentStop did not see those modifications"
            )

    return out


def _subagent_stops_path() -> Path:
    raw = (os.environ.get("IDEV_DATA") or "").strip()
    root = Path(raw).expanduser() if raw else Path.home() / ".idev"
    return root / "subagent-stops.jsonl"


def _stop_rows() -> list[dict]:
    """Every parseable row of subagent-stops.jsonl, oldest first."""
    path = _subagent_stops_path()
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _moment(value: object) -> dt.datetime | None:
    try:
        when = dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.astimezone()


def stop_id(row: dict) -> str:
    """Rows from before the hook stamped an id are told apart by their time."""
    return str(row.get("id") or row.get("at") or "")


def _holds(roots: object, repo: Path) -> bool:
    if not isinstance(roots, list) or not roots:
        return True
    for root in roots:
        base = Path(str(root)).expanduser().resolve()
        if repo == base or base in repo.parents or repo in base.parents:
            return True
    return False


STOP_LOOKBACK = dt.timedelta(hours=6)


def stop_for(record: dict, repo: Path, taken: set[str]) -> dict | None:
    """This delegation's subagentStop row, or None.

    The newest row is not enough: parallel delegations stop in any order, and
    a retry recorded without a stop of its own would copy the first attempt's
    time. A row counts when its subagent_type is the record's agent, its
    workspace holds the repo, no other record took it, and it fell inside the
    delegation: after started_at (the last six hours without one) and before
    finished_at plus a minute.
    """
    agent = str(record.get("agent") or "")
    now = dt.datetime.now().astimezone()
    started, finished = _moment(record.get("started_at")), _moment(record.get("finished_at"))
    earliest = started or now - STOP_LOOKBACK
    latest = finished + dt.timedelta(minutes=1) if finished else now
    for row in reversed(_stop_rows()):
        when = _moment(row.get("at"))
        if (
            str(row.get("subagent_type") or "") == agent
            and when is not None and earliest <= when <= latest
            and stop_id(row) not in taken
            and _holds(row.get("workspace_roots"), repo)
        ):
            return row
    return None


def _recent_modified_files() -> set[str] | None:
    """Union of modified_files from the newest subagent-stops.jsonl rows, or None."""
    path = _subagent_stops_path()
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    found: set[str] = set()
    saw = False
    for line in lines[-20:]:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        files = row.get("modified_files") or []
        if isinstance(files, list):
            saw = True
            for f in files:
                if str(f).strip():
                    found.add(str(f).strip().replace("\\", "/"))
    return found if saw else None


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
        out["hit-applied"] = "WARN:no review.md to check the hit against"
    else:
        # Say what is missing. A bare FAIL here used to leave the agent
        # guessing between "write it differently" and "go fix the code".
        out["hit-applied"] = (
            "PASS" if APPLIED.search(review)
            else f"FAIL:TABLE_HIT 写了「{hit_value[:30]}」,但 review.md 里看不到"
                 "「运用 / 纠正 / 已改 / 当轮改」—— 命中必须当轮改掉,不能只记账。"
                 "若其实是零命中,写「零命中」或「无」")

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
        out["facts-first"] = (
            "FAIL:没有 FACTS 行 —— 写你这轮的结论建立在什么第一手材料上:"
            "codegraph 查到的符号 / 读过的源码 file:line / 跑过的命令 / git 记录。"
            "「看了文档」不算 —— 文档会过时,见 references/boost.md 第零节")
    elif not FIRSTHAND.search(facts.group(1)):
        # 只写"文档"或"看了一下"不算事实来源。
        out["facts-first"] = "FAIL:no first-hand source (codegraph / 源码 / 命令 / git)"
    else:
        out["facts-first"] = "PASS"

    out["drift-declared"] = (
        "PASS" if DRIFT_LINE.search(raw)
        else "FAIL:没有 DOC_DRIFT 行 —— 文档与代码不符时要说出来(写清哪一页哪一句);"
             "没遇到就写「无」。沉默会让下一个人再踩一次")
    return out


def _hygiene_covers(rel: str, changed: set[str]) -> bool:
    """True when a diff hit is one of the files this coder says they changed."""
    hit = rel.replace("\\", "/")
    base = hit.rsplit("/", 1)[-1]
    for raw in changed:
        path = raw.replace("\\", "/")
        if path in (hit, base) or hit.endswith("/" + path) or path.endswith("/" + base):
            return True
    return False


def check_java_hygiene(record: dict, repo: Path | None) -> dict[str, str]:
    """java.md yellow bars the reviewer used to skip in favor of a principle essay.

    The coder's code_pass / review.fix must already have cleared them in
    CHANGED files. The reviewer's report must cite every remaining diff hit
    as file:line before the cohesion writeup counts. Problems-only rows
    (unused import, unused method) are not in this check.
    """
    agent = str(record.get("agent") or "")
    kind = str(record.get("kind") or "")
    reviewer = agent == "idev-reviewer" and kind == "review.report"
    coder = agent == "idev-coder" and kind in ("deliver.code_pass", "review.fix")
    if not reviewer and not coder:
        return {}
    if repo is None:
        return {"java-hygiene": "WARN:no repo, diff not scanned"}
    try:
        hits, scope, _level = java_hygiene.scan(Path(repo))
    except OSError as exc:
        return {"java-hygiene": f"WARN:{exc}"}
    if scope == "no git":
        return {"java-hygiene": "WARN:不是 git 仓库，扫不到 diff"}
    if coder:
        raw = str((record.get("report") or {}).get("raw", ""))
        changed = CHANGED_LINE.search(raw)
        paths = _paths(changed.group(1)) if changed else set()
        owed = [
            hit
            for hit in hits
            if hit.rule in java_hygiene.BLOCKING_RULES and _hygiene_covers(hit.rel, paths)
        ]
        if not owed:
            return {"java-hygiene": "PASS"}
        shown = "; ".join(f"{hit.token()} {hit.rule}" for hit in owed[:8])
        extra = f" (+{len(owed) - 8})" if len(owed) > 8 else ""
        return {
            "java-hygiene": (
                "FAIL:本轮改过的 Java 仍有 java.md 黄条，先改掉再写总则: "
                + shown
                + extra
            )
        }
    review = read_evidence(record, repo)
    if review is None:
        return {"java-hygiene": "WARN:review.md 打不开，对不上黄条"}
    owed = java_hygiene.missing(hits, review, str(record.get("shard") or ""))
    if not owed:
        return {"java-hygiene": "PASS"}
    shown = "; ".join(f"{hit.token()} {hit.rule}" for hit in owed[:8])
    extra = f" (+{len(owed) - 8})" if len(owed) > 8 else ""
    return {
        "java-hygiene": (
            f"FAIL:{scope} 有 {len(owed)} 条黄条没写进 review.md，"
            "先把 file:line 写成 I*，再写内聚和设计模式: "
            + shown
            + extra
        )
    }


# Checks that read the checkout: evidence on disk, review.md, the diff. Their
# verdict belongs to the checkout as it was when the record was written, so a
# later measurement keeps the stored one instead of reading today's tree.
CHECKOUT_CHECKS = frozenset({"evidence-present", "canon-walked", "struct-gated", "hit-applied", "java-hygiene"})


def remeasure(record: dict) -> dict[str, str]:
    """The record's checks by the current checker; checkout checks as stored."""
    stored = record.get("checks") or {}
    measured = {k: v for k, v in run_checks(record, None).items() if k not in CHECKOUT_CHECKS}
    measured.update({k: str(v) for k, v in stored.items() if k in CHECKOUT_CHECKS})
    return measured


def run_checks(record: dict, repo: Path | None) -> dict[str, str]:
    """The honesty checks from agents-evolve.md, plus the per-agent §0 checks."""
    checks: dict[str, str] = {}
    report = record.get("report") or {}
    raw = str(report.get("raw", ""))
    status = report_status(record)

    # Structured return (phase 1 §7). When JSON is present it is the main path:
    # schema fields win over prose lines. Absent → WARN unless required.
    require_json = (os.environ.get("IDEV_REQUIRE_RETURN_JSON") or "").strip() in (
        "1", "true", "yes",
    )
    checks["return-schema"] = delegation_return.check_report(raw, require=require_json)
    structured, _ = delegation_return.extract(raw)
    if structured and checks["return-schema"] == "PASS":
        raw = delegation_return.apply_as_main(raw, structured)
        report = dict(report)
        report["raw"] = raw
        evidence = structured.get("evidence")
        if evidence:
            if isinstance(evidence, list):
                report["evidence"] = " ".join(str(p) for p in evidence if str(p).strip())
            else:
                report["evidence"] = str(evidence).strip()
        if structured.get("status"):
            report["status"] = structured["status"]
        record = dict(record)
        record["report"] = report
        if structured.get("changed") is not None:
            record["changed"] = list(structured["changed"])

    # 1 evidence-present: a PASS needs a path, and the path should exist.
    evidence = report_evidence(record)
    if status.startswith("PASS"):
        if not evidence or evidence == "-":
            # These two are the most important checks in the file, and they
            # used to answer with a bare "FAIL" — the agent could not tell
            # whether it wrote the wrong thing or did the wrong thing.
            checks["evidence-present"] = (
                "FAIL:STATUS 是 PASS 却没有 EVIDENCE 路径 —— "
                "PASS 要能被别人打开看。写产出文件的路径(报告 / 日志 / plan),"
                "不是一句话描述")
        else:
            base = (repo or Path.cwd()).resolve()
            candidate = Path(evidence)
            exists = candidate.exists() or (base / evidence).exists()
            checks["evidence-present"] = (
                "PASS" if exists
                else f"WARN:EVIDENCE 指向 {evidence},但在 {base} 下找不到 —— "
                     "路径写错了,还是文件没真的产出?")
    else:
        checks["evidence-present"] = "PASS"

    # 2 no-signoff-write: an agent must never claim to have signed.
    if SIGNOFF_WRITE.search(raw) and not SIGNOFF_NEG.search(raw):
        hit = SIGNOFF_WRITE.search(raw)
        checks["no-signoff-write"] = (
            f"FAIL:回报里出现「{hit.group(0)[:30]}」—— 签字字段只有导体能写。"
            "检查过了由导体落笔，不向人要确认。你要做的是把事实回报上去。")
    else:
        checks["no-signoff-write"] = "PASS"

    # 3 brief-complete: this one points at the conductor, not the agent.
    brief = record.get("brief") or {}
    required = list(BRIEF_REQUIRED)
    # ops.classify on a feature defect must confirm the artifact matches the
    # source (artifact-verified). An agent that was never told which artifact
    # is running can only come back BLOCKED — so the brief has to carry it,
    # and failing here points at the conductor rather than wasting a round.
    if str(record.get("kind", "")) == "ops.classify":
        required.append("artifact")
    if str(record.get("agent", "")) in kind_agents.BOOST_AGENTS:
        # The boost scripts live in idev itself now, so idev_root is the only
        # root there is. Before the merge this was a separate agent_root, and
        # requiring both only gave the conductor one more field to get wrong.
        required.append("idev_root")
    missing = [k for k in required if not str(brief.get(k, "")).strip()]
    checks["brief-complete"] = (
        "PASS" if not missing
        else "FAIL:委派包缺 " + ",".join(missing)
             + " —— **这是导体的问题,不是执行者的**。格式照抄 "
               "references/agents.md「委派包(固定格式)」;重派前用 "
               "`delegation.py replay` 取回上次那份,别凭记忆重组")

    # 4 report-parsed: the report has to be machine-readable.
    checks["report-parsed"] = (
        "PASS" if STATUS_LINE.search(raw)
        else "FAIL:回报里找不到 STATUS 行 —— 第一行写 "
             "`STATUS: PASS|FAIL|UNPROVEN|BLOCKED(brief|env|logic|domain)`。"
             "没有它,导体无法机读这次委派的结果")

    # Per-agent §0 declarations (idev-coder only; empty for the rest).
    checks.update(check_boost(record, repo))
    # Local-facts declarations (the judgement-making agents).
    checks.update(check_facts(record))
    # Accuracy guards borrowed from Cursor / Claude Code.
    checks.update(check_accuracy(record))
    hygiene = check_java_hygiene(record, repo)
    if "java-hygiene" in hygiene:
        checks["java-hygiene"] = hygiene["java-hygiene"]
    return checks


def _consult_brief(record: dict) -> bool:
    brief = record.get("brief") or {}
    if not isinstance(brief, dict):
        return False
    if str(brief.get("咨询") or "").strip():
        return True
    return bool(re.search(r"(?m)^咨询\s*:", str(brief.get("raw") or "")))


def domain_directive(record: dict) -> list[str]:
    """Conductor follow-ups for GUIDE and BLOCKED(domain).

    These are not person signals. A valid domain block names another executor
    and prints CONSULT. A consult that is itself blocked does not nest. A
    missing or self domain is sent back as a rebrief. A non-empty GUIDE is
    copied verbatim into the next brief.
    """
    lines: list[str] = []
    guide = str(record.get("guide") or "").strip()
    if guide:
        lines.append(
            "HANDOFF guide: "
            + guide
            + "  (copy verbatim into the next brief as 领域约束:; do not rewrite)"
        )
    if report_status(record) != "BLOCKED(DOMAIN)":
        return lines
    if _consult_brief(record):
        lines.append(
            "CONSULT none  (this brief is already 咨询; do not delegate again; "
            "ask the person, same as BLOCKED(logic))"
        )
        return lines
    domain = str(record.get("domain") or "").strip()
    agent = str(record.get("agent") or "").strip()
    if domain in kind_agents.AGENTS and domain != agent:
        lines.append(
            f"CONSULT {domain}  (delegate once with 咨询: {record.get('step')}; "
            "they return GUIDE and EVIDENCE only; do not ask the person; do not nest)"
        )
        return lines
    if not domain:
        why = "missing"
    elif domain == agent:
        why = "self"
    else:
        why = "not an executor"
    lines.append(
        f"REBRIEF domain {why}  (send this step back as BLOCKED(brief); "
        "do not consult; do not ask the person)"
    )
    return lines


def signals_of(record: dict) -> list[str]:
    """What in this report needs a person's decision before the step passes."""
    raw = str((record.get("report") or {}).get("raw", ""))
    out = []
    if report_status(record) == "BLOCKED(LOGIC)":
        out.append("BLOCKED(logic)")
    if report_status(record) == "BLOCKED(DOMAIN)" and _consult_brief(record):
        out.append("consult does not nest")
    out += [v for v in ASSUMED_LINE.findall(raw) if v.startswith(LOAD_BEARING)]
    # AHEAD has a fixed next move (read the artifact's commit); UNKNOWN means
    # nobody can say which code is running until a person supplies it.
    artifact = ARTIFACT_LINE.search(raw)
    if artifact and artifact.group(1).upper() == "UNKNOWN":
        out.append("ARTIFACT UNKNOWN")
    return out


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
    files = [path for leaf in record_paths.LEAVES for path in target.glob(leaf)]
    for path in sorted(files):
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


def record_name(step: str, attempt: int, shard: str = "") -> str:
    """One file per step attempt. A shard adds its id so siblings do not collide."""
    if shard:
        if not record_paths.is_slug(shard):
            raise ValueError(shard)
        return f"{step}-{shard}-{attempt}.yaml"
    return f"{step}-{attempt}.yaml"


def verify_record_name(step: str, attempt: int, shard: str = "") -> str:
    """A verifier's record sits beside the writer's attempt it checked."""
    return record_name(step, attempt, shard).removesuffix(".yaml") + ".verify.yaml"


def is_verifier(record: dict) -> bool:
    return str(record.get("role") or "").strip().lower() == "verifier"


def writer_record(folder: Path, step: str, shard: str = "") -> dict | None:
    """The newest writer record of a step in one run's directory."""
    best: tuple[int, dict] | None = None
    for path in record_paths.records(folder):
        data = safeyaml.mapping(path) or {}
        if str(data.get("step")) != step or is_verifier(data):
            continue
        if str(data.get("shard") or "").strip() != shard:
            continue
        attempt = safeyaml.as_int(data.get("attempt"), 1)
        if best is None or attempt > best[0]:
            best = (attempt, data)
    return best[1] if best else None


def _attach_verification(record: dict, writer: dict) -> None:
    """Hand the verdict to the store against the writer's delegation (P1-5)."""
    delegation_id = str(writer.get("delegation_id") or "").strip()
    if not delegation_id or not _go_engine():
        return
    idev = _idev_bin()
    if not idev:
        return
    cmd = [
        idev, "delegation", "verify", "--id", delegation_id,
        "--verifier", str(record["agent"]), "--verdict", report_status(record) or "UNKNOWN",
    ]
    evidence = report_evidence(record)
    if evidence and evidence != "-":
        cmd += ["--evidence", evidence]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"BLOCKED delegation verify failed: {(proc.stderr or proc.stdout or '').strip()}", file=sys.stderr)
        raise SystemExit(2)


def _go_engine() -> bool:
    return (os.environ.get("IDEV_ENGINE") or "go").strip().lower() != "python"


def _idev_bin() -> str | None:
    return idev_bin.path()


def _allocate_attempt(record: dict, repo: Path | None) -> dict | None:
    """Ask DelegationRepo for the next attempt (E3.3). None → client path."""
    if not _go_engine():
        return None
    idev = _idev_bin()
    if not idev:
        return None
    feature = str(record.get("feature") or "").strip()
    run = load_run(feature, repo) if feature else None
    run_id = str((run or {}).get("run_id") or record.get("run_id") or "").strip()
    if not run_id:
        return None
    step = str(record.get("step") or "").strip()
    agent = str(record.get("agent") or "").strip()
    if not step or not agent:
        return None
    cmd = [
        idev, "delegation", "allocate",
        "--run-id", run_id, "--step", step, "--agent", agent,
    ]
    if feature:
        cmd.extend(["--feature", feature])
    if str(record.get("delegation_id") or "").strip():
        cmd.extend(["--id", str(record["delegation_id"]).strip()])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(
            f"BLOCKED delegation allocate failed: {(proc.stderr or proc.stdout or '').strip()}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"BLOCKED delegation allocate returned non-JSON: {proc.stdout!r}", file=sys.stderr)
        raise SystemExit(2)
    attempt = int(data.get("attempt") or 0)
    if attempt <= 0 or not data.get("id"):
        print(f"BLOCKED delegation allocate missing id/attempt: {data!r}", file=sys.stderr)
        raise SystemExit(2)
    return {"id": str(data["id"]), "attempt": attempt}


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
    role = str(record.get("role") or "writer").strip().lower()
    if role not in ("writer", "verifier"):
        print(f"BLOCKED role is writer or verifier, not {role!r}", file=sys.stderr)
        return 2
    if role == "verifier":
        expected = kind_agents.KIND_VERIFIER.get(kind)
        if not expected:
            print(f"BLOCKED kind {kind} has no independent verifier; drop role: verifier", file=sys.stderr)
            return 2
        if str(record["agent"]) != expected:
            print(f"BLOCKED kind {kind} is verified by {expected}, not {record['agent']}", file=sys.stderr)
            return 2
        record["role"] = "verifier"
    else:
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
    # Lift SUGGEST out of the report body so eval and timeline can see it.
    lifted = lift(str((record.get("report") or {}).get("raw", "")))
    if lifted["suggest"]:
        record["suggest"] = lifted["suggest"]
    record.setdefault("suggest", "")
    record["guide"] = lifted["guide"]
    record["domain"] = lifted["domain"]
    record["conclusion"] = lifted["conclusion"]

    # E3.3: when the Go engine owns truth, attempt comes from DelegationRepo
    # (server assigns). The YAML filename is a projection of that number, not
    # the primary key. Python golden keeps client-chosen attempt + exclusive create.
    shard = str(record.get("shard") or "").strip()
    writer = None
    if role == "verifier":
        # A verification is not another attempt at the step: it sits beside
        # the writer's attempt it checked and takes no attempt number.
        writer = writer_record(record_dir(args.feature, args.repo), str(record["step"]), shard)
        if writer is None:
            print(
                f"BLOCKED no writer record for {record['step']} in this run; "
                "the writer's delegation is recorded before its verification",
                file=sys.stderr,
            )
            return 2
        record["attempt"] = safeyaml.as_int(writer.get("attempt"), 1)
        record["verifies"] = {
            key: writer[key] for key in ("attempt", "agent", "delegation_id")
            if str(writer.get(key) or "").strip()
        }
    else:
        allocated = _allocate_attempt(record, args.repo)
        if allocated is not None:
            record["attempt"] = allocated["attempt"]
            record["delegation_id"] = allocated["id"]
    attempt = safeyaml.as_int(record.get("attempt"), 1)
    record["attempt"] = attempt
    try:
        name = (verify_record_name if writer is not None else record_name)(str(record["step"]), attempt, shard)
    except ValueError:
        print(f"BLOCKED shard {shard!r} is not a slug", file=sys.stderr)
        return 2
    if writer is None and attempt > 1 and not str((record.get("brief") or {}).get("prior_failure", "")).strip():
        print("BLOCKED attempt > 1 needs brief.prior_failure (the agent must read it)", file=sys.stderr)
        return 2

    # Timing is optional on purpose: observability must not become a gate.
    # When both ends are present, store the derived duration so views and
    # metrics never have to re-parse timestamps. The subagentStop hook also
    # leaves duration_ms and tool_call_count; copy them from this
    # delegation's own row when the record has none yet (phase 1 §4).
    seconds = duration_of(record)
    if seconds is not None:
        record["duration_s"] = seconds
    taken = {str(r["stop_id"]) for _, r in load_all(args.feature, args.repo) if r.get("stop_id")}
    stop = stop_for(record, (args.repo or Path.cwd()).resolve(), taken)
    if stop is not None:
        record["stop_id"] = stop_id(stop)
        for key in ("duration_ms", "tool_call_count", "message_count"):
            if key not in record and isinstance(stop.get(key), (int, float)):
                record[key] = int(stop[key])
        if seconds is None and isinstance(record.get("duration_ms"), int) and record["duration_ms"] >= 0:
            record["duration_s"] = round(record["duration_ms"] / 1000, 3)
            seconds = record["duration_s"]

    record["checks"] = run_checks(record, args.repo)
    record["checker"] = checker_version()
    record["signals"] = signals_of(record)

    target = record_dir(args.feature, args.repo)
    target.mkdir(parents=True, exist_ok=True)
    path = target / name
    # The filename is the only key a record has, and `attempt` defaults to 1.
    # So writing a second record for the same step silently replaced the
    # first: the failure that caused the retry disappeared, taking the reason
    # for the retry with it. Create exclusively and make the caller say which
    # attempt this is.
    # report.raw is the agent's report, whose machine checks (FACTS / DOC_DRIFT
    # / SCOPE / RED_FIRST / ASSUMED …) are all line-anchored. yaml.safe_dump
    # folds a multi-line single-quoted scalar into one line, which blinds
    # every one of those regexes — the checks then fail and blame the agent
    # for fields it did write. Represent raw as a literal block so the
    # newlines survive the round trip (proposal 20261022-delegation-raw-folding).
    report = record.get("report")
    if isinstance(report, dict) and isinstance(report.get("raw"), str):
        record["report"] = dict(
            report, raw=yaml_representers.LiteralString(report["raw"])
        )
    if writer is not None:
        if path.exists():
            print(f"BLOCKED {path} already records the verification of {record['step']} attempt {attempt}",
                  file=sys.stderr)
            return 2
        _attach_verification(record, writer)
    try:
        with open(path, "x", encoding="utf-8") as fh:
            fh.write(yaml_representers.dump(record))
    except FileExistsError:
        print(f"BLOCKED {path} already records {record['step']} attempt {attempt}", file=sys.stderr)
        print(f"HINT    set attempt: {attempt + 1} in the record (with brief.prior_failure) to log a retry", file=sys.stderr)
        return 2
    print(f"OK   {path}" + (f"  ({human_secs(seconds)})" if seconds is not None else ""))
    for signal in record["signals"]:
        print(f"SIGNAL {signal}  (ask the person; record the answer with workflow.py decide)")
    for line in domain_directive(record):
        print(line)
    if seconds is None:
        print("HINT no timing: pass started_at + finished_at to make duration observable")
    if stop is None and _stop_rows():
        print(f"HINT no subagentStop row of {record['agent']} for this delegation (another record took it, "
              "or it fell outside started_at..finished_at): tool calls stay unknown")
    elif stop is None:
        print(f"HINT {_subagent_stops_path()} has no rows: install the hooks "
              f"(bash {kind_agents.kernel_root()}/scripts/install-idev-hooks.sh) so records carry "
              "duration and tool calls")

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
        shard = str(record.get("shard") or "").strip()
        label = f"{record.get('step')}-{record.get('attempt', 1)} {record.get('agent')}"
        if shard:
            label = f"{record.get('step')}/{shard}-{record.get('attempt', 1)} {record.get('agent')}"
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
    # prior_failure must carry *why* it failed, not just the status the
    # agent self-reported. An agent told "last time: PASS" after three
    # checks failed will repeat the same omission — the whole point of
    # re-delegating is that it knows what to fix.
    prior = report_status(record) or "?"
    failed = [f"{k}={v}" for k, v in sorted((record.get("checks") or {}).items())
              if isinstance(v, str) and v.startswith("FAIL")]
    if failed:
        print(f"prior_failure: 上次 STATUS={prior},但有 {len(failed)} 项检查未过,"
              "**这些是本次必须修掉的**:")
        for f in failed:
            print(f"  - {f}")
        ev = (record.get("report") or {}).get("evidence", "")
        if ev:
            print(f"  上次证据: {ev}")
    else:
        print(f"prior_failure: {prior} — "
              f"{(record.get('report') or {}).get('evidence', '') or '见上次留痕'}")
    print("# 只改上面点名的失败项和证据路径，不重判上次产物，不索取上次推理。")
    for line in domain_directive(record):
        if line.startswith("CONSULT ") and not line.startswith("CONSULT none"):
            target = line.split()[1]
            print(f"# 重派本步之前先咨询 {target} 一次。将其 GUIDE 原样写进下一行。")
            print("领域约束:")
        elif line.startswith("REBRIEF"):
            print(f"# {line}")
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
        items.sort(key=lambda r: (safeyaml.as_int(r.get("attempt"), 1), str(r.get("shard") or "")))

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
            shard = str(record.get("shard") or "").strip()
            label = step if attempt == 1 else f"{step} #{attempt}"
            if shard:
                label = f"{label}/{shard}"
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
            suggest = suggestion_of(record)
            if suggest:
                print(f"{indent}↳ suggest: {suggest}")
            if str(record.get("guide", "")).strip():
                print(f"{indent}↳ guide: {record['guide']}")
            if str(record.get("domain", "")).strip():
                print(f"{indent}↳ domain: {record['domain']}")

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
    loaded = load_all(args.feature, args.repo)
    pairs = record_paths.distinct(loaded)
    kinds = record_paths.attempt_kinds(pairs)
    by_agent: Counter[str] = Counter()
    blocked: Counter[str] = Counter()
    checks: Counter[str] = Counter()
    produced: Counter[str] = Counter()
    rejected = suggests = remeasured = telemetry = 0
    unscoped: list[tuple[Path, dict]] = []
    durations: list[int] = []

    for path, record in pairs:
        by_agent[str(record.get("agent", "?"))] += 1
        status = report_status(record)
        if status.startswith("BLOCKED"):
            hit = re.search(r"BLOCKED\((\w+)\)", status)
            blocked[hit.group(1) if hit else "unclassified"] += 1
        if kinds[path] == "unscoped":
            unscoped.append((path, record))
        # One ruler for every record: the report is measured again by the
        # current checker, so an old record is not judged by a checker that
        # has since been fixed. `outcome: rejected` was never written by
        # anything; a record whose checks fail IS a rejected round, whatever
        # the agent's self-reported STATUS said.
        measured = remeasure(record)
        stored = record.get("checks") or {}
        if any(str(stored.get(k, "")).startswith("FAIL") != v.startswith("FAIL") for k, v in measured.items()):
            remeasured += 1
        failed = [k for k, v in measured.items() if str(v).startswith("FAIL")]
        if failed:
            rejected += 1
        for name in failed:
            checks[name] += 1
        if suggestion_of(record):
            suggests += 1
        if has_telemetry(record):
            telemetry += 1
        seconds = duration_of(record)
        if seconds is not None:
            durations.append(seconds)
        for key, value in (record.get("metrics") or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                produced[str(key)] += int(value)

    print("## agent-eval")
    print()
    copies = len(loaded) - len(pairs)
    print(f"- delegated: {len(pairs)}" + (f" (duplicate files counted once: {copies})" if copies else ""))
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
    print(f"- retried: {sum(1 for kind in kinds.values() if kind == 'retry')}")
    print(f"- verifications: {sum(1 for kind in kinds.values() if kind == 'verification')}")
    if unscoped:
        print(f"- unscoped: {len(unscoped)} flat records with attempt > 1 — a retry, or a later run's first try; "
              "brief.prior_failure says which")
        for path, record in unscoped:
            why = " ".join(str((record.get("brief") or {}).get("prior_failure") or "-").split())
            print(f"  - {path.name}: {why[:60]}")
    print(f"- rejected: {rejected}")
    print(f"- check_fail: {dict(checks) or '{}'}")
    print(f"- checker: {checker_version()} (reports measured again; a FAIL differs from the stored checks on {remeasured})")
    print(f"- suggest: {suggests}")
    if durations:
        print(
            f"- duration_s: n={len(durations)} total={sum(durations)} "
            f"p50={int(statistics.median(durations))} max={max(durations)}"
        )
    else:
        print("- duration_s: 无计时")
    print(f"- telemetry: {telemetry}/{len(pairs)} records carry duration_ms and tool_call_count "
          "from the subagentStop hook")
    if produced:
        print(f"- produced: {dict(produced)}")
    print()
    print("件数,不打分。结构好不好由人在拷问里评。")
    return 0


def cmd_dir(args: argparse.Namespace) -> int:
    print(record_dir(args.feature, args.repo))
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

    p = sub.add_parser("dir", help="print the directory this run's records go to")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_dir)

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
