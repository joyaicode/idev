#!/usr/bin/env python3
"""Drive an S8 run from its recipe yaml.

The recipe is the artifact; run.yaml is its instance. This tool binds
params, writes run.yaml, names the next step and the page that executes it,
and records step results. It never executes a step: the agent does that in
the module the step lands on.

  workflow.py resolve <id>
  workflow.py start <id> [--feature F] [--param k=v ...]
  workflow.py next    [--feature F | --run PATH]
  workflow.py delegate <step>
  workflow.py delegate --open
  workflow.py ask     <step>
  workflow.py record  <step> <STATUS> [--evidence P] [--by NAME --quote TEXT] [--note TEXT]
                      [--verified-by AGENT --verify-evidence P]
  workflow.py decide  <step> --signal S --question Q --answer A --quote TEXT [--options O] [--recommend R]
  workflow.py status  [--feature F | --run PATH]
  workflow.py abort   --note TEXT [--feature F | --run PATH]

A human.gate is signed by the person's chat reply. `record <gate> PASS
--by <name> --quote "确认"` is the signoff (确认 / 全签 / 同意 / LGTM).
`ask` plus `idev gate approve` in their terminal still works, and is not
required.

Exit codes: 0 ok, 1 usage or invalid recipe, 2 BLOCKED (missing inputs or a
rule refused the write).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import doc_home  # noqa: E402
import ids  # noqa: E402
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402
import workflow_defaults  # noqa: E402
from product_marker import resolve_extension_repo  # noqa: E402
from product_sink import kernel_root, product_repo, sink_dir  # noqa: E402
from workflow_spec import (  # noqa: E402
    KINDS,
    STEP_DONE,
    STEP_STATUS,
    STEP_STOP,
    auto_tiers,
    check_recipe,
    check_run,
    is_answer,
    is_human,
    parse_confirm,
    people_whitelist,
    will_write_line,
)

try:
    import yaml
except ImportError:
    yaml = None


class Blocked(Exception):
    pass


# Why a quote was refused, in the words a person would use. The parser knows
# the reason; saying only "needs confirm words" sends them to re-type the
# same sentence.
WHY = {
    "no-verb": "it does not start with one of those words",
    "question": "it reads as a question, not a decision",
    "negation": "it contains a refusal",
    "hesitation": "it reads as hesitation, not a decision",
    "unparsed-tail": "there is more in it than a confirmation",
    "keyword-mismatch": "this gate needs its keyword (origin=… / 解除密封)",
}


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def load_yaml(path: Path) -> Any:
    if yaml is None:
        raise SystemExit("workflow.py requires PyYAML")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump_yaml(path: Path, data: Any) -> None:
    """Write a run file so a reader never sees it half-written.

    `path.write_text` truncates first, so a crash — or a reader arriving in
    the middle — leaves a run.yaml that parses as something other than the
    run. Temp file plus `os.replace` makes the swap atomic on the same
    filesystem. Serialization goes through safeyaml so this file and the
    three ledgers cannot drift into two dialects of yaml.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, safeyaml.dump(data))


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def session_repo(arg: str) -> Path | None:
    return product_repo(Path(arg).expanduser().resolve() if arg else None)


def resolve(workflow_id: str, repo: Path | None) -> Path:
    if repo is not None:
        pages, err = resolve_extension_repo(repo)
        if err:
            raise Blocked(err)
        if pages is not None:
            candidate = pages / ".idev" / "workflows" / f"{workflow_id}.yaml"
            if candidate.is_file():
                return candidate
    kernel_one = kernel_root() / "workflows" / f"{workflow_id}.yaml"
    if kernel_one.is_file():
        return kernel_one
    raise Blocked(f"no recipe {workflow_id} in the product .idev/workflows or idev workflows")


def bind_params(recipe: dict, given: dict[str, str], repo: Path | None, deliver: Path | None) -> dict:
    bound: dict[str, Any] = {}
    missing: list[str] = []
    defaults: dict | None = None
    for param in recipe.get("params") or []:
        name, src = param["name"], param["from"]
        value: Any = given.get(name)
        if value is None and src == "default":
            value = param.get("default")
        elif value is None and src == "deliver.yaml" and deliver is not None and deliver.is_file():
            value = (load_yaml(deliver) or {}).get(name)
        elif value is None and src == "product" and repo is not None:
            if defaults is None:
                dest, _ = workflow_defaults.defaults_file(repo)
                defaults = load_yaml(dest) if dest is not None and dest.is_file() else {}
            value = workflow_defaults._lookup(defaults or {}, str(param.get("product_key") or name))
        if value is None or (isinstance(value, str) and not value.strip()):
            if param.get("required"):
                missing.append(f"{name} (from {src})")
            continue
        bound[name] = value
    unknown = sorted(set(given) - {p["name"] for p in recipe.get("params") or []})
    if unknown:
        raise Blocked("unknown params: " + ", ".join(unknown))
    if missing:
        raise Blocked("missing params: " + "; ".join(missing))
    return bound


def run_path_for(recipe: dict, feature: str, repo: Path | None) -> Path:
    if feature and repo is not None:
        return doc_home.homes(repo, feature)["task"] / "workflow" / "run.yaml"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return sink_dir("workflow-runs", start=repo) / f"{recipe['id']}-{stamp}.yaml"


def find_run(args: argparse.Namespace) -> Path:
    if args.run:
        return Path(args.run).expanduser().resolve()
    repo = session_repo(args.repo)
    if args.feature:
        if repo is None:
            raise Blocked("a ticket run needs a product checkout; cd into it or pass --repo")
        path = doc_home.homes(repo, args.feature)["task"] / "workflow" / "run.yaml"
        if not path.is_file():
            raise Blocked(f"no run for {args.feature}: {path}")
        return path
    live = []
    runs = sink_dir("workflow-runs", start=repo)
    for path in sorted(runs.glob("*.yaml"), key=lambda p: p.stat().st_mtime, reverse=True):
        if (load_yaml(path) or {}).get("status") in ("running", "blocked"):
            live.append(path)
    if len(live) == 1:
        return live[0]
    if not live:
        raise Blocked("no live run; pass --feature or --run")
    raise Blocked("several live runs; pass --run: " + ", ".join(str(p) for p in live))


def decisions_path(run_path: Path) -> Path:
    """The ticket's decision ledger, or one beside a ticketless run file."""
    if run_path.name == "run.yaml":
        return run_path.parent.parent / "decisions.yaml"
    return run_path.with_name(run_path.stem + ".decisions.yaml")


def latest_delegation(run_path: Path, step_id: str) -> dict | None:
    """The newest delegation record for a step of a ticket run, if any."""
    if run_path.name != "run.yaml":
        return None
    best: tuple[int, dict] | None = None
    for path in (run_path.parent / "delegations").glob(f"{step_id}-*.yaml"):
        data = safeyaml.mapping(path) or {}
        if str(data.get("step")) != step_id:
            continue
        attempt = safeyaml.as_int(data.get("attempt"), 1)
        if best is None or attempt > best[0]:
            best = (attempt, data)
    return best[1] if best else None


