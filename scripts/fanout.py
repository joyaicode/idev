#!/usr/bin/env python3
"""On-demand split for self-test, case design, case execution, review, and root cause.

The conductor asks this before delegating those activities. Fewer than two
independent shards, overlapping writes, or a shared Maven module that has
not opted in stay one agent. A FANOUT wave is still one workflow step and
one run: each agent writes only its own shard file, and the conductor
merges before record. When those shard files are already on disk, assess
prints MERGE and does not ask for another agent.

    fanout.py assess --feature F --activity plan|run|selftest|rootcause|report
    fanout.py merge  --feature F --activity plan|run|selftest|rootcause|report

assess writes verify/fanout-<activity>.yaml so merge can see the wave and
can refuse a plan.yaml or hypotheses.yaml that an agent touched.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402

sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
try:
    import doc_home  # noqa: E402
except ImportError:
    print(f"BLOCKED cannot import doc_home from {kind_agents.kernel_root()}; set IDEV_ROOT", file=sys.stderr)
    raise SystemExit(2) from None

import hypothesis  # noqa: E402

ACTIVITIES = ("plan", "run", "selftest", "rootcause", "report")
AGENTS = {
    "plan": "idev-verifier",
    "run": "idev-verifier",
    "selftest": "idev-verifier",
    "rootcause": "idev-ops",
    "report": "idev-reviewer",
}
SIGNED_FINDING = re.compile(r"(?m)^### (I\d+) 已签收\b")
SOURCE_EXT = {".java", ".vue", ".js", ".jsx", ".ts", ".tsx", ".yml", ".yaml", ".xml"}
SKIP_DIR = {"target", "node_modules", "dist", ".git", "generatedverify"}
DEFAULT_CAP = 4
MAX_CAP = 8
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
CASE_STATUS = ("PASS", "FAIL", "UNPROVEN")
HYPO_STATUS = ("open", "proven", "disproven")


def task_of(feature: str, repo: Path | None) -> Path:
    base = (repo or Path.cwd()).resolve()
    return doc_home.homes(base, feature)["task"]


def manifest_path(task: Path, activity: str) -> Path:
    return task / "verify" / f"fanout-{activity}.yaml"


def shard_path(activity: str, shard_id: str) -> str:
    return f"verify/shards/{activity}-{shard_id}.yaml"


def evidence_dir(case_id: str) -> str:
    return f"verify/evidence/{case_id}/"


def _slug(value: object) -> str:
    text = str(value or "").strip()
    if SLUG.fullmatch(text) is None or ".." in text:
        return ""
    return text


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = safeyaml.mapping(path)
    return data or {}


def _fingerprint(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _accepted(case: dict) -> bool:
    value = case.get("accepted")
    return value is True or value == "true"


def _overlap(left: str, right: str) -> bool:
    if left == right:
        return True
    a, b = left.rstrip("/") + "/", right.rstrip("/") + "/"
    return a.startswith(b) or b.startswith(a)


def _writes_ok(shards: list[dict]) -> bool:
    owned: list[str] = []
    for shard in shards:
        for path in shard["writes"]:
            for prior in owned:
                if _overlap(prior, path):
                    return False
            owned.append(path)
    return True


def _cap_wave(shards: list[dict], cap: int) -> tuple[list[dict], list[dict]]:
    if cap < 1:
        cap = 1
    return shards[:cap], shards[cap:]


def _serial(activity: str, reason: str, hint: str = "") -> dict:
    return {
        "schema_version": 1,
        "decision": "SERIAL",
        "activity": activity,
        "reason": reason,
        "hint": hint,
        "cap": 0,
        "shards": [],
        "queued": [],
        "prep": [],
        "guards": {},
    }


def _fanout(activity: str, shards: list[dict], queued: list[dict], prep: list[str], cap: int, hint: str, guards: dict) -> dict:
    return {
        "schema_version": 1,
        "decision": "FANOUT",
        "activity": activity,
        "reason": "",
        "hint": hint,
        "cap": cap,
        "shards": shards,
        "queued": queued,
        "prep": prep,
        "guards": guards,
    }


def _finish(activity: str, shards: list[dict], cap: int, hint: str, guards: dict, serial_reason: str) -> dict:
    if len(shards) < 2 or not _writes_ok(shards):
        reason = serial_reason if len(shards) < 2 else "shard writes overlap"
        return _serial(activity, reason, hint)
    launched, queued = _cap_wave(shards, cap)
    if len(launched) < 2:
        return _serial(activity, f"cap {cap} leaves one shard", hint)
    return _fanout(activity, launched, queued, [], cap, hint, guards)


def _launch(activity: str, pending: list[dict], drafted: list[dict], cap: int, guards: dict, serial_reason: str) -> dict:
    """Keep drafts that are already on disk in the manifest the merge reads.

    A later assess used to keep only the shards that still had no file.
    Merge would then drop the ones that had finished. A wave whose files are
    all present is MERGE: the conductor must not delegate an agent that
    rewrites the ledger.
    """
    if not pending and drafted:
        result = _fanout(activity, drafted, [], [], max(len(drafted), 1), "", guards)
        result["resume"] = "merge"
        return result
    if len(pending) == 1 and drafted:
        result = _fanout(activity, drafted + pending, [], [], len(drafted) + 1, "", guards)
        result["pending_ids"] = [pending[0]["id"]]
        return result
    if len(pending) < 2:
        return _serial(activity, serial_reason)
    result = _finish(activity, pending, cap, "", guards, serial_reason)
    if result["decision"] != "FANOUT" or not drafted:
        return result
    launched = [shard["id"] for shard in result["shards"]]
    result["shards"] = drafted + result["shards"]
    result["pending_ids"] = launched
    return result


def _intent_rows(arch: dict) -> list[dict]:
    rows = []
    for row in safeyaml.as_list(arch.get("case_intents")):
        if isinstance(row, dict) and row.get("id"):
            rows.append(row)
    return rows


def _triple(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("slice_id") or ""),
        str(row.get("baseline_item_id") or ""),
        str(row.get("dimension") or ""),
    )


def _uncovered(intents: list[dict], cases: list[dict]) -> list[dict]:
    pool = [row for row in cases if isinstance(row, dict)]
    used = [False] * len(pool)
    open_rows = []
    for intent in intents:
        key = _triple(intent)
        hit = None
        for i, case in enumerate(pool):
            if not used[i] and _triple(case) == key:
                hit = i
                break
        if hit is None:
            open_rows.append(intent)
        else:
            used[hit] = True
    return open_rows


def _signed_findings(task: Path) -> list[str]:
    """I* headings a person has already signed. Unsigned findings are not cases yet."""
    path = task / "review.md"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    found: list[str] = []
    seen: set[str] = set()
    for match in SIGNED_FINDING.finditer(text):
        sid = match.group(1)
        if sid in seen or not _slug(sid):
            continue
        seen.add(sid)
        found.append(sid)
    return found


def _covers_finding(case: dict, finding: str) -> bool:
    if str(case.get("finding") or "") == finding:
        return True
    cid = str(case.get("id") or "")
    return re.search(rf"(?i)(?:^|[-_]){re.escape(finding)}(?:$|[-_])", cid) is not None


def _assess_plan_findings(task: Path, cap: int) -> dict:
    """Split a fresh plan by signed findings.

    case_intents are an output of this step, so a review ticket that has
    not drafted them yet would otherwise stay one agent forever.
    """
    findings = _signed_findings(task)
    if len(findings) < 2:
        return _serial("plan", "fewer than two case_intents")
    plan_path = task / "verify" / "plan.yaml"
    cases = [row for row in safeyaml.as_list(_load(plan_path).get("cases")) if isinstance(row, dict)]
    uncovered = [sid for sid in findings if not any(_covers_finding(case, sid) for case in cases)]
    if not uncovered:
        return _serial("plan", "signed findings already have cases; record the step, do not delegate")
    shards = []
    for sid in uncovered:
        check_dir = f"verify/checks/{sid}/"
        shards.append({
            "id": sid,
            "agent": AGENTS["plan"],
            "writes": [shard_path("plan", sid), check_dir],
            "scope": (
                f"signed finding {sid}; draft one or more selftest cases in the shard file; "
                f"each case has finding: {sid} and a slug id; list the product files it names under paths; "
                f"check scripts go under {check_dir}; "
                "do not write plan.yaml, arch.yaml, or review.md; do not set accepted"
            ),
            "units": [sid],
            "finding": sid,
            "intent": {
                "id": sid,
                "finding": sid,
                "slice_id": "",
                "baseline_item_id": "",
                "dimension": "",
            },
        })
    drafted, pending = _drafts(task, shards)
    return _launch(
        "plan", pending, drafted, cap,
        {
            "verify/plan.yaml": _fingerprint(plan_path),
            "arch.yaml": _fingerprint(task / "arch.yaml"),
            "review.md": _fingerprint(task / "review.md"),
        },
        "fewer than two signed findings still need a case",
    )


def assess_plan(task: Path, cap: int) -> dict:
    arch = _load(task / "arch.yaml")
    intents = _intent_rows(arch)
    if len(intents) < 2:
        return _assess_plan_findings(task, cap)
    plan_path = task / "verify" / "plan.yaml"
    cases = safeyaml.as_list(_load(plan_path).get("cases"))
    pending = _uncovered(intents, [c for c in cases if isinstance(c, dict)])
    if len(pending) < 2:
        return _serial("plan", "fewer than two case_intents still need a case")
    shards = []
    for intent in pending:
        sid = _slug(intent.get("id"))
        if not sid:
            return _serial("plan", f"case_intent id is not a shard slug: {intent.get('id')}")
        shards.append({
            "id": sid,
            "agent": AGENTS["plan"],
            "writes": [shard_path("plan", sid)],
            "scope": (
                f"case_intent {sid} dimension {intent.get('dimension') or '-'}; "
                "write only this shard; do not write plan.yaml; do not set accepted"
            ),
            "units": [sid],
            "intent": {
                "id": sid,
                "slice_id": str(intent.get("slice_id") or ""),
                "baseline_item_id": str(intent.get("baseline_item_id") or ""),
                "dimension": str(intent.get("dimension") or ""),
            },
        })
    return _finish(
        "plan", shards, cap, "",
        {"verify/plan.yaml": _fingerprint(plan_path)},
        "fewer than two case drafts",
    )


def _contention(case: dict) -> tuple[str, str]:
    """Cases that share a build or a session stay in one shard.

    Maven on one module writes the same target/. Splitting it needs
    runner.parallel: true, which is the author saying these selectors do
    not share that output. frontend-http on one env shares a login.
    """
    runner = case.get("runner") if isinstance(case.get("runner"), dict) else {}
    kind = str(runner.get("kind") or "")
    if kind.startswith("maven-") and runner.get("parallel") is not True:
        return ("maven", str(runner.get("module") or "."))
    if kind == "frontend-http":
        return ("http", str(runner.get("env") or ""))
    if not kind:
        return ("unknown", "")
    return ("case", str(case.get("id") or ""))


def _case_rows(plan: dict) -> list[dict]:
    rows = []
    for case in safeyaml.as_list(plan.get("cases")):
        if not isinstance(case, dict):
            continue
        if not _accepted(case):
            continue
        if str(case.get("status") or "") == "PASS":
            continue
        rows.append(case)
    return rows


def assess_cases(task: Path, activity: str, cap: int) -> dict:
    plan_path = task / "verify" / "plan.yaml"
    plan = _load(plan_path)
    if not plan:
        return _serial(activity, "no plan.yaml")
    mode = str(plan.get("mode") or "")
    if activity == "selftest" and mode != "selftest":
        return _serial(activity, f"plan mode is {mode or 'unset'}, not selftest")
    cases = _case_rows(plan)
    if len(cases) < 2:
        return _serial(activity, "fewer than two accepted cases still to run")
    ids = [str(case.get("id") or "") for case in cases]
    if any(not _slug(cid) for cid in ids) or len(set(ids)) != len(ids):
        return _serial(activity, "case id missing, duplicated, or not a shard slug")
    groups: dict[tuple[str, str], list[dict]] = {}
    order: list[tuple[str, str]] = []
    for case in cases:
        key = _contention(case)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(case)
    hint = ""
    held = [key for key in order if key[0] == "maven" and len(groups[key]) > 1]
    if held:
        names = ", ".join(f"{key[1]} ({len(groups[key])} cases)" for key in held)
        hint = (
            "shared maven module "
            + names
            + "; set runner.parallel: true on each of those cases to split them"
        )
    shards = []
    for key in order:
        members = groups[key]
        if len(members) == 1:
            sid = _slug(members[0].get("id"))
        else:
            sid = _slug(f"{key[0]}-{key[1]}".replace("/", "-"))
        if not sid:
            return _serial(activity, f"cannot name a shard for {key}")
        units = [str(case["id"]) for case in members]
        writes = [shard_path(activity, sid)]
        writes.extend(evidence_dir(unit) for unit in units)
        scope = "cases " + ",".join(units) + "; write only these paths; do not write plan.yaml; do not run mvn clean"
        shard = {
            "id": sid,
            "agent": AGENTS[activity],
            "writes": writes,
            "scope": scope,
            "units": units,
        }
        runner = members[0].get("runner") if isinstance(members[0].get("runner"), dict) else {}
        if runner.get("parallel") is True and str(runner.get("kind") or "").startswith("maven-"):
            shard["module"] = str(runner.get("module") or "")
        shards.append(shard)
    result = _finish(
        activity, shards, cap, hint,
        {"verify/plan.yaml": _fingerprint(plan_path)},
        "one contention group",
    )
    if result["decision"] == "FANOUT":
        prep: list[str] = []
        for shard in result["shards"]:
            module = str(shard.get("module") or "")
            line = f"{module} mvn -pl {module} -am -Pex test-compile"
            if module and line not in prep:
                prep.append(line)
        result["prep"] = prep
    return result


def assess_rootcause(task: Path, cap: int) -> dict:
    path = task / "hypotheses.yaml"
    items = [row for row in safeyaml.as_list(_load(path).get("items")) if isinstance(row, dict)]
    open_items = [row for row in items if str(row.get("status") or "open") == "open"]
    if len(open_items) < 2:
        return _serial("rootcause", "fewer than two open hypotheses")
    shards = []
    for item in open_items:
        sid = _slug(item.get("id"))
        if not sid:
            return _serial("rootcause", f"hypothesis id is not a shard slug: {item.get('id')}")
        shards.append({
            "id": sid,
            "agent": AGENTS["rootcause"],
            "writes": [shard_path("rootcause", sid)],
            "scope": f"hypothesis {sid}; write only this shard; do not write hypotheses.yaml; another shard is not evidence",
            "units": [sid],
        })
    if len({shard["id"] for shard in shards}) != len(shards):
        return _serial("rootcause", "duplicate hypothesis id")
    return _finish(
        "rootcause", shards, cap, "",
        {"hypotheses.yaml": _fingerprint(path)},
        "fewer than two open hypotheses",
    )


def _source_path(path: str) -> bool:
    parts = Path(path).parts
    if not parts or any(part.startswith(".") or part in SKIP_DIR for part in parts):
        return False
    if path.startswith("docs/task/") or path == "docs/task":
        return False
    return Path(path).suffix.lower() in SOURCE_EXT


def _changed_sources(repo: Path) -> list[str]:
    if not (repo / ".git").exists():
        return []
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "-uall"],
            check=False, capture_output=True, text=True,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    found = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if _source_path(path):
            found.append(path)
    return found


def _drafts(task: Path, shards: list[dict]) -> tuple[list[dict], list[dict]]:
    """Shards whose primary file is already on disk, then the ones an agent still has to write."""
    drafted: list[dict] = []
    pending: list[dict] = []
    for shard in shards:
        rel = str((shard.get("writes") or [""])[0])
        if rel and (task / rel).is_file():
            drafted.append(shard)
        else:
            pending.append(shard)
    return drafted, pending


def assess_report(task: Path, repo: Path, cap: int) -> dict:
    """Deep-read changed source by top-level module. The scan itself stays one command."""
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for path in _changed_sources(repo):
        module = path.split("/", 1)[0] if "/" in path else "root"
        if not _slug(module):
            continue
        if module not in groups:
            order.append(module)
            groups[module] = []
        groups[module].append(path)
    if len(order) < 2:
        return _serial("report", "fewer than two source modules changed")
    shards = []
    for module in order:
        files = groups[module]
        shown = ", ".join(files[:40])
        if len(files) > 40:
            shown += f" (+{len(files) - 40} more)"
        shards.append({
            "id": module,
            "agent": AGENTS["report"],
            "writes": [f"review/shards/{module}.md"],
            "scope": (
                f"module {module}; deep-read only these changed sources: {shown}; "
                f"write review/shards/{module}.md; "
                "each formal finding is a ### FINDING block with 位置 / 根据 / 失败场景 / 修复建议; "
                "files not opened go under ### UNPROVEN; do not write review.md; do not number I*"
            ),
            "units": files,
        })
    drafted, pending = _drafts(task, shards)
    if drafted and _signed_findings(task):
        return _serial("report", "review.md is already signed; record the step, do not delegate")
    result = _launch(
        "report", pending, drafted, cap,
        {"review.md": _fingerprint(task / "review.md")},
        "fewer than two module drafts",
    )
    if result["decision"] == "FANOUT" and result.get("resume") != "merge":
        root = kind_agents.kernel_root()
        result["prep"] = [f"bash {root}/scripts/coding-scan.sh {repo}"]
    return result


def lease_globs(ticket: str, writes: list[str]) -> list[str]:
    """Repo-relative patterns for one shard. A directory write keeps a trailing slash."""
    out = []
    base = ticket.strip().strip("/")
    for raw in writes:
        rel = str(raw).strip().lstrip("./")
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            raise ValueError(rel)
        if rel.endswith("/"):
            out.append(f"{base}/{rel.rstrip('/')}/**")
        else:
            out.append(f"{base}/{rel}")
    return out


def assess(feature: str, activity: str, repo: Path | None = None, cap: int = DEFAULT_CAP) -> dict:
    if activity not in ACTIVITIES:
        raise ValueError(activity)
    cap = min(max(int(cap), 1), MAX_CAP)
    task = task_of(feature, repo)
    if not task.is_dir():
        return _serial(activity, "no ticket")
    if activity == "plan":
        return assess_plan(task, cap)
    if activity == "report":
        return assess_report(task, (repo or Path.cwd()).resolve(), cap)
    if activity == "rootcause":
        return assess_rootcause(task, cap)
    return assess_cases(task, activity, cap)


def render(result: dict, feature: str) -> str:
    activity = result["activity"]
    if result.get("resume") == "merge":
        return "\n".join([
            f"MERGE {activity} shard drafts are in; do not delegate",
            "MERGE python3 scripts/fanout.py merge --feature "
            f"{feature} --activity {activity}",
        ])
    lines = []
    pending = {str(item) for item in (result.get("pending_ids") or [])}
    if result["decision"] == "SERIAL":
        lines.append(f"SERIAL {activity} {result['reason']}")
    else:
        shown = [shard for shard in result["shards"] if not pending or str(shard["id"]) in pending]
        lines.append(f"FANOUT {activity} {len(shown)} cap={result['cap']}")
        for prep in result.get("prep") or []:
            lines.append(f"PREP {prep}")
        for shard in shown:
            writes = ",".join(shard["writes"])
            lines.append(f"SHARD {shard['id']} AGENT {shard['agent']} WRITES {writes}")
            lines.append(f"SCOPE {shard['scope']}")
        for shard in result.get("queued") or []:
            lines.append(f"QUEUED {shard['id']}")
        lines.append(
            "MERGE python3 scripts/fanout.py merge --feature "
            f"{feature} --activity {activity}"
        )
        lines.append(
            "LEASE workflow.py delegate <step> --shard <id> for each SHARD; "
            "that lease covers only the shard WRITES"
        )
    if result.get("hint"):
        lines.append(f"HINT {result['hint']}")
    return "\n".join(lines)


def write_manifest(feature: str, result: dict, repo: Path | None) -> Path | None:
    task = task_of(feature, repo)
    if not task.is_dir():
        return None
    path = manifest_path(task, result["activity"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safeyaml.dump(result), encoding="utf-8")
    return path


def _guard_ok(task: Path, result: dict) -> str:
    for rel, digest in (result.get("guards") or {}).items():
        current = _fingerprint(task / rel)
        if current != digest:
            return rel
    return ""


def _rel_file(path: str) -> bool:
    if not path or path.startswith("/") or ".." in Path(path).parts:
        return False
    return True


def _take_finding(shard: dict, body: dict, cases: list[dict], known: set[str], included: list[str]) -> str:
    finding = str(shard.get("finding") or "")
    drafted = [row for row in safeyaml.as_list(body.get("cases")) if isinstance(row, dict)]
    if not drafted:
        return f"shard {finding} drafted no case"
    for raw in safeyaml.as_list(body.get("paths")):
        rel = str(raw or "").strip()
        if not _rel_file(rel):
            return f"shard {finding} path {raw!r} is not a repo-relative file"
        if rel not in included:
            included.append(rel)
    for drafted_case in drafted:
        case = dict(drafted_case)
        if str(case.get("finding") or "") != finding:
            return f"shard {finding} case must set finding: {finding}"
        cid = str(case.get("id") or "")
        if not _slug(cid):
            return f"shard {finding} case id {cid!r} is not a slug"
        if cid in known:
            return f"shard {finding} case {cid} is already in plan.yaml"
        case["accepted"] = False
        case["status"] = "UNPROVEN"
        case.setdefault("evidence", "not run")
        cases.append(case)
        known.add(cid)
    return ""


def _write_includes(task: Path, paths: list[str]) -> None:
    if not paths:
        return
    arch_path = task / "arch.yaml"
    arch = _load(arch_path)
    rows = [row for row in safeyaml.as_list(arch.get("impact_candidates")) if isinstance(row, dict)]
    have = {str(row.get("path") or "") for row in rows}
    for rel in paths:
        if rel in have:
            continue
        rows.append({"path": rel, "hop": 0, "include": True})
        have.add(rel)
    if not arch:
        arch = {"schema_version": 1, "feature": task.name}
    arch["impact_candidates"] = rows
    arch_path.write_text(safeyaml.dump(arch), encoding="utf-8")


def _merge_plan(task: Path, result: dict) -> int:
    plan_path = task / "verify" / "plan.yaml"
    plan = _load(plan_path)
    cases = [row for row in safeyaml.as_list(plan.get("cases")) if isinstance(row, dict)]
    known = {str(row.get("id")) for row in cases}
    triples = [_triple(row) for row in cases]
    included: list[str] = []
    for shard in result["shards"]:
        body = _load(task / shard["writes"][0])
        if shard.get("finding"):
            err = _take_finding(shard, body, cases, known, included)
            if err:
                print(f"BLOCKED {err}", file=sys.stderr)
                return 2
            continue
        intent = shard.get("intent") or {}
        drafted = [row for row in safeyaml.as_list(body.get("cases")) if isinstance(row, dict)]
        if len(drafted) != 1:
            print(f"BLOCKED shard {shard['id']} must draft one case", file=sys.stderr)
            return 2
        case = dict(drafted[0])
        if str(case.get("id") or "") != intent.get("id"):
            print(f"BLOCKED shard {shard['id']} case id must be {intent.get('id')}", file=sys.stderr)
            return 2
        if _triple(case) != _triple(intent):
            print(f"BLOCKED shard {shard['id']} drifted from its case_intent", file=sys.stderr)
            return 2
        if case["id"] in known or _triple(case) in triples:
            print(f"BLOCKED shard {shard['id']} is already in plan.yaml", file=sys.stderr)
            return 2
        case["accepted"] = False
        case["status"] = "UNPROVEN"
        case.setdefault("evidence", "not run")
        cases.append(case)
        known.add(case["id"])
        triples.append(_triple(case))
    if not plan:
        plan = {"schema_version": 1, "feature": task.name, "accepted": False}
    plan["cases"] = cases
    plan.setdefault("accepted", False)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(safeyaml.dump(plan), encoding="utf-8")
    _write_includes(task, included)
    print(f"OK   merged {len(result['shards'])} plan shards -> {plan_path}")
    return 0


def _marked_blocks(text: str) -> tuple[list[str], list[str], bool]:
    """FINDING and UNPROVEN bodies. The third value is whether either marker appeared."""
    findings: list[str] = []
    unproven: list[str] = []
    mode = ""
    buf: list[str] = []
    seen = False

    def flush() -> None:
        body = "\n".join(buf).strip()
        if mode == "finding" and body:
            findings.append(body)
        elif mode == "unproven" and body:
            unproven.append(body)

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "### FINDING":
            flush()
            buf = []
            mode = "finding"
            seen = True
            continue
        if stripped == "### UNPROVEN":
            flush()
            buf = []
            mode = "unproven"
            seen = True
            continue
        if line.startswith("### "):
            flush()
            buf = []
            mode = ""
            continue
        if mode:
            buf.append(line)
    flush()
    return findings, unproven, seen


def _merge_report(task: Path, result: dict) -> int:
    findings: list[str] = []
    unproven: list[str] = []
    for shard in result["shards"]:
        text = (task / shard["writes"][0]).read_text(encoding="utf-8", errors="replace")
        found, missed, seen = _marked_blocks(text)
        if not seen:
            print(f"BLOCKED shard {shard['id']} needs ### FINDING or ### UNPROVEN", file=sys.stderr)
            return 2
        findings.extend(found)
        if missed:
            unproven.append(f"### {shard['id']}\n" + "\n\n".join(missed))
    lines = [
        "# Review",
        "",
        f"feature: {task.name}",
        "by: idev-reviewer",
        "",
        "本步只记账，状态一律**待签收**。分片合并。审查者: idev-reviewer。",
        "",
        "## 正式发现",
        "",
    ]
    if not findings:
        lines.append("- 无")
    for number, body in enumerate(findings, start=1):
        lines.append(f"### I{number} 待签收")
        lines.append("")
        lines.append(body)
        lines.append("")
    lines.append("## UNPROVEN")
    lines.append("")
    lines.append("\n\n".join(unproven) if unproven else "- 无")
    lines.append("")
    path = task / "review.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK   merged {len(result['shards'])} report shards -> {path}")
    return 0


def _merge_run(task: Path, result: dict) -> int:
    plan_path = task / "verify" / "plan.yaml"
    plan = _load(plan_path)
    if not plan:
        print("BLOCKED no plan.yaml to merge into", file=sys.stderr)
        return 2
    by_id = {}
    for row in safeyaml.as_list(plan.get("cases")):
        if isinstance(row, dict) and row.get("id"):
            by_id[str(row["id"])] = row
    for shard in result["shards"]:
        body = _load(task / shard["writes"][0])
        updates = [row for row in safeyaml.as_list(body.get("cases")) if isinstance(row, dict)]
        got = [str(row.get("id") or "") for row in updates]
        if got != list(shard["units"]):
            print(f"BLOCKED shard {shard['id']} cases {got} != {list(shard['units'])}", file=sys.stderr)
            return 2
        for row in updates:
            cid = str(row["id"])
            target = by_id.get(cid)
            if target is None:
                print(f"BLOCKED shard {shard['id']} names unknown case {cid}", file=sys.stderr)
                return 2
            status = str(row.get("status") or "")
            if status not in CASE_STATUS:
                print(f"BLOCKED shard {shard['id']} status {status}", file=sys.stderr)
                return 2
            evidence = str(row.get("evidence") or "")
            home = evidence_dir(cid)
            if status in ("PASS", "FAIL"):
                if not _rel_file(evidence) or not evidence.startswith(home):
                    print(f"BLOCKED shard {shard['id']} evidence must stay under {home}", file=sys.stderr)
                    return 2
                if not (task / evidence).is_file():
                    print(f"BLOCKED shard {shard['id']} evidence file missing: {evidence}", file=sys.stderr)
                    return 2
            elif not evidence or not _rel_file(evidence):
                print(f"BLOCKED shard {shard['id']} needs an evidence note", file=sys.stderr)
                return 2
            target["status"] = status
            target["evidence"] = evidence
    plan_path.write_text(safeyaml.dump(plan), encoding="utf-8")
    print(f"OK   merged {len(result['shards'])} run shards -> {plan_path}")
    return 0


def _shard_update(task: Path, shard: dict) -> dict | str:
    """The hypothesis fields one shard may change, or an error string."""
    body = _load(task / shard["writes"][0])
    hid = shard["id"]
    if str(body.get("shard") or "") != hid:
        return f"shard file does not name {hid}"
    status = str(body.get("status") or "")
    if status not in HYPO_STATUS:
        return f"shard {hid} status {status}"
    evidence = [str(item) for item in safeyaml.as_list(body.get("evidence")) if str(item).strip()]
    note = str(body.get("note") or "")
    if status == "proven" and not evidence:
        return f"shard {hid} proven without evidence"
    if status == "disproven" and not note.strip():
        return f"shard {hid} disproven without a note"
    repro = str(body.get("repro") or "")
    if repro and repro not in hypothesis.REPRO:
        return f"shard {hid} repro {repro}"
    return {"id": hid, "status": status, "evidence": evidence, "note": note, "repro": repro}


def _merge_rootcause(task: Path, feature: str, result: dict) -> int:
    path = task / "hypotheses.yaml"
    updates = []
    for shard in result["shards"]:
        update = _shard_update(task, shard)
        if isinstance(update, str):
            print(f"BLOCKED {update}", file=sys.stderr)
            return 2
        updates.append(update)

    class Missing(Exception):
        def __init__(self, hid: str) -> None:
            self.hid = hid

    def apply(data: dict) -> dict:
        data.setdefault("schema_version", 1)
        data.setdefault("feature", feature)
        data.setdefault("items", [])
        for update in updates:
            item = hypothesis.find(safeyaml.as_list(data.get("items")), update["id"])
            if item is None:
                raise Missing(update["id"])
            have = [str(x) for x in safeyaml.as_list(item.get("evidence"))]
            for piece in update["evidence"]:
                if piece not in have:
                    have.append(piece)
            item["evidence"] = have
            item["status"] = update["status"]
            if update["note"]:
                item["note"] = update["note"]
            if update["repro"]:
                item["repro"] = update["repro"]
            item["at"] = hypothesis.now()
            data = hypothesis._merge_item(data, item)
        return data

    try:
        safeyaml.save_locked(path, apply)
    except Missing as exc:
        print(f"BLOCKED no such hypothesis: {exc.hid}", file=sys.stderr)
        return 2
    print(f"OK   merged {len(result['shards'])} rootcause shards -> {path}")
    return 0


def merge(feature: str, activity: str, repo: Path | None = None) -> int:
    if activity not in ACTIVITIES:
        print(f"BLOCKED unknown activity {activity}", file=sys.stderr)
        return 2
    task = task_of(feature, repo)
    path = manifest_path(task, activity)
    result = _load(path)
    if result.get("decision") != "FANOUT" or result.get("activity") != activity:
        print(f"BLOCKED {path} is not a FANOUT manifest for {activity}", file=sys.stderr)
        return 2
    moved = _guard_ok(task, result)
    if moved:
        print(f"BLOCKED {moved} changed after assess; a shard must not write it", file=sys.stderr)
        return 2
    for shard in safeyaml.as_list(result.get("shards")):
        rel = (shard.get("writes") or [""])[0]
        if not (task / rel).is_file():
            print(f"BLOCKED missing shard file {rel}", file=sys.stderr)
            return 2
    if activity == "plan":
        return _merge_plan(task, result)
    if activity == "report":
        return _merge_report(task, result)
    if activity == "rootcause":
        return _merge_rootcause(task, feature, result)
    return _merge_run(task, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    assess_cmd = sub.add_parser("assess", help="decide SERIAL or FANOUT")
    assess_cmd.add_argument("--feature", required=True)
    assess_cmd.add_argument("--activity", required=True, choices=ACTIVITIES)
    assess_cmd.add_argument("--cap", type=int, default=DEFAULT_CAP)

    merge_cmd = sub.add_parser("merge", help="fold shard files into the single ledger")
    merge_cmd.add_argument("--feature", required=True)
    merge_cmd.add_argument("--activity", required=True, choices=ACTIVITIES)

    args = parser.parse_args(argv)
    if args.repo is None and os.environ.get("IDEV_PRODUCT_REPO"):
        args.repo = Path(os.environ["IDEV_PRODUCT_REPO"])
    if args.cmd == "assess":
        result = assess(args.feature, args.activity, args.repo, args.cap)
        written = write_manifest(args.feature, result, args.repo)
        print(render(result, args.feature))
        if written is not None:
            print(f"MANIFEST {written}")
        return 0
    return merge(args.feature, args.activity, args.repo)


if __name__ == "__main__":
    raise SystemExit(main())
