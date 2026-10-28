#!/usr/bin/env python3
"""Structural gates for idev deliver / verify / ops modules.

Parses ticket YAML with PyYAML (see ticket_yaml.py). Locks slice.must
to the baseline item text, recorded semantic_gate, test-surface coverage,
and outbound handoff Skills. Still does not judge whether a slogan item
is falsifiable. Structure-green is not a semantic lock; humans still own
semantic-gate.
Exit 0 = no FAIL; 1 = at least one FAIL.

verify-plan is an admission gate when drafting or changing cases, before
asking the human to accept the plan. Do not invoke it just to run an
already-accepted plan.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import idev_bin  # noqa: E402
from doc_home import homes, layout_for, reconcile_spec  # noqa: E402
from ticketless import skips_baseline  # noqa: E402
from ticket_yaml import (
    TicketYamlError,
    as_str,
    collect_hops,
    dimensions_from_surfaces,
    entries,
    field_list,
    has_open_status,
    load_ticket_yaml,
    nonempty_list,
    scalar,
    section_ids,
    signoff_bys,
    yaml_str_list,
)


def coding_section(text: str) -> str:
    m = re.search(r"^##[ \t]*编码规范(?!填写)[^\n]*\n(?P<body>.*?)(?=^##[ \t]|\Z)", text, re.M | re.S)
    return m.group("body") if m else ""


def check_review_coding(review_text: str, errors: list) -> None:
    """Weak structural gate for conventions/coding.md — not semantic judgment."""
    if "编码规范" not in review_text:
        fail("review.md missing 编码规范 section", errors)
        return
    ok("review.md has 编码规范")
    body = coding_section(review_text)
    if not body.strip():
        fail("review.md 编码规范 section empty", errors)
        return

    scene_lines = [
        ln for ln in body.splitlines()
        if re.search(r"场景命中", ln)
    ]
    if not scene_lines:
        fail("review.md missing 场景命中", errors)
    else:
        scene_blob = "\n".join(scene_lines)
        has_zero = bool(re.search(r"零命中", scene_blob))
        has_p = bool(re.search(r"\bP(?:1[0-7]|[1-9])\b", scene_blob))
        has_placeholder = bool(re.search(r"P\?", scene_blob)) and not has_p and not has_zero
        if has_placeholder:
            fail("review.md 场景命中 still placeholder P?", errors)
        elif not has_zero and not has_p:
            fail("review.md 场景命中 needs P# or 零命中", errors)
        else:
            ok("review.md has 场景命中")

    smell_lines = [ln for ln in body.splitlines() if re.search(r"气味命中", ln)]
    if not smell_lines:
        fail("review.md missing 气味命中", errors)
    else:
        smell_blob = "\n".join(smell_lines)
        has_none = bool(re.search(r"(气味命中\s*[:：]\s*无\b)|(/\s*无\b)|(\b无\s*[（(]已扫)", smell_blob))
        if not has_none:
            has_none = bool(re.search(r"气味命中\s*[:：]\s*无\b", smell_blob))
        has_c = bool(re.search(r"\bC(?:1[0-5]|[1-9])\b", smell_blob))
        has_c_ph = bool(re.search(r"C\?", smell_blob)) and not has_c and not has_none
        if has_c_ph:
            fail("review.md 气味命中 still placeholder C?", errors)
        elif not has_none and not has_c:
            fail("review.md 气味命中 needs C# or 无（已扫）", errors)
        else:
            ok("review.md has 气味命中")

    refactor_claimed = bool(
        re.search(r"重构\s*[:：]\s*有", body)
        or re.search(r"结构调整\s*[:：]\s*有", body)
    )
    if refactor_claimed:
        # R 条件 has the same none-word hazard as 护栏, for the same reason:
        # the line exists but names nothing. The value must carry an R#
        # or the word 满足 — whether all six conditions truly hold stays
        # with the human reviewer (§3.4), not with this regex.
        has_r = False
        m = re.search(
            r"^\s*(?:[-*+]|\d+[.)、])?\s*R\s*条件\s*[:：][ \t]*([^\n]*)$", body, re.M
        )
        if m:
            val = m.group(1).strip()
            has_r = bool(val) and (
                re.search(r"R\s*[1-6]", val) is not None or "满足" in val
            )
        # The guard field is line-anchored. The old search's \s* ate the
        # newline after a bare "护栏:" and matched the next line's bullet,
        # so an empty guard counted as a named one — and "护栏: 无" passed
        # because \S counts 无 as a value. coding-tables.md §3.1 R1: an
        # explicit none is the same as no guard; 先补最小护栏再动结构.
        guard_val = ""
        m = re.search(
            r"^\s*(?:[-*+]|\d+[.)、])?\s*护栏\s*[:：][ \t]*([^\n]*)$", body, re.M
        )
        if m:
            guard_val = m.group(1).strip()
        none_guard = bool(guard_val) and (
            re.fullmatch(
                r"(?:无|暂无|没有|待补|todo|none)\s*(?:[（(][^）)]*[）)])?\s*[。．.!！]?",
                guard_val,
                re.I,
            )
            is not None
            or guard_val.startswith(("无，", "无。", "无;"))
        )
        has_guard = bool(guard_val) and not none_guard
        if none_guard:
            fail(
                "review.md refactor claim names no guard (护栏: %s): 先补最小护栏再动结构"
                % guard_val,
                errors,
            )
        elif not has_r and not has_guard:
            fail("review.md refactor claim needs R1-R6 or 护栏:", errors)
        else:
            ok("review.md refactor guard noted")

    hit_blob = "\n".join(scene_lines + smell_lines)
    hit_codes = re.findall(r"\b(?:P(?:1[0-7]|[1-9])|C(?:1[0-5]|[1-9]))\b", hit_blob)
    zero_only = bool(re.search(r"零命中", hit_blob)) and not hit_codes
    if hit_codes and not zero_only:
        fix_lines = [ln for ln in body.splitlines() if re.search(r"纠正\s*[:：]", ln)]
        fix_blob = "\n".join(fix_lines)
        if not fix_lines or not re.search(r"纠正\s*[:：]\s*\S", fix_blob):
            fail("review.md has P/C hits but empty 纠正", errors)
        elif re.search(r"纠正\s*[:：]\s*(路径\s*\+\s*改了什么)?\s*$", fix_blob):
            fail("review.md 纠正 still template placeholder", errors)
        else:
            ok("review.md has 纠正 for hits")

    five = [ln for ln in body.splitlines() if re.search(r"五轴", ln)]
    if not five:
        fail("review.md missing 五轴", errors)
    else:
        blob = "\n".join(five)
        axes = ("正确性", "可读性", "架构", "安全", "性能")
        missing = [a for a in axes if a not in blob]
        if missing:
            fail("review.md 五轴 missing: %s" % ",".join(missing), errors)
        else:
            ok("review.md has 五轴")

    stack = [ln for ln in body.splitlines() if re.search(r"栈指南", ln)]
    if not stack:
        fail("review.md missing 栈指南", errors)
    else:
        blob = "\n".join(stack)
        if re.search(r"栈指南\s*[:：]\s*$", blob) or re.search(r"栈指南\s*[:：]\s*…", blob):
            fail("review.md 栈指南 empty", errors)
        elif not re.search(r"栈指南\s*[:：]\s*\S", blob):
            fail("review.md 栈指南 empty", errors)
        else:
            ok("review.md has 栈指南")

    enh = [ln for ln in body.splitlines() if re.search(r"增强扫描", ln)]
    if not enh:
        fail("review.md missing 增强扫描", errors)
    else:
        blob = "\n".join(enh)
        if re.search(r"未跑", blob) and not re.search(r"已跑", blob):
            fail("review.md 增强扫描 still 未跑", errors)
        elif not re.search(r"已跑", blob):
            fail("review.md 增强扫描 needs 已跑", errors)
        else:
            ok("review.md has 增强扫描")

    who = [ln for ln in body.splitlines() if re.search(r"审查者", ln)]
    if not who:
        fail("review.md missing 审查者", errors)
    else:
        blob = "\n".join(who)
        if re.search(r"\bidev-reviewer\b", blob):
            ok("review.md has 审查者")
        else:
            fail("review.md 审查者 must be idev-reviewer", errors)

    size = [ln for ln in body.splitlines() if re.search(r"文件与行数", ln)]
    if not size:
        fail("review.md missing 文件与行数", errors)
    else:
        blob = "\n".join(size)
        if re.search(r"\d", blob):
            ok("review.md has 文件与行数")
        else:
            fail("review.md 文件与行数 needs a count", errors)


# One blacklist, not two. This file used to carry its own copy, and it had
# already drifted: a blank name passed here and was rejected by
# workflow_spec. Every call site happened to add `not who` as a backstop —
# correctness that depends on each caller remembering is correctness waiting
# to break. agent_signoff() asks the one authority instead.
import workflow_spec as _wspec  # noqa: E402


def agent_signoff(who: str) -> bool:
    """True when `who` cannot sign: an agent name, or nothing at all."""
    return not _wspec.is_human(str(who or ""))

OPS_KINDS = ("onboard", "runtime", "feature", "patrol", "unknown")
OPS_STATUSES = (
    "open",
    "classified",
    "reproducing",
    "root-caused",
    "rewound",
    "handed-off",
    "resolved",
)

# Every tier seals the baseline and accepts req in one signoff.
# A test plan passes on machine checks at every tier when no signal is raised.
# ops resolved stays a person at P0 and machine-only at P1/P2.
SEAL_WITH_REQ = ("P0", "P1", "P2")
AUTO_TIERS = ("P1", "P2")
PLAN_AUTO_TIERS = ("P0", "P1", "P2")

SEMANTIC_PRIOR = {
    "req": ("req-review",),
    "arch": ("req-review", "req"),
    "code": ("req-review", "req", "arch"),
    "test": ("req-review", "req", "arch", "code"),
}

TEST_SURFACE_ALIASES = {
    "correctness": frozenset({"correctness"}),
    "compat": frozenset({"compat"}),
    "boundary": frozenset({"boundary", "exception"}),
    "concurrency": frozenset({"concurrency"}),
    "performance": frozenset({"performance"}),
    "ui-prototype": frozenset({"ui-prototype", "ui"}),
}

DIM_RE = re.compile(r"(?m)^\s*-?\s*dimension:\s*['\"]?([A-Za-z0-9_-]+)")


def collect_dimensions_md(blob: str) -> set[str]:
    return {m.group(1).strip().lower() for m in DIM_RE.finditer(blob or "")}


def family_covered(family: str, dims: set[str]) -> bool:
    return bool(dims & TEST_SURFACE_ALIASES[family])


def semantic_stage(gate: dict, stage: str) -> dict:
    body = gate.get(stage) if isinstance(gate, dict) else None
    return body if isinstance(body, dict) else {}


def check_slice_must_lock(baseline: dict, req: dict, errors: list[str]) -> None:
    items = {i["id"]: i for i in entries(baseline, "items")}
    drifted = []
    for s in entries(req, "slices"):
        item = items.get(s.get("baseline_item_id") or "")
        if not item:
            continue
        expected = item.get("must") or item.get("must_not") or ""
        got = s.get("must") or ""
        if not expected:
            drifted.append("%s (baseline item has no must/must_not)" % s["id"])
        elif re.sub(r"\s+", " ", expected) != re.sub(r"\s+", " ", got):
            drifted.append("%s!=%s" % (s["id"], item["id"]))
    if drifted:
        fail(
            "slice must diverges from baseline item (semantic drift): %s"
            % ",".join(drifted),
            errors,
        )
    else:
        ok("slice must matches baseline item")


def _semantic_missing(gate, needed):
    # type: (object, tuple) -> list
    missing = []
    if not isinstance(gate, dict) or not gate:
        return list(needed)
    for st in needed:
        body = semantic_stage(gate, st)
        passed = as_str(body.get("passed"))
        who = as_str(body.get("by"))
        if passed != "true" or agent_signoff(who):
            missing.append(st)
    return missing


def _soft_ticket(path):
    # type: (Path) -> dict
    try:
        if path.is_file():
            data = load_ticket_yaml(path)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _hint_semantic_backfill(root, deliver, missing):
    # type: (Path, object, list) -> None
    """Print recoverable prior stages; never writes YAML."""
    if not missing:
        return
    baseline = _soft_ticket(root / "baseline.yaml")
    req = _soft_ticket(root / "req.yaml")
    arch = _soft_ticket(root / "arch.yaml")
    sealed = as_str(baseline.get("sealed")) == "true"
    req_ok = as_str(req.get("accepted")) == "true"
    arch_ok = as_str(arch.get("accepted")) == "true"
    evidence = {
        "req-review": "baseline.sealed=true" if sealed else "baseline not sealed",
        "req": "req.accepted=true" if req_ok else "req not accepted",
        "arch": "arch.accepted=true" if arch_ok else "arch not accepted",
    }
    print("HINT semantic_gate backfill candidates (human confirm still required; do not auto-write):")
    for st in missing:
        print("  - %s  evidence: %s" % (st, evidence.get(st, "n/a")))
    print("HINT dry-run: check-feature.sh <feature> <stage> --backfill-semantic-gate-dry-run")


def check_semantic_recorded(deliver, stage, errors, root=None, deferred=()):
    # type: (dict, str, list, object, tuple) -> None
    needed = tuple(st for st in SEMANTIC_PRIOR.get(stage) or () if st not in deferred)
    if not needed:
        return
    gate = deliver.get("semantic_gate") if isinstance(deliver, dict) else None
    if not isinstance(gate, dict) or not gate:
        fail(
            "deliver.yaml missing semantic_gate (prior stages must record 语义门已过); missing=%s"
            % ",".join(needed),
            errors,
        )
        if root is not None:
            _hint_semantic_backfill(root, deliver, list(needed))
        return
    missing = []
    for st in needed:
        body = semantic_stage(gate, st)
        passed = as_str(body.get("passed"))
        who = as_str(body.get("by"))
        if passed != "true":
            fail("semantic_gate.%s.passed is not true" % st, errors)
            missing.append(st)
        elif agent_signoff(who):
            fail("semantic_gate.%s requires human by" % st, errors)
            missing.append(st)
        else:
            ok("semantic_gate.%s recorded" % st)
    if missing and root is not None:
        _hint_semantic_backfill(root, deliver, missing)


def dry_run_semantic_backfill(repo, feature, stage):
    # type: (Path, str, str) -> int
    """Print YAML snippet for missing semantic_gate keys; write nothing."""
    root = homes(repo, feature)["task"]
    deliver_path = root / "deliver.yaml"
    if not deliver_path.is_file():
        print("dry-run: missing %s" % deliver_path)
        return 1
    try:
        deliver = load_ticket_yaml(deliver_path)
    except Exception as ex:
        print("dry-run: cannot parse deliver.yaml: %s" % ex)
        return 1
    if not isinstance(deliver, dict):
        print("dry-run: deliver.yaml not a mapping")
        return 1
    needed = SEMANTIC_PRIOR.get(stage)
    if not needed:
        print("dry-run: stage %s needs no semantic_gate prior" % stage)
        return 0
    gate = deliver.get("semantic_gate") if isinstance(deliver.get("semantic_gate"), dict) else {}
    missing = _semantic_missing(gate, needed)
    who = as_str(deliver.get("by"))
    if agent_signoff(who):
        who = "<HUMAN_BY>"
    print("# dry-run only — not written. After human confirm, merge into deliver.yaml:")
    print("semantic_gate:")
    for st in needed:
        body = semantic_stage(gate, st) if gate else {}
        if st in missing:
            print("  %s:" % st)
            print("    passed: true")
            print("    by: %s" % who)
        else:
            print("  %s:  # already ok by=%s" % (st, as_str(body.get("by"))))
    _hint_semantic_backfill(root, deliver, missing)
    return 0


def check_correctness_runner(plan: dict, errors: list[str]) -> None:
    """At plan time, correctness must already be runnable.

    The test stage refuses an UNPROVEN correctness; finding that out after
    the plan was accepted costs a second acceptance round. A case is
    runnable when it names a runner, or has already PASSed with evidence.
    """
    raw = [c for c in (plan.get("cases") or []) if isinstance(c, dict)]
    correctness = [
        c for c in raw
        if str(c.get("dimension") or "").strip().lower() in TEST_SURFACE_ALIASES["correctness"]
    ]
    if not correctness:
        fail("plan has no correctness case (needs one with a runner)", errors)
        return
    stuck = [
        str(c.get("id") or "?")
        for c in correctness
        if not c.get("runner") and not (as_str(c.get("status")) == "PASS" and as_str(c.get("evidence")))
    ]
    if stuck:
        fail("correctness case with neither runner nor PASS evidence: %s" % ",".join(stuck), errors)
    else:
        ok("every correctness case is runnable")


def check_ledger_settled(repo: Path, feature: str, errors: list[str]) -> None:
    """resolved passes without a person only on a proven root cause and no open guess."""
    import hypothesis

    path = hypothesis.ledger_path(feature, repo)
    if not path.is_file():
        fail("ops.auto needs the hypothesis ledger: %s" % path, errors)
        return
    data = hypothesis.load(path, feature)
    items = [i for i in data.get("items") or [] if isinstance(i, dict)]
    still_open = [str(i.get("id") or "?") for i in items if str(i.get("status", "open")) == "open"]
    if hypothesis.check(data, verbose=False) != 0:
        fail("ops.auto but hypothesis.py check has findings; ask a person", errors)
    elif still_open:
        fail("ops.auto but hypotheses still open: %s; ask a person" % ",".join(still_open), errors)
    elif not any(str(i.get("status")) == "proven" for i in items):
        fail("ops.auto but no proven root cause; ask a person", errors)
    else:
        ok("hypothesis ledger settled (a proven root cause, nothing open)")


def plan_signals(plan: dict, baseline_items: list[str], has_baseline: bool) -> list[str]:
    """What a person must decide before the plan can pass without them.

    Printed as SIGNAL lines; `workflow.py record <gate> AUTO` refuses an
    evidence file that carries one.
    """
    raw = [c for c in (plan.get("cases") or []) if isinstance(c, dict)]
    out = []
    # A case that has not run yet is UNPROVEN too; only one with no runner
    # is certain to stay that way.
    unrunnable = [str(c.get("id") or "?") for c in raw
                  if not c.get("runner") and as_str(c.get("status")) != "PASS"]
    if unrunnable or plan.get("unproven_surfaces"):
        out.append("plan leaves UNPROVEN for a person to accept: %s"
                   % (",".join(unrunnable) or "unproven_surfaces"))
    if has_baseline:
        extra = [str(c.get("id") or "?") for c in raw
                 if as_str(c.get("baseline_item_id")) not in baseline_items]
        if extra:
            out.append("cases not derived 1:1 from the baseline: %s" % ",".join(extra))
    return out


def check_auto_record(
    label: str, data: dict, tier: str, root: Path, errors: list[str],
    tiers: tuple[str, ...] = AUTO_TIERS,
) -> None:
    """`auto: <path>` stands in for a person only at `tiers`, with readable evidence."""
    auto = scalar(data, "auto")
    if not auto:
        return
    evidence = Path(auto) if Path(auto).is_absolute() else root / auto
    if tier not in tiers:
        fail("%s.auto at %s: this tier needs a person's signoff" % (label, tier), errors)
    elif signoff_bys(data):
        fail("%s has both auto and by; pick one" % label, errors)
    elif not evidence.is_file():
        fail("%s.auto evidence not found: %s" % (label, auto), errors)
    else:
        ok("%s passed on machine checks (%s)" % (label, auto))


def check_unproven_surfaces(
    root: Path, plan: dict, cases: list[dict[str, str]], errors: list[str]
) -> None:
    unproven_md = root / "unproven.md"
    blob = ""
    if unproven_md.is_file():
        blob += unproven_md.read_text(encoding="utf-8")
    unproven_dims = collect_dimensions_md(blob)
    unproven_dims |= dimensions_from_surfaces(plan.get("unproven_surfaces"))
    case_dims = {(c.get("dimension") or "").strip().lower() for c in cases}
    case_dims.discard("")
    pass_dims = {
        (c.get("dimension") or "").strip().lower()
        for c in cases
        if c.get("status") == "PASS"
    }
    pass_dims.discard("")

    if "correctness" in unproven_dims:
        fail("correctness cannot be waived via unproven_surfaces", errors)
    overlap = []
    for family, aliases in TEST_SURFACE_ALIASES.items():
        if pass_dims & aliases and unproven_dims & aliases:
            overlap.append(family)
    if overlap:
        fail(
            "PASS case dimension also listed UNPROVEN: %s" % ",".join(overlap),
            errors,
        )

    missing = []
    for family in (
        "correctness",
        "compat",
        "boundary",
        "concurrency",
        "performance",
        "ui-prototype",
    ):
        if family_covered(family, case_dims):
            continue
        if family == "correctness":
            missing.append("correctness (needs executable case, not UNPROVEN)")
        elif family_covered(family, unproven_dims):
            continue
        else:
            missing.append(family)
    if missing:
        fail(
            "test surfaces uncovered (need case or unproven.md / "
            "plan.unproven_surfaces): %s" % ",".join(missing),
            errors,
        )
    else:
        ok("test surfaces covered")


def run_stage_extensions(repo: Path, stage: str, errors: list[str], product: str = "") -> None:
    script = Path(__file__).resolve().parent / "stage-extensions.py"
    cmd = [sys.executable, str(script), stage, "--repo", str(repo)]
    if product:
        cmd.extend(["--product", product])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        fail("stage-extensions could not run: %s" % exc, errors)
        return
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.splitlines():
        print(line)
    if proc.returncode != 0:
        fail("stage-extensions: declared product page missing", errors)
    elif any(line.startswith("OPEN ") for line in out.splitlines()):
        ok("stage extensions listed")
    else:
        ok("no stage extensions")


def run_product_checks(repo: Path, stage: str, errors: list[str]) -> None:
    script = Path(__file__).resolve().parent / "product-checks.sh"
    try:
        proc = subprocess.run(
            ["bash", str(script), "--stage", stage, "--repo", str(repo)],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        fail("product-checks could not run: %s" % exc, errors)
        return
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.splitlines():
        print(line)
    if proc.returncode != 0:
        fail("product-checks: product check failed", errors)
    else:
        ok("product checks")


def run_outbound_skills_check(repo: Path, errors: list[str]) -> None:
    script = Path(__file__).resolve().parent / "outbound-skills-check.sh"
    try:
        proc = subprocess.run(
            ["bash", str(script), "--repo", str(repo)],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        fail("outbound-skills-check could not run: %s" % exc, errors)
        return
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.splitlines():
        print(line)
    if proc.returncode != 0:
        fail("outbound-skills-check: required handoff Skill missing", errors)
    else:
        ok("outbound required skills present")


def fail(msg: str, errors: list[str]) -> None:
    errors.append(msg)
    print("FAIL  " + msg)


def ok(msg: str) -> None:
    print("PASS  " + msg)


# Actionable next steps for common structural fails (printed once at end).
FAIL_HINTS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"plan\.mode must be test"),
        "HINT: set plan.mode: test, cover unproven 六族 (or unproven.md), then re-run check-feature <f> test",
    ),
    (
        re.compile(r"aligned/done requires human by|stage=done requires aligned"),
        "HINT: wait for human confirmation wording; write aligned: true + by: <人名>; never by: agent",
    ),
    (
        re.compile(r"resolved=true requires human by"),
        "HINT: ops.resolved needs human by after chat-confirm; do not forge",
    ),
    (
        re.compile(r"sealed baseline but grill\.md frontier is not closed|missing grill\.md"),
        "HINT: open ~/.cursor/skills/grilling/SKILL.md; close frontier: empty + shared_understanding: true before seal",
    ),
    (
        re.compile(r"design\.md|arch review grill|arch grill"),
        "HINT: at arch write design.md (目标/方案/契约/影响面/回退/用例). Open grill.md ## arch only for a real open question; arch_frontier must be empty before the review. Test cases are written after the architecture is accepted.",
    ),
    (
        re.compile(r"case_intent|plan case"),
        "HINT: draft verify/plan.yaml with the architecture; each case_intent and each plan case share slice_id, baseline_item_id and dimension",
    ),
    (
        re.compile(r"PASS without run evidence"),
        "HINT: keep UNPROVEN until a real run leaves a log path in evidence",
    ),
    (
        re.compile(r"missing verify/plan\.yaml|plan\.goal"),
        "HINT: draft verify/plan.yaml with goal copied from baseline; accept before run",
    ),
    (
        re.compile(r"ops\.kind is still unknown|ops\.\w+ empty"),
        "HINT: classify first (ops/references/classify.md); fill phenomenon/env/artifact/observable",
    ),
    (
        re.compile(r"semantic_gate"),
        "HINT: prior stages need semantic_gate.*.passed: true + human by; dry-run: --backfill-semantic-gate-dry-run",
    ),
]


def print_fail_hints(errors: list[str]) -> None:
    seen: set[str] = set()
    for err in errors:
        for pat, hint in FAIL_HINTS:
            if pat.search(err) and hint not in seen:
                print(hint)
                seen.add(hint)


_GRILL_LINE = re.compile(
    r"(?m)^(convention|frontier|shared_understanding):\s*(\S+)\s*$"
)
_GRILL_Q = re.compile(r"(?m)^❓ \*\*Q[1-9][0-9]*\*\* - \*\*[^*]+\*\*:")
_GRILL_A = re.compile(r"(?m)^➡️ \S")


def _grill_fields(text: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for key, val in _GRILL_LINE.findall(text):
        found.setdefault(key, []).append(val)
    return found


def check_human_spec(
    repo: Path, feature: str, baseline: dict, errors: list[str], sealing: bool = False
) -> None:
    """Sealed tickets have one human spec. Two copies collapse onto the repo's spec directory.

    `sealing` holds a baseline about to be sealed to the same rule.
    """
    layout = layout_for(repo, feature)
    spec = reconcile_spec(repo, feature, layout)
    if scalar(baseline, "sealed") != "true" and not sealing:
        return
    if spec.is_file() and spec.read_text(encoding="utf-8").strip():
        ok("human spec %s" % spec.relative_to(repo).as_posix())
        return
    fail("sealed baseline missing %s" % spec.relative_to(repo).as_posix(), errors)


_DESIGN_SECTIONS = ("目标", "方案", "契约", "影响面", "回退", "用例")
_ARCH_GRILL_LINE = re.compile(
    r"(?m)^(arch_frontier|arch_shared_understanding):\s*(\S+)\s*$"
)
_ARCH_HEADING = re.compile(r"(?m)^##[ \t]+arch[ \t]*$")


def _norm_ws(text: str) -> str:
    return " ".join(text.split())


def _design_section(text: str, name: str) -> str | None:
    match = re.search(
        rf"(?m)^##[ \t]+{re.escape(name)}[^\n]*\n(.*?)(?=^##[ \t]|\Z)",
        text,
        re.S,
    )
    return match.group(1) if match else None


def _mentions_id(text: str, item_id: str) -> bool:
    return re.search(r"(?<![\w-])" + re.escape(item_id) + r"(?![\w-])", text) is not None


def check_design(root: Path, baseline: dict, arch: dict, errors: list[str]) -> None:
    """The architecture review reads design.md. A one-line approach is not that document."""
    path = root / "design.md"
    if not path.is_file():
        fail("missing design.md; the architecture review needs the design write-up", errors)
        return
    text = path.read_text(encoding="utf-8")
    missing = [name for name in _DESIGN_SECTIONS if _design_section(text, name) is None]
    if missing:
        fail("design.md missing sections: %s" % ",".join(missing), errors)
        return
    empty = [
        name for name in _DESIGN_SECTIONS
        if not (_design_section(text, name) or "").strip()
    ]
    if empty:
        fail("design.md empty sections: %s" % ",".join(empty), errors)
        return
    goal = scalar(baseline, "goal")
    if goal and _norm_ws(goal) not in _norm_ws(_design_section(text, "目标") or ""):
        fail("design.md 目标 does not quote baseline.goal", errors)
    else:
        ok("design.md quotes baseline.goal")
    for item_id in section_ids(baseline, "items"):
        if not _mentions_id(text, item_id):
            fail("design.md does not mention baseline item %s" % item_id, errors)
            return
    ok("design.md names every baseline item")
    intents = entries(arch, "case_intents") if arch else []
    cases_section = _design_section(text, "用例") or ""
    unnamed = [row["id"] for row in intents if row["id"] and not _mentions_id(cases_section, row["id"])]
    if unnamed:
        fail("design.md 用例 omits case_intent: %s" % ",".join(unnamed), errors)
    else:
        ok("design.md 用例 names every case_intent")


def check_arch_grill(root: Path, errors: list[str]) -> None:
    """A design question round is optional. An open one blocks the review.

    A closed round may still record a question and a shared-understanding line.
    Those lines are notes, not a second signature, and a review with nothing
    left to ask does not need them.
    """
    path = root / "grill.md"
    if not path.is_file():
        ok("architecture review has no open questions")
        return
    text = path.read_text(encoding="utf-8")
    heading = _ARCH_HEADING.search(text)
    if not heading:
        ok("architecture review has no open questions")
        return
    found: dict[str, list[str]] = {}
    for key, val in _ARCH_GRILL_LINE.findall(text):
        found.setdefault(key, []).append(val)
    if found.get("arch_frontier") != ["empty"]:
        fail("arch review grill is not closed; arch_frontier must be empty", errors)
        return
    ok("arch grill frontier empty")
    if found.get("arch_shared_understanding") == ["true"]:
        ok("arch grill shared understanding confirmed")
    tail = text[heading.end():]
    if _GRILL_Q.search(tail) and _GRILL_A.search(tail):
        ok("arch grill round has a question")


def _triple(row: dict[str, str]) -> tuple[str, str, str]:
    return (row.get("slice_id", ""), row.get("baseline_item_id", ""), row.get("dimension", ""))


def check_plan_tracks_arch(arch: dict, plan: dict, errors: list[str], require_plan: bool) -> None:
    """Cases and case_intents stay the same set. Written apart, they drift."""
    if not arch:
        return
    intents = [row for row in entries(arch, "case_intents") if row.get("id")]
    if not plan:
        if require_plan:
            fail("missing verify/plan.yaml; draft cases after the architecture review", errors)
        else:
            ok("verify/plan.yaml is written after the architecture review")
        return
    cases = [row for row in entries(plan, "cases") if row.get("id")]
    intent_keys: dict[tuple[str, str, str], list[str]] = {}
    for row in intents:
        intent_keys.setdefault(_triple(row), []).append(row["id"])
    case_keys: dict[tuple[str, str, str], list[str]] = {}
    for row in cases:
        case_keys.setdefault(_triple(row), []).append(row["id"])
    missing = []
    for key, ids in intent_keys.items():
        have = case_keys.get(key, [])
        if len(have) < len(ids):
            missing.extend(ids[len(have):])
    extra = []
    for key, ids in case_keys.items():
        have = intent_keys.get(key, [])
        if len(ids) > len(have):
            extra.extend(ids[len(have):])
    if missing:
        fail("case_intent has no plan case: %s" % ",".join(missing), errors)
    elif extra:
        fail("plan case has no case_intent: %s" % ",".join(extra), errors)
    else:
        ok("plan cases match case_intents")


def check_grill(root: Path, baseline: dict, errors: list[str], sealing: bool = False) -> None:
    """grill.md is the only question write-up. A sealed baseline must close it.

    `sealing` holds a baseline about to be sealed to the same rule.
    """
    path = root / "grill.md"
    sealed = scalar(baseline, "sealed") == "true" or sealing
    if not path.is_file():
        if sealed:
            fail("sealed baseline missing grill.md", errors)
        return
    text = path.read_text(encoding="utf-8")
    fields = _grill_fields(text)
    convention = fields.get("convention", [])
    frontier = fields.get("frontier", [])
    shared = fields.get("shared_understanding", [])
    if convention != ["grilling"]:
        fail("grill.md must have one line: convention: grilling", errors)
        return
    ok("grill.md convention grilling")
    if len(frontier) != 1 or frontier[0] not in ("empty", "open"):
        fail("grill.md must have one frontier line: empty or open", errors)
        return
    if len(shared) != 1 or shared[0] not in ("true", "false"):
        fail("grill.md must have one shared_understanding line: true or false", errors)
        return
    if not _GRILL_Q.search(text) or not _GRILL_A.search(text):
        fail("grill.md missing a grilling question line", errors)
        return
    ok("grill.md uses grilling question lines")
    actually_sealed = scalar(baseline, "sealed") == "true"
    pending_seal = sealing and not actually_sealed
    if not actually_sealed and not pending_seal:
        ok("grill.md present")
        return
    if frontier[0] != "empty":
        fail("grill.md frontier is not closed", errors)
        return
    if pending_seal and shared[0] != "true":
        ok("grill frontier empty; shared understanding is written with the requirements confirm")
        return
    if shared[0] != "true":
        fail("sealed baseline but grill.md frontier is not closed", errors)
    else:
        ok("grill.md closed with sealed baseline")


def check_baseline_ready(root: Path, repo: Path, baseline: dict, errors: list[str]) -> None:
    """What a baseline needs before anyone may seal it."""
    if not (root / "baseline.yaml").is_file():
        fail("missing %s" % (root / "baseline.yaml").relative_to(repo).as_posix(), errors)
        return
    if not baseline:
        if not any("baseline.yaml" in e for e in errors):
            fail("baseline.yaml is empty", errors)
        return
    ok("baseline.yaml exists")
    if not scalar(baseline, "goal"):
        fail("baseline.goal empty", errors)
    else:
        ok("baseline.goal set")
    if not scalar(baseline, "non_goal"):
        fail("baseline.non_goal empty", errors)
    else:
        ok("baseline.non_goal set")
    items = section_ids(baseline, "items")
    if not items:
        fail("baseline.items has no id entries", errors)
    else:
        ok("baseline.items = %s" % ",".join(items))
    if has_open_status(baseline):
        fail("baseline still has status: open", errors)
    else:
        ok("no status: open in baseline")
    if nonempty_list(baseline, "objections"):
        fail("baseline.objections not empty", errors)
    else:
        ok("objections empty")
    if nonempty_list(baseline, "review_questions"):
        fail("baseline.review_questions must stay empty; questions belong in grill.md", errors)
    else:
        ok("review_questions empty")


def load_ticket(path: Path, errors: list[str]) -> dict:
    if not path.is_file():
        return {}
    try:
        return load_ticket_yaml(path)
    except TicketYamlError as exc:
        fail(str(exc), errors)
        return {}


def _idev_bin() -> str | None:
    return idev_bin.path()


def check_sealed_projection(
    feature: str, ticket: Path, baseline: dict, errors: list[str]
) -> None:
    """YAML sealed:true is a projection of a sealed SQLite row (E4.3).

    Hand-editing sealed:true without a row must FAIL when the Go binary is
    available. Without the binary, keep the YAML-only check (python golden).
    Also recomputes the manifest (E4.2): drift → FAIL, format-only → ok.
    """
    if as_str(baseline.get("sealed")) != "true":
        return
    idev = _idev_bin()
    if not idev or (os.environ.get("IDEV_ENGINE") or "").strip().lower() == "python":
        return
    sealed = subprocess.run(
        [idev, "baseline", "sealed", "--feature", feature],
        capture_output=True,
        text=True,
    )
    if sealed.returncode != 0:
        fail(
            "baseline.sealed is true in YAML but no sealed row in the store "
            "(hand-edited projection; seal via idev baseline seal — a ticket "
            "whose seal was committed before the store existed: idev baseline adopt)",
            errors,
        )
        return
    ok("baseline sealed row matches YAML projection")
    verify = subprocess.run(
        [
            idev, "baseline", "verify",
            "--feature", feature,
            "--ticket", str(ticket),
            "--block-run=false",
        ],
        capture_output=True,
        text=True,
    )
    out = (verify.stdout or "") + (verify.stderr or "")
    if verify.returncode != 0:
        if "baseline-drift" in out:
            fail(out.strip().splitlines()[-1] if out.strip() else "baseline-drift", errors)
        else:
            fail("baseline verify failed: %s" % (out.strip() or verify.returncode), errors)
    elif "format-only" in out:
        ok("baseline format-only change (WARN)")
    else:
        ok("baseline manifest intact")


def git_names(repo: Path, *git_args: str) -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), *git_args],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [l for l in out.splitlines() if "generatedverify" in l]


def staged_generatedverify(repo: Path) -> list[str]:
    return git_names(repo, "diff", "--cached", "--name-only")


def tracked_generatedverify(repo: Path) -> list[str]:
    return git_names(repo, "ls-files")


DESIGN_HEADINGS = ("目标", "方案", "契约", "影响面", "回退", "用例")


def check_doc_form(
    repo: Path, feature: str, root: Path, arch: dict, plan: dict | None, baseline: dict | None, errors: list
) -> None:
    """The shared shape in docs/SKILL.md 体例: six design headings, one intent id, one case."""
    design_path = root / "design.md"
    if not design_path.is_file():
        fail("missing design.md", errors)
        return
    text = design_path.read_text(encoding="utf-8")
    for title in DESIGN_HEADINGS:
        if re.search(rf"(?m)^##[ \t]+{re.escape(title)}[ \t]*$", text):
            ok(f"design.md has {title}")
        else:
            fail(f"design.md missing ## {title}", errors)
    usecase = ""
    hit = re.search(r"(?m)^##[ \t]+用例[ \t]*\n(?P<body>.*?)(?=^##[ \t]|\Z)", text, re.S)
    if hit:
        usecase = hit.group("body")
    intents = [item for item in (arch.get("case_intents") or []) if isinstance(item, dict)]
    for intent in intents:
        iid = str(intent.get("id") or "").strip()
        if iid and iid not in usecase:
            fail(f"design.md 用例节 missing case_intent {iid}", errors)
        elif iid:
            ok(f"design.md names {iid}")
    if not isinstance(plan, dict):
        return
    cases = [item for item in (plan.get("cases") or []) if isinstance(item, dict)]
    for intent in intents:
        key = (str(intent.get("slice_id") or ""), str(intent.get("baseline_item_id") or ""))
        if not key[0] or not key[1]:
            continue
        matched = [
            case for case in cases
            if str(case.get("slice_id") or "") == key[0]
            and str(case.get("baseline_item_id") or "") == key[1]
        ]
        label = intent.get("id") or key[0]
        if matched:
            ok(f"plan case matches {label}")
        else:
            fail(f"plan missing case for {label} ({key[0]} / {key[1]})", errors)
    report_path = root / "verify" / "report.md"
    if not report_path.is_file():
        return
    report = report_path.read_text(encoding="utf-8")
    for case in cases:
        cid = str(case.get("id") or "").strip()
        goal = str(case.get("goal") or "").strip()
        if cid and cid not in report:
            fail(f"verify/report.md missing case {cid}", errors)
        elif cid:
            ok(f"verify/report.md indexes {cid}")
        if len(goal) >= 24 and goal in report:
            fail(f"verify/report.md copies the goal of {cid or '?'}", errors)
    if isinstance(baseline, dict):
        prd = repo / "docs" / "prd" / f"{feature}.md"
        if prd.is_file():
            prose = prd.read_text(encoding="utf-8")
            for item in baseline.get("items") or []:
                iid = str(item.get("id") or "").strip() if isinstance(item, dict) else ""
                if not iid:
                    continue
                if iid in prose:
                    ok(f"prd names {iid}")
                else:
                    fail(f"docs/prd/{feature}.md missing item {iid}", errors)
    cases_md = repo / "docs" / "test-case" / f"{feature}.md"
    if cases_md.is_file():
        prose = cases_md.read_text(encoding="utf-8")
        for intent in intents:
            iid = str(intent.get("id") or "").strip()
            if not iid:
                continue
            if iid in prose:
                ok(f"test-case names {iid}")
            else:
                fail(f"docs/test-case/{feature}.md missing case_intent {iid}", errors)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", default=".")
    p.add_argument("--feature", required=True)
    p.add_argument(
        "--stage",
        required=True,
        choices=["req-review", "req", "arch", "code", "test", "verify-plan", "ops"],
    )
    p.add_argument(
        "--product",
        default="",
        help="Named product for stage-page filter. Omit to use the checkout marker id",
    )
    p.add_argument(
        "--backfill-semantic-gate-dry-run",
        action="store_true",
        help="Print semantic_gate YAML for missing priors; write nothing",
    )
    args = p.parse_args()
    repo = Path(args.repo).resolve()
    root = homes(repo, args.feature)["task"]
    patrol = homes(repo, args.feature)["patrol"]
    if args.backfill_semantic_gate_dry_run:
        return dry_run_semantic_backfill(repo, args.feature, args.stage)
    errors: list[str] = []
    run_stage_extensions(repo, args.stage, errors, args.product.strip())
    run_product_checks(repo, args.stage, errors)

    deliver = load_ticket(root / "deliver.yaml", errors)
    baseline = load_ticket(root / "baseline.yaml", errors)
    req = load_ticket(root / "req.yaml", errors)
    arch = load_ticket(root / "arch.yaml", errors)
    plan = load_ticket(root / "verify" / "plan.yaml", errors)
    ops = load_ticket(root / "ops.yaml", errors)

    tier = scalar(deliver, "risk_tier") or "P1"
    # Every tier seals the baseline and accepts req in one signoff at the
    # end of req, so req is checked against a baseline that is ready but not sealed.
    sealing = args.stage == "req" and tier in SEAL_WITH_REQ and scalar(baseline, "sealed") != "true"

    if args.stage == "req-review" or sealing:
        check_baseline_ready(root, repo, baseline, errors)

    if args.stage in ("req", "arch", "code", "test", "verify-plan"):
        # code-review and other needs_ticket:false runs have no baseline.
        # A baseline file that exists is still required to be sealed.
        if args.stage == "verify-plan" and skips_baseline(root):
            ok("verify-plan without baseline (recipe needs_ticket false)")
        elif sealing:
            ok("baseline seals with req at %s (one signoff: sealed + req.accepted)" % tier)
        elif scalar(baseline, "sealed") != "true":
            fail("baseline.sealed is not true", errors)
        else:
            ok("baseline sealed")
            check_sealed_projection(args.feature, root, baseline, errors)
        b_rev = scalar(baseline, "revision")
        items = section_ids(baseline, "items")

        if args.stage in ("req", "arch", "code", "test"):
            if not req:
                fail("missing req.yaml", errors)
            else:
                if scalar(req, "baseline_revision") != b_rev:
                    fail(
                        "req.baseline_revision %s != baseline.revision %s"
                        % (scalar(req, "baseline_revision"), b_rev),
                        errors,
                    )
                else:
                    ok("req.baseline_revision matches")
                slice_ids = section_ids(req, "slices")
                refs = field_list(req, "slices", "baseline_item_id")
                missing = [i for i in items if i not in refs]
                if missing:
                    fail("baseline items with no slice: %s" % ",".join(missing), errors)
                else:
                    ok("every baseline item has a slice")
                extra = [r for r in refs if r not in items]
                if extra:
                    fail("slice baseline_item_id not in baseline: %s" % ",".join(extra), errors)
                else:
                    ok("no unknown baseline_item_id in req")
                if len(refs) != len(slice_ids):
                    fail("each slice must have exactly one baseline_item_id", errors)
                check_slice_must_lock(baseline, req, errors)

        if args.stage in ("req", "arch", "code", "test"):
            check_semantic_recorded(
                deliver, args.stage, errors, root=root,
                deferred=("req-review",) if sealing else (),
            )

        if args.stage in ("arch", "code", "test"):
            if not arch:
                fail("missing arch.yaml", errors)
            else:
                if scalar(arch, "baseline_revision") != b_rev:
                    fail("arch.baseline_revision mismatch", errors)
                else:
                    ok("arch.baseline_revision matches")
                intent_refs = field_list(arch, "case_intents", "baseline_item_id")
                missing = [i for i in items if i not in intent_refs]
                if missing:
                    fail("baseline items with no case_intent: %s" % ",".join(missing), errors)
                else:
                    ok("every baseline item has a case_intent")
                bad = [str(h) for h in collect_hops(arch) if h > 1]
                if bad:
                    fail("arch impact hop > 1: %s" % ",".join(bad), errors)
                else:
                    ok("impact hops <= 1")
                if not scalar(arch, "approach") or not scalar(arch, "non_approach"):
                    fail("arch.approach and arch.non_approach must both be set", errors)
                else:
                    ok("arch approach set")
                if args.stage == "arch" and nonempty_list(arch, "open_questions"):
                    print("SIGNAL arch open_questions still open")

        if args.stage in ("arch", "code", "test"):
            check_design(root, baseline, arch, errors)
            check_arch_grill(root, errors)
            check_plan_tracks_arch(arch, plan, errors, require_plan=args.stage != "arch")
        elif args.stage == "verify-plan" and arch:
            check_plan_tracks_arch(arch, plan, errors, require_plan=False)

        if args.stage in ("code", "test", "verify-plan"):
            if not plan:
                fail("missing verify/plan.yaml", errors)
            else:
                if args.stage == "test" and scalar(plan, "mode") != "test":
                    fail("plan.mode must be test at test stage (got %s)" % (scalar(plan, "mode") or "empty"), errors)
                else:
                    if args.stage == "test":
                        ok("plan.mode is test")

                if args.stage in ("verify-plan", "test"):
                    b_goal = scalar(baseline, "goal")
                    p_goal = scalar(plan, "goal")
                    if not p_goal:
                        fail("plan.goal empty", errors)
                    elif b_goal and p_goal != b_goal:
                        fail(
                            "plan.goal diverges from baseline.goal (semantic drift)",
                            errors,
                        )
                    else:
                        ok("plan.goal matches baseline.goal")

                cases = entries(plan, "cases")
                if args.stage == "test":
                    check_unproven_surfaces(root, plan, cases, errors)
                if args.stage == "verify-plan":
                    check_correctness_runner(plan, errors)
                    for signal in plan_signals(plan, items, bool(baseline) and not skips_baseline(root)):
                        print("SIGNAL %s" % signal)
                if args.stage == "test":
                    check_auto_record("plan", plan, tier, root, errors, tiers=PLAN_AUTO_TIERS)
                case_refs = [c["baseline_item_id"] for c in cases if c["baseline_item_id"]]
                missing = [i for i in items if i not in case_refs]
                if missing:
                    fail("baseline items with no plan case: %s" % ",".join(missing), errors)
                else:
                    ok("every baseline item has a plan case")
                extra = [r for r in case_refs if r not in items]
                if extra:
                    fail("plan baseline_item_id not in baseline: %s" % ",".join(extra), errors)
                fake_pass = [
                    c["id"]
                    for c in cases
                    if c["status"] == "PASS"
                    and c["evidence"] in ("", "not run", "not-run", "UNPROVEN")
                ]
                if fake_pass:
                    fail("PASS without run evidence: %s" % ",".join(fake_pass), errors)
                else:
                    ok("no PASS without run evidence")
                if req:
                    slice_map = {
                        s["id"]: s["baseline_item_id"] for s in entries(req, "slices")
                    }
                    no_slice = [c["id"] for c in cases if not c["slice_id"]]
                    if no_slice:
                        fail("plan cases missing slice_id: %s" % ",".join(no_slice), errors)
                    else:
                        ok("every plan case has slice_id")
                    unknown = [
                        c["id"] for c in cases if c["slice_id"] and c["slice_id"] not in slice_map
                    ]
                    if unknown:
                        fail("plan slice_id not in req: %s" % ",".join(unknown), errors)
                    else:
                        ok("plan slice_id exists in req")
                    mismatch = [
                        c["id"]
                        for c in cases
                        if c["slice_id"] in slice_map
                        and c["baseline_item_id"] != slice_map[c["slice_id"]]
                    ]
                    if mismatch:
                        fail(
                            "plan baseline_item_id != req slice: %s" % ",".join(mismatch),
                            errors,
                        )
                    else:
                        ok("plan baseline_item_id matches req slice")
                if any(h > 1 for h in collect_hops(plan)):
                    fail("plan impact hop > 1", errors)

    if args.stage in ("arch", "code", "test", "verify-plan"):
        check_doc_form(
            repo,
            args.feature,
            root,
            arch if isinstance(arch, dict) else {},
            plan if isinstance(plan, dict) else None,
            baseline if isinstance(baseline, dict) else None,
            errors,
        )

    if args.stage in ("req-review", "req", "arch", "code", "test"):
        ev = root / "deliver-eval.md"
        if not ev.is_file() or not ev.read_text(encoding="utf-8").strip():
            fail("missing %s" % (root / "deliver-eval.md").relative_to(repo).as_posix(), errors)
        else:
            ok("deliver-eval.md exists")

    if args.stage == "code":
        review = root / "review.md"
        review_text = review.read_text(encoding="utf-8") if review.is_file() else ""
        if not review.is_file() or not review_text.strip():
            fail("missing %s" % (root / "review.md").relative_to(repo).as_posix(), errors)
        else:
            ok("review.md exists")
            check_review_coding(review_text, errors)

    if args.stage == "ops":
        if not ops:
            fail("missing %s" % (root / "ops.yaml").relative_to(repo).as_posix(), errors)
        else:
            ok("ops.yaml exists")
            for field in ("phenomenon", "env", "artifact", "observable"):
                if not scalar(ops, field):
                    fail("ops.%s empty" % field, errors)
                else:
                    ok("ops.%s set" % field)
            kind = scalar(ops, "kind")
            if kind not in OPS_KINDS:
                fail("ops.kind unknown: %s" % kind, errors)
            else:
                ok("ops.kind = %s" % kind)
            status = scalar(ops, "status")
            if status not in OPS_STATUSES:
                fail("ops.status unknown: %s" % status, errors)
            if kind == "unknown":
                fail("ops.kind is still unknown", errors)
            if kind in ("onboard", "runtime"):
                if not scalar(ops, "handoff"):
                    fail("ops.handoff required for kind=%s" % kind, errors)
                else:
                    ok("ops.handoff set")
            if kind in ("feature", "patrol"):
                if scalar(baseline, "sealed") != "true":
                    fail("baseline.sealed is not true", errors)
                else:
                    ok("baseline sealed")
                suspects = yaml_str_list(ops, "suspect_item_ids")
                items = section_ids(baseline, "items")
                extra = [s for s in suspects if s not in items]
                if extra:
                    fail("suspect_item_ids not in baseline: %s" % ",".join(extra), errors)
                elif kind == "feature" and not suspects:
                    fail("kind=feature needs suspect_item_ids", errors)
                else:
                    ok("suspect_item_ids in baseline")
                b_rev = scalar(baseline, "revision")
                if scalar(ops, "baseline_revision") and scalar(ops, "baseline_revision") != b_rev:
                    fail("ops.baseline_revision mismatch", errors)
            if kind == "patrol":
                if not patrol.is_file():
                    fail("missing %s" % patrol.relative_to(repo).as_posix(), errors)
                else:
                    ok("patrol pack exists")
            origin = scalar(ops, "defect_origin")
            if origin and origin not in ("req", "arch", "code"):
                fail("ops.defect_origin must be req|arch|code", errors)
            if scalar(ops, "resolved") == "true" and scalar(ops, "auto"):
                check_auto_record("ops", ops, tier, root, errors)
                check_ledger_settled(repo, args.feature, errors)
            elif scalar(ops, "resolved") == "true":
                who = scalar(ops, "by")
                if agent_signoff(who):
                    fail("resolved=true requires human by", errors)
                else:
                    ok("resolved has human by")
        run_outbound_skills_check(repo, errors)

    if deliver:
        rt = scalar(deliver, "risk_tier")
        if rt and rt not in ("P0", "P1", "P2"):
            fail("deliver.risk_tier must be P0|P1|P2", errors)
        stage = scalar(deliver, "stage")
        if stage not in (
            "",
            "req-review",
            "req",
            "arch",
            "code",
            "test",
            "done",
            "ops",
        ):
            fail("deliver.stage unknown: %s" % stage, errors)
        aligned = scalar(deliver, "aligned")
        if aligned == "true" or stage == "done":
            who = scalar(deliver, "by")
            if agent_signoff(who):
                fail("aligned/done requires human by", errors)
            else:
                ok("aligned/done has human by")
            if stage == "done" and aligned != "true":
                fail("stage=done requires aligned: true", errors)
            elif stage == "done":
                ok("stage=done with aligned: true")

    forged = []
    for label, text in (
        ("baseline", baseline),
        ("req", req),
        ("arch", arch),
        ("deliver", deliver),
        ("plan", plan),
        ("ops", ops),
    ):
        for who in signoff_bys(text):
            if agent_signoff(who):
                forged.append("%s.by=%s" % (label, who))
    if forged:
        fail("agent filled signoff by: %s" % ", ".join(forged), errors)
    else:
        ok("no agent-filled signoff by")

    staged = staged_generatedverify(repo)
    if staged:
        fail("staged generatedverify paths: %s" % ", ".join(staged), errors)
    else:
        ok("no staged generatedverify")
    tracked = tracked_generatedverify(repo)
    if tracked:
        fail("tracked generatedverify paths: %s" % ", ".join(tracked), errors)
    else:
        ok("no tracked generatedverify")

    check_grill(root, baseline, errors, sealing=sealing)
    check_human_spec(repo, args.feature, baseline, errors, sealing=sealing)

    print("---")
    if errors:
        print("%d FAIL" % len(errors))
        print_fail_hints(errors)
        return 1
    print("0 FAIL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