def unanswered(run_path: Path, step_id: str) -> list[str]:
    """Signals from the latest delegation of this step that no decision answers."""
    record = latest_delegation(run_path, step_id)
    if not record:
        return []
    attempt = safeyaml.as_int(record.get("attempt"), 1)
    ledger = safeyaml.mapping(decisions_path(run_path)) if decisions_path(run_path).is_file() else None
    answered = {
        str(d.get("signal"))
        for d in ((ledger or {}).get("decisions") or [])
        if str(d.get("step")) == step_id and safeyaml.as_int(d.get("attempt"), 1) == attempt
    }
    return [s for s in (record.get("signals") or []) if str(s) not in answered]


def ticket_of(run_path: Path) -> Path:
    return run_path.parent.parent if run_path.name == "run.yaml" else run_path.parent


def cites(blob: str, evidence: str) -> bool:
    """True when evidence is its own token, not a suffix of a longer path."""
    if not evidence:
        return False
    for token in blob.split():
        if token == evidence or token.removeprefix("EVIDENCE:") == evidence:
            return True
    return False


def report_text(data: dict) -> str:
    report = data.get("report") or {}
    if not isinstance(report, dict):
        return ""
    return f"{report.get('raw') or ''}\n{report.get('evidence') or ''}"


def independent_refusal(run_path: Path, step: dict, verifier: str, evidence: str) -> str:
    """Why this PASS is not an independent review, or "" when it is.

    The flags alone are a claim. The report file has to be on disk, and a
    delegation recorded by the verifier — not by the writer of this step —
    has to cite that same path.
    """
    target = Path(evidence)
    if not target.is_absolute():
        ticket = ticket_of(run_path)
        target = next((p for p in (ticket / evidence, Path.cwd() / evidence) if p.is_file()), ticket / evidence)
    if not target.is_file():
        return f"verify-evidence not found: {evidence} (the verifier writes that file first)"
    if not target.read_text(encoding="utf-8", errors="replace").strip():
        return f"verify-evidence is empty: {evidence}"
    writer = str((step.get("delegated") or {}).get("agent") or "")
    if not writer:
        rec = latest_delegation(run_path, str(step.get("id") or ""))
        writer = str((rec or {}).get("agent") or "")
    if writer == verifier:
        return (
            f"{verifier} is the writer of {step['id']}; "
            "independent verification has to come from the other agent"
        )
    folder = run_path.parent / "delegations"
    if folder.is_dir():
        for path in sorted(folder.glob("*.yaml")):
            data = safeyaml.mapping(path) or {}
            if str(data.get("agent") or "") != verifier:
                continue
            if cites(report_text(data), evidence):
                return ""
    return (
        f"no report from {verifier} cites {evidence}; "
        "that agent records its own delegation, then this PASS points --verify-evidence at that report"
    )


def auto_refusal(run_path: Path, evidence: str) -> str:
    """Why a saved check output cannot stand in for a person, or "" if it can.

    The output must end clean (a `0 FAIL` line, as check-feature and
    stage-gate print) and raise no SIGNAL: a signal is a question for a person.
    """
    target = Path(evidence)
    if not target.is_absolute():
        ticket = ticket_of(run_path)
        target = next((p for p in (ticket / evidence, Path.cwd() / evidence) if p.is_file()), ticket / evidence)
    if not target.is_file():
        return f"AUTO evidence not found: {evidence} (save the check output there first)"
    lines = [line.strip() for line in target.read_text(encoding="utf-8", errors="replace").splitlines()]
    signals = [line for line in lines if line.startswith("SIGNAL ")]
    if signals:
        return ("AUTO refused: the checks raised a question for a person — "
                + "; ".join(s[len("SIGNAL "):] for s in signals))
    if "0 FAIL" not in lines:
        return f"AUTO needs a clean check output (a '0 FAIL' line) in {evidence}"
    return ""


def go_engine() -> bool:
    return (os.environ.get("IDEV_ENGINE") or "go").strip().lower() != "python"


def idev(*argv: str) -> dict:
    """Run the gate channel and parse its JSON; a refusal becomes Blocked."""
    exe = os.environ.get("IDEV_BIN", "").strip() or None
    if exe is None:
        built = kernel_root() / "bin" / "idev"
        exe = str(built) if built.is_file() else shutil.which("idev")
    if not exe or not Path(exe).is_file():
        raise Blocked(
            "human.gate needs the idev binary: go build -o bin/idev ./cmd/idev in the kernel "
            "(or set IDEV_BIN); IDEV_ENGINE=python falls back to --by / --quote"
        )
    proc = subprocess.run([exe, *argv], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise Blocked((proc.stderr or proc.stdout).strip().removeprefix("idev: "))
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def pending_gate_id(message: str) -> str:
    """The id of the question a second request collided with, or ""."""
    mark = " already pending"
    i = message.find(mark)
    if i < 26:
        return ""
    cand = message[i - 26:i]
    if len(cand) == 26 and cand.isalnum() and cand == cand.upper():
        return cand
    return ""


def gate_question(run: dict, run_path: Path, step: dict) -> list[str]:
    """The `idev gate request` arguments for a recipe gate.

    The type and subject come from `with.gate_type` / `with.subject` when the
    recipe says; otherwise a gate that writes plan.yaml is accepted_plan bound
    to that file, and anything else confirms the step itself.
    """
    payload = step.get("with") or {}
    will_write = [str(w) for w in (payload.get("will_write") or [])]
    gtype = str(payload.get("gate_type") or "")
    if not gtype:
        gtype = "accepted_plan" if any("plan.yaml" in w for w in will_write) else "step_confirm"
    subject = payload.get("subject") or []
    if isinstance(subject, str):
        subject = [subject]
    ticket = ticket_of(run_path)
    if not subject and gtype == "accepted_plan" and (ticket / "verify" / "plan.yaml").is_file():
        subject = ["verify/plan.yaml"]
    proof = "; ".join(
        f"{s['id']} {s['status']}" + (f" ({s['evidence']})" if s.get("evidence") else "")
        for s in run["steps"]
        if s.get("status") in STEP_DONE
    ) or str(step.get("label") or step["id"])
    argv = [
        "gate", "request", "--feature", feature_id(run, run_path),
        "--type", gtype, "--risk", risk_tier_of(run, run_path),
        "--run-id", str(run.get("run_id") or ""), "--step", step["id"], "--proof", proof,
    ]
    for w in will_write:
        argv += ["--will-write", w]
    if subject:
        argv += ["--root", str(ticket)]
        for s in subject:
            argv += ["--subject", str(s)]
    return argv


def signed_answer(step: dict) -> dict:
    """The person's answer to a gate as the channel recorded it, or Blocked."""
    gid = str((step.get("gate") or {}).get("id") or "")
    if not gid:
        raise Blocked(f"{step['id']} has not been asked: workflow.py ask {step['id']}")
    state = idev("gate", "status", gid)
    status = state.get("status")
    if status == "pending":
        raise Blocked(
            "waiting for the person: record PASS --by <name> --quote \"<their 确认>\", "
            f"or they answer in their own terminal with `idev gate approve {gid}`"
        )
    if status == "expired":
        raise Blocked(f"gate {gid} expired unanswered; ask again: workflow.py ask {step['id']}")
    if status != "approved":
        who = (state.get("approval") or {}).get("handle", "the person")
        raise Blocked(f"{who} answered 驳回 on gate {gid}; record {step['id']} FAIL, or change and ask again")
    approval = state.get("approval") or {}
    if not approval.get("signature_ok"):
        raise Blocked(f"approval {approval.get('id')} does not verify against this machine's key")
    if not state.get("digest_match"):
        raise Blocked(f"what gate {gid} approved has changed since; ask again: workflow.py ask {step['id']}")
    return {
        "by": approval["handle"],
        "quote": approval["quote"],
        "at": approval["decided_at"],
        "approval_id": approval["id"],
        "assurance": approval["assurance"],
        **({"assurance_downgraded": True} if approval.get("downgraded") else {}),
    }


def feature_id(run: dict, run_path: Path) -> str:
    """The key gates and leases are scoped by: the ticket directory, so two
    checkouts that both have a `demo` ticket do not share one write lease."""
    if run_path.name == "run.yaml":
        return str(ticket_of(run_path).resolve())
    return str(run.get("feature") or "-")


def live_tokens(run: dict) -> list[tuple[str, str]]:
    """Lease id and bearer token still stored on any step.

    The token stays in run.yaml until release succeeds. Dropping it first
    locks the feature until the TTL: the lease is still held, and nobody
    can present the token again.
    """
    out = []
    for step in run.get("steps") or []:
        held = step.get("lease") or {}
        if held.get("id") and held.get("token"):
            out.append((str(held["id"]), str(held["token"])))
    return out


def drop_released(run: dict, released: set[str]) -> None:
    for step in run.get("steps") or []:
        held = step.get("lease") or {}
        if held.get("id") in released and held.get("token"):
            held.pop("token", None)
            held["released_at"] = now()


def release_kept(path: Path, pairs: list[tuple[str, str]]) -> list[str]:
    """Release each lease. A failure leaves that token in run.yaml.

    Returns the lease ids that are still held.
    """
    released: set[str] = set()
    failed: list[str] = []
    for lease_id, token in pairs:
        try:
            idev("lease", "release", lease_id, "--token", token)
        except Blocked as exc:
            print(
                f"WARN lease {lease_id} not released ({exc}); "
                "the token stays in run.yaml so the next delegate can retry"
            )
            failed.append(lease_id)
            continue
        print(f"LEASE {lease_id} released")
        released.add(lease_id)
    if released:
        def mutate(run: dict) -> dict:
            if not run or "steps" not in run:
                raise Blocked(f"{path} is empty or unreadable; not dropping lease tokens")
            drop_released(run, released)
            return run

        safeyaml.save_locked(path, mutate)
    return failed


def lease_purpose(run: dict, step: dict) -> str | None:
    """The lease this step needs on a ticket run under the Go engine:
    "write" fences the arch.yaml includes, "verify" fences the ticket directory."""
    purpose = kind_agents.KIND_LEASE.get(step["kind"])
    if go_engine() and purpose in ("write", "verify") and str(run.get("feature") or "-") != "-":
        return purpose
    return None


def ticket_dir_repo_relative(run_path: Path, repo: Path | None) -> str:
    """The ticket directory as the repository sees it: what a verify lease is fenced to."""
    ticket = ticket_of(run_path).resolve()
    roots = [repo.resolve()] if repo is not None else []
    roots += [p for p in ticket.parents if (p / ".git").is_dir()]
    for root in roots:
        try:
            return ticket.relative_to(root).as_posix()
        except ValueError:
            continue
    raise Blocked(f"{ticket} is not inside a git repository; a verify lease needs one")


def arch_includes(run_path: Path) -> list[str]:
    """The paths a person included in arch.yaml: what a write lease may touch."""
    arch = ticket_of(run_path) / "arch.yaml"
    data = safeyaml.mapping(arch) if arch.is_file() else {}
    return [
        str(c["path"]).strip()
        for c in (data or {}).get("impact_candidates") or []
        if isinstance(c, dict) and c.get("include") is True and str(c.get("path") or "").strip()
    ]


def changed_paths(run_path: Path, step_id: str) -> list[str]:
    """The files the latest delegation report says it changed."""
    _has_report, _has_line, paths = delegation_changed(run_path, step_id)
    return paths


def delegation_changed(run_path: Path, step_id: str) -> tuple[bool, bool, list[str]]:
    """Whether a delegation exists, whether it declared CHANGED, and the paths."""
    import delegation  # noqa: PLC0415 - scripts/, imported only when a report is read

    record = latest_delegation(run_path, step_id)
    if not record:
        return False, False, []
    raw = str((record.get("report") or {}).get("raw", ""))
    hit = delegation.CHANGED_LINE.search(raw)
    if not hit:
        return True, False, []
    if delegation.NONE_VALUE.match(hit.group(1)):
        return True, True, []
    return True, True, sorted(delegation._paths(hit.group(1)))


def ticket_tree(ticket: Path) -> dict[str, str]:
    """Hash of each file in the ticket, excluding the workflow bookkeeping directory."""
    found: dict[str, str] = {}
    if not ticket.is_dir():
        return found
    for path in ticket.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ticket).as_posix()
        if rel == "workflow" or rel.startswith("workflow/"):
            continue
        found[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def stamp_open_group(run: dict, ticket: Path) -> None:
    """Remember the ticket as the wave opens, so a later record can see what changed."""
    opened = open_steps(run)
    if not opened or not opened[0].get("group"):
        return
    if all(isinstance(step.get("tree"), dict) for step in opened):
        return
    tree = ticket_tree(ticket)
    for step in opened:
        if not isinstance(step.get("tree"), dict):
            step["tree"] = dict(tree)


def group_writes(run: dict, step: dict) -> list[str]:
    group = step.get("group")
    owned: list[str] = []
    for item in run.get("steps") or []:
        if item.get("group") == group:
            owned.extend(str(w) for w in (item.get("writes") or []) if str(w).strip())
    return owned


def disk_outside_group(run: dict, step: dict, ticket: Path) -> list[str]:
    """Ticket files changed since the wave opened that no member of the group may write."""
    tree = step.get("tree")
    if not isinstance(tree, dict) or not step.get("writes"):
        return []
    allowed = group_writes(run, step)
    now = ticket_tree(ticket)
    outside: list[str] = []
    for rel in sorted(set(tree) | set(now)):
        if tree.get(rel) == now.get(rel):
            continue
        if covered_by_writes(allowed, rel):
            continue
        outside.append(rel)
    return outside


def covered_by_writes(writes: list[str], path: str) -> bool:
    """True when a reported path is exactly one writes entry, or sits under a directory entry."""
    norm = path.replace("\\", "/").lstrip("./")
    if not norm or ".." in Path(norm).parts:
        return False
    for raw in writes:
        write = str(raw).replace("\\", "/").strip().lstrip("./")
        if not write:
            continue
        if norm == write or norm.endswith("/" + write):
            return True
        if write.endswith("/") and norm.startswith(write):
            return True
    return False


def writes_block(step_id: str, writes: list[str], has_report: bool, has_line: bool, changed: list[str]) -> str:
    """Refuse a grouped step whose report writes something else, or never says what it wrote."""
    if not writes or not has_report:
        return ""
    allowed = ", ".join(writes)
    if not has_line:
        return (
            f"{step_id} report needs a CHANGED line (无 if it wrote nothing); "
            f"this step writes only {allowed}"
        )
    outside = [path for path in changed if not covered_by_writes(writes, path)]
    if outside:
        return (
            f"{step_id} changed files outside its writes ({allowed}): "
            + ", ".join(outside)
            + " — revert them; this step writes only those paths"
        )
    return ""


def risk_tier_of(run: dict, run_path: Path) -> str:
    """The ticket's risk_tier, else the recipe's, else the P1 default."""
    if run_path.name == "run.yaml":
        deliver = run_path.parent.parent / "deliver.yaml"
        if deliver.is_file():
            tier = (safeyaml.mapping(deliver) or {}).get("risk_tier")
            if tier:
                return str(tier)
    recipe = Path(str(run.get("recipe") or ""))
    if recipe.is_file():
        tier = (load_yaml(recipe) or {}).get("risk_tier")
        if tier:
            return str(tier)
    return "P1"


def current_step(run: dict) -> dict | None:
    for step in run["steps"]:
        if step.get("status") not in STEP_DONE:
            return step
    return None


def open_steps(run: dict) -> list[dict]:
    """Steps that may be recorded or delegated now.

    A step with no group is alone. A contiguous group is open together, from
    the first unfinished member through the last member of that group. Steps
    after the group stay closed until every member is done.
    """
    steps = run.get("steps") or []
    start = next((i for i, step in enumerate(steps) if step.get("status") not in STEP_DONE), None)
    if start is None:
        return []
    group = steps[start].get("group")
    if not group:
        return [steps[start]]
    opened: list[dict] = []
    for step in steps[start:]:
        if step.get("group") != group:
            break
        if step.get("status") not in STEP_DONE:
            opened.append(step)
    return opened


def _step_open(run: dict, step: dict) -> bool:
    return any(item is step for item in open_steps(run))


def next_line(run: dict) -> list[str]:
    if run["status"] in ("done", "aborted"):
        return [f"RUN {run['status'].upper()}"]
    opened = open_steps(run)
    if not opened:
        return ["RUN DONE"]
    blocks = [_step_lines(run, step) for step in opened]
    if len(blocks) == 1:
        lines = blocks[0]
    else:
        lines = [f"PARALLEL {opened[0].get('group')}"]
        for i, block in enumerate(blocks):
            if i:
                lines.append("---")
            lines.extend(block)
    if run["status"] == "blocked":
        lines.insert(0, "RUN BLOCKED; fix this step, then record it again")
    return lines


def _step_lines(run: dict, step: dict) -> list[str]:
    kind = step["kind"]
    lines = [
        f"NEXT {step['id']}  kind={kind}  status={step.get('status', 'pending')}",
        f"OPEN {KINDS.get(kind, '-')}",
        kind_agents.delegate_line(kind),
    ]
    if step.get("label"):
        lines.append(f"LABEL {step['label']}")
    if step.get("group"):
        lines.append(f"GROUP {step['group']}")
    if step.get("writes"):
        lines.append("WRITES " + ", ".join(step["writes"]))
    if step.get("with"):
        lines.append(f"WITH {step['with']}")
    key = workflow_defaults.KIND_COMMANDS.get(kind)
    if key:
        lines.append(f"COMMAND workflow-defaults.yaml {key}")
    if kind == "human.gate":
        tiers = auto_tiers(step)
        if tiers:
            lines.append(
                f"GATE at {'/'.join(sorted(tiers))}: save the check output (0 FAIL, no SIGNAL) "
                "and record AUTO --evidence <that file>; a SIGNAL or another tier means stop and ask"
            )
        lines.append(f"GATE stop here; post this line and the proof: {will_write_line(step)}")
        lines.append(
            "GATE the person's reply of 确认 / 同意 / 全签 / LGTM is the signoff; "
            "record PASS --by <name> --quote \"<their words>\""
        )
    purpose = lease_purpose(run, step)
    if purpose == "write":
        lines.append(f"LEASE workflow.py delegate {step['id']} before the agent starts; it writes only arch.yaml includes")
    elif purpose == "verify":
        lines.append(f"LEASE workflow.py delegate {step['id']} before the verifier starts; it writes only inside the ticket")
    verifier = kind_agents.KIND_VERIFIER.get(kind)
    if verifier:
        lines.append(f"VERIFY {verifier} confirms before PASS: --verified-by {verifier} --verify-evidence <report>")
    return lines


def write_report(run_path: Path, run: dict) -> Path:
    report = run_path.with_name("report.md") if run_path.name == "run.yaml" else run_path.with_suffix(".md")
    rows = [f"# {run['workflow_id']} · {run['feature']} · {run['status']}", "", "| step | kind | status | evidence |", "|---|---|---|---|"]
    for step in run["steps"]:
        rows.append(f"| {step['id']} | {step['kind']} | {step.get('status', 'pending')} | {step.get('evidence', '')} |")
    if run.get("revisions"):
        rows += ["", "## revisions", ""]
        rows += [f"- {r['at']} {r.get('step', '')} {r['note']}" for r in run["revisions"]]
    report.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(report, "\n".join(rows) + "\n")
    return report


def cmd_resolve(args: argparse.Namespace) -> int:
    print(resolve(args.workflow, session_repo(args.repo)))
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    repo = session_repo(args.repo)
    recipe_path = resolve(args.workflow, repo)
    recipe = load_yaml(recipe_path)
    errors: list[str] = []
    check_recipe(recipe, recipe_path, errors)
    if errors:
        for err in errors:
            print("FAIL " + err, file=sys.stderr)
        return 1
    given = {}
    for item in args.param or []:
        if "=" not in item:
            raise SystemExit(f"--param wants k=v, got {item!r}")
        key, value = item.split("=", 1)
        given[key.strip()] = value
    feature = args.feature or str(given.get("feature") or "")
    needs_ticket = recipe.get("needs_ticket") is not False
    deliver = None
    if feature:
        if repo is None:
            raise Blocked("a ticket run needs a product checkout; cd into it or pass --repo")
        if any(p["name"] == "feature" for p in recipe.get("params") or []):
            given.setdefault("feature", feature)
        deliver = doc_home.homes(repo, feature)["deliver"]
    if needs_ticket:
        if not feature:
            raise Blocked(f"{recipe['id']} needs a ticket: pass --feature")
        if deliver is None or not deliver.is_file():
            raise Blocked(f"missing {deliver}")
    params = bind_params(recipe, given, repo, deliver)
    if repo is not None:
        code, lines = workflow_defaults.check_recipe(repo, recipe_path)
        if code:
            raise Blocked("; ".join(lines))
    run_path = run_path_for(recipe, feature, repo)
    run = {
        "schema_version": 1,
        # Written, never read. idevd keys runs on this from P2 on; writing it
        # now means the runs created during the migration already have the
        # identity the Go side will look for.
        "run_id": ids.ulid(),
        "workflow_id": recipe["id"],
        "recipe": str(recipe_path),
        "feature": feature or "-",
        "status": "running",
        "started_at": now(),
        "params": params,
        "policy": recipe.get("policy") or {},
        "steps": [
            {k: step[k] for k in ("id", "kind", "label", "with", "group", "writes") if k in step}
            for step in recipe["steps"]
        ],
        "revisions": [],
        "feedback": {"status": "pending"},
    }
    stamp_open_group(run, ticket_of(run_path))
    claim_run(run_path, run)
    write_report(run_path, run)
    print(f"RUN {run_path}")
    print("\n".join(next_line(run)))
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    run = load_yaml(find_run(args))
    print("\n".join(next_line(run)))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    path = find_run(args)
    run = load_yaml(path)
    print(f"RUN {path}  {run['workflow_id']}  {run['status']}")
    for step in run["steps"]:
        print(f"  {step.get('status', 'pending'):9} {step['id']}  {step['kind']}")
    return 0


def chat_signoff(by: str, quote: str) -> dict:
    """The signoff a person's chat reply is. Their words, recorded as they said them."""
    if not people_whitelist():
        raise Blocked(
            "human.gate PASS needs a people.yaml whitelist; "
            "blacklist-only is not enough"
        )
    if not is_human(by or ""):
        raise Blocked("human.gate PASS needs --by with a person's name, not an agent")
    parsed = parse_confirm(quote or "")
    if not parsed.ok:
        raise Blocked(
            f"human.gate PASS needs --quote with the person's confirm words "
            f"(确认 / 全签 / 同意 / LGTM); {WHY[parsed.reason]}"
        )
    return {"by": by.strip(), "quote": quote.strip(), "at": now(), "assurance": "chat"}


def cmd_record(args: argparse.Namespace) -> int:
    path = find_run(args)
    status = args.status.upper()
    if status not in STEP_STATUS:
        raise SystemExit(f"status must be one of {sorted(STEP_STATUS)}")

    # The yaml lock only covers the read-modify-write. idev is a subprocess
    # and must not run while that lock is held, or every other writer of this
    # run waits on the database. The facts those calls return are applied
    # under the lock only if the step is still the one they were read from.
    done: dict = {}
    pre: dict = {}

    def peek(run: dict) -> None:
        if not run or "steps" not in run or run.get("status") not in ("running", "blocked"):
            return
        step = next((s for s in run["steps"] if s["id"] == args.step), None)
        if step is None:
            return
        held = step.get("lease") or {}
        purpose = lease_purpose(run, step) if status == "PASS" else None
        writes = [str(w) for w in (step.get("writes") or []) if str(w).strip()]
        has_report, has_line, write_changed = (False, False, [])
        if writes:
            has_report, has_line, write_changed = delegation_changed(path, step["id"])
        disk_outside = disk_outside_group(run, step, ticket_of(path)) if writes else []
        pre.update(
            seen=True,
            kind=step["kind"],
            gate_id=str((step.get("gate") or {}).get("id") or ""),
            lease_id=str(held.get("id") or ""),
            purpose=purpose,
            changed=changed_paths(path, step["id"]) if purpose else [],
            writes=writes,
            has_report=has_report,
            has_changed=has_line,
            write_changed=write_changed,
            disk_outside=disk_outside,
            group_writes=group_writes(run, step) if writes else [],
            verifier=kind_agents.KIND_VERIFIER.get(step["kind"]),
        )

    safeyaml.load_locked(path, peek)
    verifier_pre = pre.get("verifier")
    flags_missing = bool(
        verifier_pre and status == "PASS"
        and (args.verified_by != verifier_pre or not args.verify_evidence)
    )
    signed = None
    if (pre.get("seen") and not flags_missing and pre.get("kind") == "human.gate"
            and status == "PASS" and go_engine() and not (args.by or args.quote)
            and pre.get("gate_id")):
        signed = signed_answer({"id": args.step, "gate": {"id": pre["gate_id"]}})
    if (pre.get("seen") and not flags_missing and pre.get("purpose")
            and pre.get("lease_id") and pre.get("changed")):
        outside = idev(
            "lease", "check", pre["lease_id"],
            *[a for p in pre["changed"] for a in ("--path", p)],
        ).get("outside") or []
        if outside:
            if pre["purpose"] == "verify":
                raise Blocked(
                    f"{args.step} changed files outside its lease (the ticket directory): "
                    + ", ".join(outside)
                    + " — revert them; a verify lease covers only the ticket directory"
                )
            raise Blocked(
                f"{args.step} changed files outside its lease (arch.yaml include): "
                + ", ".join(outside)
                + " — revert them, or include them in arch.yaml and delegate again"
            )
    if pre.get("writes"):
        blocked = writes_block(
            args.step,
            pre["writes"],
            bool(pre.get("has_report")),
            bool(pre.get("has_changed")),
            list(pre.get("write_changed") or []),
        )
        if blocked:
            raise Blocked(blocked)
        outside_disk = list(pre.get("disk_outside") or [])
        if outside_disk:
            allowed = ", ".join(pre.get("group_writes") or [])
            raise Blocked(
                f"{args.step} disk changed files outside the group writes ({allowed}): "
                + ", ".join(outside_disk)
                + " — revert them; this wave writes only those paths"
            )

    def mutate(run: dict) -> dict:
        if not run or "steps" not in run:
            raise Blocked(f"{path} is empty or unreadable; not overwriting it")
        if run["status"] not in ("running", "blocked"):
            raise Blocked(f"run is {run['status']}; start a new one")
        steps = {s["id"]: s for s in run["steps"]}
        step = steps.get(args.step)
        if step is None:
            raise Blocked(f"no step {args.step} in this run")
        if not _step_open(run, step):
            if "status" not in step:
                cur = current_step(run)
                who = cur["id"] if cur else "the open steps"
                raise Blocked(f"finish {who} first; record it SKIPPED to skip")
            if not args.note:
                raise Blocked(f"{step['id']} is already {step['status']}; changing it needs --note")
        if step["kind"] == "human.gate":
            if status == "PASS" and (args.by or args.quote or not go_engine()):
                step["signoff"] = chat_signoff(args.by or "", args.quote or "")
            elif status == "PASS" and go_engine():
                gid = str((step.get("gate") or {}).get("id") or "")
                if not gid:
                    raise Blocked(
                        f"{step['id']} needs the person's confirm words: "
                        "record PASS --by <name> --quote \"确认\""
                    )
                if signed is None or gid != str(pre.get("gate_id") or ""):
                    raise Blocked(f"{step['id']} changed while it was being recorded; record again")
                step["signoff"] = signed
            elif status == "SKIPPED" and not args.evidence:
                raise Blocked(
                    "a gate is skipped only with --evidence: the earlier signoff, "
                    "or the file that shows nothing is left to sign"
                )
            elif status == "AUTO":
                tier = risk_tier_of(run, path)
                if tier not in auto_tiers(step):
                    raise Blocked(
                        f"{step['id']} may not pass on machine checks at {tier}; "
                        "it needs a person's signoff"
                    )
                if not args.evidence:
                    raise Blocked("AUTO needs --evidence of the machine checks that passed")
                if args.by or args.quote:
                    raise Blocked("AUTO is not a signoff; drop --by / --quote")
                refusal = auto_refusal(path, args.evidence)
                if refusal:
                    raise Blocked(refusal)
        elif status == "AUTO":
            raise Blocked("AUTO is only for a human.gate that declares auto_tiers")
        verifier = kind_agents.KIND_VERIFIER.get(step["kind"])
        if verifier and status == "PASS":
            if args.verified_by != verifier or not args.verify_evidence:
                raise Blocked(
                    f"{step['kind']} needs independent verification: "
                    f"--verified-by {verifier} --verify-evidence <its report>"
                )
        held = step.get("lease") or {}
        purpose = lease_purpose(run, step) if status == "PASS" else None
        if purpose:
            if not held.get("id"):
                if purpose == "verify":
                    raise Blocked(
                        f"{step['id']} writes ticket artifacts and was never given a verify lease: "
                        f"workflow.py delegate {step['id']} before the verifier starts"
                    )
                raise Blocked(
                    f"{step['id']} writes product code and was never given a write lease: "
                    f"workflow.py delegate {step['id']} before the agent starts"
                )
            changed = changed_paths(path, step["id"])
            if changed != list(pre.get("changed") or []) or str(held.get("id") or "") != str(pre.get("lease_id") or ""):
                raise Blocked(f"{step['id']} changed while it was being recorded; record again")
        if verifier and status == "PASS":
            refusal = independent_refusal(path, step, verifier, args.verify_evidence)
            if refusal:
                raise Blocked(refusal)
            step["verification"] = {"by": args.verified_by, "evidence": args.verify_evidence, "at": now()}
        if held.get("token"):
            # Released after the record is durable. Popping here would throw
            # the token away before release is known to have succeeded.
            done["release"] = [(held["id"], held["token"])]
        if status == "PASS":
            open_signals = unanswered(path, step["id"])
            if open_signals:
                raise Blocked(
                    f"{step['id']} has signals waiting for a person's decision: "
                    + "; ".join(open_signals)
                    + f" — ask, then: workflow.py decide {step['id']} --signal ..."
                )
        if "status" in step:
            note = args.note or "recorded again"
            run.setdefault("revisions", []).append(
                {"at": now(), "step": step["id"], "note": f"{step['status']} -> {status}: {note}"}
            )
        elif args.note:
            step["note"] = args.note
        step["status"] = status
        step["at"] = now()
        if args.evidence:
            step["evidence"] = args.evidence
        if any(s.get("status") in STEP_STOP for s in run["steps"]):
            run["status"] = "blocked"
        elif current_step(run) is None:
            run["status"] = "done"
        else:
            run["status"] = "running"
        stamp_open_group(run, ticket_of(path))
        errors: list[str] = []
        check_run(run, path, errors)
        if errors:
            raise Blocked("; ".join(errors))
        done["run"] = run
        done["step"] = step
        return run

    safeyaml.save_locked(path, mutate)
    run, step = done["run"], done["step"]
    # The report is a view of the run. Write it only after run.yaml is the
    # new bytes, so a failed save cannot leave the report ahead of the run.
    write_report(path, run)
    release_kept(path, done.get("release") or [])
    if status in STEP_STOP:
        ask = (run.get("policy") or {}).get("on_fail") == "ask"
        print(f"BLOCKED {step['id']} {status}; " + ("ask the person how to go on" if ask else "stop; fix and record again"))
    print("\n".join(next_line(run)))
    return 0


def cmd_delegate(args: argparse.Namespace) -> int:
    """Hand the current step, or every open agent step, to its agent."""
    path = find_run(args)
    if args.open:
        if args.step:
            raise SystemExit("delegate --open does not take a step")
        run = load_yaml(path) or {}
        opened = [
            step for step in open_steps(run)
            if kind_agents.KIND_AGENTS.get(step["kind"], "-") != "-"
        ]
        if not opened:
            raise Blocked("no open agent step to delegate")
        print(f"WAVE {opened[0].get('group') or '-'} " + " ".join(step["id"] for step in opened))
        for step in opened:
            args.step = step["id"]
            delegate_one(args, path)
        return 0
    if not args.step:
        raise SystemExit("delegate needs a step, or --open for the current wave")
    return delegate_one(args, path)


def delegate_one(args: argparse.Namespace, path: Path) -> int:
    """Hand one open step to its agent, with a write lease when it writes code."""
    # A recorded step can still hold a token when the release that followed
    # the record failed. Free those before taking another lease on this feature.
    prior = load_yaml(path) or {}
    stale = [
        pair for step in (prior.get("steps") or [])
        if "status" in step
        for pair in live_tokens({"steps": [step]})
    ]
    if stale:
        failed = release_kept(path, stale)
        if failed:
            raise Blocked(
                "a recorded step still holds "
                + ", ".join(failed)
                + "; its token is in run.yaml, release it before delegating again"
            )
    sidecar = path.with_name(f"lease-{args.step}.token")
    if sidecar.is_file():
        lines = sidecar.read_text(encoding="utf-8").splitlines()
        if len(lines) >= 2:
            try:
                idev("lease", "release", lines[0], "--token", lines[1])
                print(f"LEASE {lines[0]} released")
            except Blocked as exc:
                raise Blocked(
                    f"lease {lines[0]} was acquired but never saved ({sidecar}); "
                    f"release failed ({exc}). The token is still in that file."
                ) from exc
        sidecar.unlink(missing_ok=True)
    marked: dict = {}

    def mark(run: dict) -> dict:
        if not run or "steps" not in run:
            raise Blocked(f"{path} is empty or unreadable; not overwriting it")
        if run["status"] not in ("running", "blocked"):
            raise Blocked(f"run is {run['status']}; start a new one")
        step = next((s for s in run["steps"] if s["id"] == args.step), None)
        if step is None:
            raise Blocked(f"no step {args.step} in this run")
        if not _step_open(run, step):
            raise Blocked(f"{args.step} is not the current step")
        agent = kind_agents.KIND_AGENTS.get(step["kind"], "-")
        if agent == "-":
            raise Blocked(f"{step['kind']} stays with the conductor; nothing to delegate")
        held = step.get("lease") or {}
        if held.get("token"):
            raise Blocked(f"{args.step} already holds lease {held['id']}; record the step to release it")
        step["delegated"] = {"agent": agent, "at": now()}
        stamp_open_group(run, ticket_of(path))
        marked.update(
            agent=agent, lease=lease_purpose(run, step), tier=risk_tier_of(run, path),
            feature_id=feature_id(run, path),
        )
        return run

    safeyaml.save_locked(path, mark)
    print(f"DELEGATE {args.step} -> {marked['agent']}")
    if not marked["lease"]:
        print("LEASE none (this kind does not write product code)")
        return 0
    purpose = marked["lease"]
    ticket = None
    if purpose == "verify":
        ticket = ticket_dir_repo_relative(path, session_repo(args.repo))
        paths = [f"{ticket}/**"]
    else:
        paths = arch_includes(path)
        if not paths:
            raise Blocked(
                "a write lease needs the paths a person included in arch.yaml "
                "(impact_candidates[].include: true); none found"
            )
    acquire = [
        "lease", "acquire", "--run", str(path), "--step", args.step, "--risk", marked["tier"],
        "--feature-id", marked["feature_id"],
    ]
    if purpose == "verify":
        acquire += ["--purpose", "verify", "--ticket-dir", ticket]
    else:
        acquire += [a for p in paths for a in ("--write-path", p)]
    out = idev(*acquire)

    def hold(run: dict) -> dict:
        step = next(s for s in run["steps"] if s["id"] == args.step)
        step["lease"] = {"id": out["lease_id"], "token": out["token"], "fencing": out["fencing"], "paths": paths}
        return run

    try:
        safeyaml.save_locked(path, hold)
    except BaseException as exc:
        # The token exists only in this process until hold writes it. Release
        # while we still have it; if that also fails, keep it beside the run.
        try:
            idev("lease", "release", out["lease_id"], "--token", out["token"])
        except Blocked as rel:
            sidecar.write_text(out["lease_id"] + "\n" + out["token"] + "\n", encoding="utf-8")
            os.chmod(sidecar, 0o600)
            raise Blocked(
                f"lease {out['lease_id']} was acquired but not saved, and releasing it failed ({rel}); "
                f"the token is in {sidecar}"
            ) from exc
        raise Blocked(
            f"lease {out['lease_id']} was acquired but not saved ({exc}); it was released, delegate again"
        ) from exc
    print(f"LEASE {out['lease_id']} fencing={out['fencing']} for {out['agent']} until {out['expires_at']}")
    print("LEASE paths " + ", ".join(paths))
    return 0


def gate_view(state: dict) -> dict:
    """The fields ask stores, from either a request or a status response."""
    return {
        "gate_id": state["gate_id"],
        "type": state.get("type") or "",
        "risk": state.get("risk") or "",
        "required_assurance": state.get("required_assurance") or "",
        "subject": state.get("subject") or [],
    }


def print_asked(step_id: str, asked: dict, recovered: bool) -> None:
    print(f"GATE {asked['gate_id']} asked ({asked['type']}, {asked['risk']}, needs {asked['required_assurance']})")
    if recovered:
        print("GATE already open; recorded the existing id")
    print(
        f"GATE the person's reply of 确认 is enough: "
        f"workflow.py record {step_id} PASS --by <name> --quote \"<their words>\""
    )
    print(f"GATE optional terminal: idev gate approve {asked['gate_id']}")


def remember_gate(path: Path, step_id: str, asked: dict) -> None:
    """Write the gate id under the run lock. The question itself is already open."""

    def hold(run: dict) -> dict:
        if not run or "steps" not in run:
            raise Blocked(f"{path} is empty or unreadable; not overwriting it")
        step = next((s for s in run["steps"] if s["id"] == step_id), None)
        if step is None or step.get("kind") != "human.gate" or not _step_open(run, step):
            raise Blocked(
                f"gate {asked['gate_id']} was asked but {step_id} is no longer the current step; "
                f"idev gate reject {asked['gate_id']}"
            )
        existing = str((step.get("gate") or {}).get("id") or "")
        if existing and existing != asked["gate_id"]:
            raise Blocked(f"gate {existing} is still waiting: idev gate approve {existing}")
        step["gate"] = {
            "id": asked["gate_id"],
            "type": asked.get("type") or "",
            "subject": asked.get("subject") or [],
        }
        return run

    safeyaml.save_locked(path, hold)


def cmd_ask(args: argparse.Namespace) -> int:
    """Open the person's question for the current human.gate."""
    if not go_engine():
        raise Blocked("IDEV_ENGINE=python has no gate channel; record PASS with --by / --quote")
    path = find_run(args)
    sidecar = path.with_name(f"gate-{args.step}.id")
    prepared: dict = {}

    def prepare(run: dict) -> None:
        if not run or "steps" not in run:
            raise Blocked(f"{path} is empty or unreadable; not overwriting it")
        if run["status"] not in ("running", "blocked"):
            raise Blocked(f"run is {run['status']}; start a new one")
        step = next((s for s in run["steps"] if s["id"] == args.step), None)
        if step is None:
            raise Blocked(f"no step {args.step} in this run")
        if step["kind"] != "human.gate":
            raise Blocked(f"{args.step} is {step['kind']}, not a human.gate; only a gate asks a person")
        if not _step_open(run, step):
            raise Blocked(f"{args.step} is not the current step")
        prepared["prior"] = str((step.get("gate") or {}).get("id") or "")
        prepared["question"] = gate_question(run, path, step)

    # Validate under the lock, then talk to idev after releasing it.
    safeyaml.load_locked(path, prepare)
    prior = str(prepared.get("prior") or "")
    if prior:
        state = idev("gate", "status", prior)
        got = state.get("status")
        if got == "pending":
            raise Blocked(f"gate {prior} is still waiting: idev gate approve {prior}")
        if got == "approved" and state.get("digest_match"):
            raise Blocked(f"gate {prior} is already approved; workflow.py record {args.step} PASS")

    asked = None
    recovered = False
    side_id = ""
    if sidecar.is_file():
        lines = [ln.strip() for ln in sidecar.read_text(encoding="utf-8").splitlines() if ln.strip()]
        side_id = lines[0] if lines else ""
    if side_id:
        try:
            state = idev("gate", "status", side_id)
        except Blocked:
            state = {}
        if state.get("status") == "pending":
            asked = gate_view(state)
            recovered = True
        else:
            sidecar.unlink(missing_ok=True)
    if asked is None:
        try:
            asked = idev(*prepared["question"])
        except Blocked as exc:
            gid = pending_gate_id(str(exc))
            if not gid:
                raise
            state = idev("gate", "status", gid)
            if state.get("status") != "pending":
                raise
            asked = gate_view(state)
            recovered = True
    try:
        remember_gate(path, args.step, asked)
    except Blocked:
        raise
    except BaseException as exc:
        sidecar.write_text(asked["gate_id"] + "\n", encoding="utf-8")
        os.chmod(sidecar, 0o600)
        raise Blocked(
            f"gate {asked['gate_id']} was asked but not saved ({exc}); "
            f"the id is in {sidecar}. ask again to record it"
        ) from exc
    sidecar.unlink(missing_ok=True)
    print_asked(args.step, asked, recovered)
    return 0


def claim_run(path: Path, new_run: dict) -> None:
    """Install new_run as the live run, under the ledger lock.

    Two starts that both looked and both wrote used to leave one run and
    report success twice. The check and the write are the same critical
    section: a running or blocked run is refused, a finished one is moved
    aside, and only then is the new run published.
    """

    def mutate(_existing: dict) -> dict:
        # The reader handed in here turns a broken file into {}.
        # A live run that did not parse is not the same as no run: replacing
        # it would publish a second start over one that is still in progress.
        if path.is_file():
            try:
                loaded = load_yaml(path)
            except Exception as exc:
                raise Blocked(f"{path} is unreadable ({exc}); not replacing it") from exc
            if loaded is None:
                loaded = {}
            elif not isinstance(loaded, dict):
                raise Blocked(f"{path} is not a mapping; not replacing it")
            if loaded.get("status") in ("running", "blocked"):
                raise Blocked(f"run already live at {path}; continue it or abort it")
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            dest = path.with_name(f"run-{stamp}.yaml")
            n = 0
            while dest.exists():
                n += 1
                dest = path.with_name(f"run-{stamp}-{n}.yaml")
            path.rename(dest)
        return new_run

    safeyaml.save_locked(path, mutate)


def append_decision(run_path: Path, step: str, fields: dict) -> dict:
    """Record one answer. The same signal on the same attempt is refused.

    The membership check and the append share the ledger lock, so two
    decides cannot both observe 'not answered yet' and both write.
    """
    entry: dict = {}

    def mutate(data: dict) -> dict:
        data = data or {}
        data.setdefault("schema_version", 1)
        items = data.setdefault("decisions", [])
        if not isinstance(items, list) or any(not isinstance(d, dict) for d in items):
            raise Blocked("decisions.yaml decisions must be a list of mappings; fix it before deciding")
        record = latest_delegation(run_path, step)
        signal = fields["signal"]
        if record is not None and signal not in [str(s) for s in (record.get("signals") or [])]:
            raise Blocked(
                f"--signal must be one of the signals of {step}: "
                + ("; ".join(str(s) for s in (record.get("signals") or [])) or "none recorded")
            )
        attempt = safeyaml.as_int((record or {}).get("attempt"), 1)
        prior = next(
            (
                d for d in items
                if str(d.get("step")) == step
                and safeyaml.as_int(d.get("attempt"), 1) == attempt
                and str(d.get("signal")) == signal
            ),
            None,
        )
        if prior:
            raise Blocked(
                f"signal already decided ({prior.get('id')}) for this attempt; "
                "a second answer would contradict the first"
            )
        run = load_yaml(run_path) or {}
        entry.update({
            "id": f"D{len(items) + 1}",
            "run_id": str(run.get("run_id") or ""),
            "step": step,
            "attempt": attempt,
            "signal": signal,
            "question": fields["question"],
            "options": fields.get("options") or "",
            "ai_recommendation": fields.get("recommend") or "",
            "answer": fields["answer"],
            "quote": fields["quote"],
            "at": now(),
        })
        items.append(entry)
        return data

    safeyaml.save_locked(decisions_path(run_path), mutate)
    return entry


def cmd_decide(args: argparse.Namespace) -> int:
    """Append a person's answer to a signal. A decision, not a signoff."""
    path = find_run(args)
    run = load_yaml(path) or {}
    steps = {s["id"]: s for s in run.get("steps") or []}
    if args.step not in steps:
        raise Blocked(f"no step {args.step} in this run")
    for name in ("signal", "question", "answer"):
        if not str(getattr(args, name) or "").strip():
            raise Blocked(f"a decision needs --{name}")
    if not is_answer(args.quote):
        raise Blocked("--quote must be the person's answer to the question; 继续 / ok choose nothing, ask again")
    entry = append_decision(path, args.step, {
        "signal": args.signal.strip(),
        "question": args.question.strip(),
        "answer": args.answer.strip(),
        "quote": args.quote.strip(),
        "options": args.options.strip(),
        "recommend": args.recommend.strip(),
    })
    print(f"DECISION {entry['id']} {decisions_path(path)}")
    left = unanswered(path, args.step)
    print("SIGNALS none left" if not left else "SIGNALS still open: " + "; ".join(left))
    return 0


def cmd_abort(args: argparse.Namespace) -> int:
    path = find_run(args)
    held: list = []
    saved: dict = {}

    def mutate(run: dict) -> dict:
        if not run or "steps" not in run:
            raise Blocked(f"{path} is empty or unreadable; not overwriting it")
        run["status"] = "aborted"
        run.setdefault("revisions", []).append({"at": now(), "note": f"aborted: {args.note}"})
        held.extend(live_tokens(run))
        saved["run"] = run
        return run

    safeyaml.save_locked(path, mutate)
    write_report(path, saved["run"])
    print(f"RUN ABORTED {path}")
    release_kept(path, held)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default="", help="session checkout (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def locate(p: argparse.ArgumentParser) -> None:
        p.add_argument("--feature", default="")
        p.add_argument("--run", default="")

    p = sub.add_parser("resolve")
    p.add_argument("workflow")
    p.set_defaults(func=cmd_resolve)
    p = sub.add_parser("start")
    p.add_argument("workflow")
    p.add_argument("--feature", default="")
    p.add_argument("--param", action="append")
    p.set_defaults(func=cmd_start)
    for name, func in (("next", cmd_next), ("status", cmd_status)):
        p = sub.add_parser(name)
        locate(p)
        p.set_defaults(func=func)
    p = sub.add_parser("ask")
    p.add_argument("step")
    locate(p)
    p.set_defaults(func=cmd_ask)
    p = sub.add_parser("delegate")
    p.add_argument("step", nargs="?")
    p.add_argument("--open", action="store_true", help="delegate every open agent step in the current wave")
    locate(p)
    p.set_defaults(func=cmd_delegate)
    p = sub.add_parser("record")
    p.add_argument("step")
    p.add_argument("status")
    p.add_argument("--evidence", default="")
    p.add_argument("--by", default="")
    p.add_argument("--quote", default="")
    p.add_argument("--note", default="")
    p.add_argument("--verified-by", default="")
    p.add_argument("--verify-evidence", default="")
    locate(p)
    p.set_defaults(func=cmd_record)
    p = sub.add_parser("decide")
    p.add_argument("step")
    p.add_argument("--signal", default="")
    p.add_argument("--question", default="")
    p.add_argument("--answer", default="")
    p.add_argument("--quote", default="")
    p.add_argument("--options", default="")
    p.add_argument("--recommend", default="")
    locate(p)
    p.set_defaults(func=cmd_decide)
    p = sub.add_parser("abort")
    p.add_argument("--note", required=True)
    locate(p)
    p.set_defaults(func=cmd_abort)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Blocked as exc:
        print(f"BLOCKED {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
