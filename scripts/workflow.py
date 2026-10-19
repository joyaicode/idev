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
  workflow.py ask     <step>
  workflow.py record  <step> <STATUS> [--evidence P] [--by NAME --quote TEXT] [--note TEXT]
                      [--verified-by AGENT --verify-evidence P]
  workflow.py decide  <step> --signal S --question Q --answer A --quote TEXT [--options O] [--recommend R]
  workflow.py status  [--feature F | --run PATH]
  workflow.py abort   --note TEXT [--feature F | --run PATH]

A human.gate is asked with `ask` and answered by the person in their own
terminal (`idev gate approve <id>`); `record <gate> PASS` then reads the
signed answer back. IDEV_ENGINE=python is the fallback: the old path where
PASS carries --by / --quote typed into the chat.

Exit codes: 0 ok, 1 usage or invalid recipe, 2 BLOCKED (missing inputs or a
rule refused the write).
"""
from __future__ import annotations

import argparse
import datetime as dt
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
        raise Blocked(f"waiting for the person: they answer in their own terminal with `idev gate approve {gid}`")
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


def release_held(run: dict) -> list[tuple[str, str]]:
    """Take every live lease token out of the run, for releasing after the write."""
    out = []
    for step in run.get("steps") or []:
        held = step.get("lease") or {}
        if held.get("token"):
            out.append((held["id"], held.pop("token")))
            held["released_at"] = now()
    return out


def release_all(pairs: list[tuple[str, str]]) -> None:
    for lease_id, token in pairs:
        try:
            idev("lease", "release", lease_id, "--token", token)
            print(f"LEASE {lease_id} released")
        except Blocked as exc:
            # The record stands; an unreleased lease runs out on its own and
            # the next acquire sweeps it.
            print(f"WARN lease {lease_id} not released ({exc}); it expires on its own")


def needs_write_lease(run: dict, step: dict) -> bool:
    """A write-lease kind on a ticket run, under the Go engine."""
    return (
        go_engine()
        and kind_agents.KIND_LEASE.get(step["kind"]) == "write"
        and str(run.get("feature") or "-") != "-"
    )


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
    import delegation  # noqa: PLC0415 - scripts/, imported only when a lease is checked

    record = latest_delegation(run_path, step_id) or {}
    raw = str((record.get("report") or {}).get("raw", ""))
    hit = delegation.CHANGED_LINE.search(raw)
    if not hit or delegation.NONE_VALUE.match(hit.group(1)):
        return []
    return sorted(delegation._paths(hit.group(1)))


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


def next_line(run: dict) -> list[str]:
    if run["status"] in ("done", "aborted"):
        return [f"RUN {run['status'].upper()}"]
    step = current_step(run)
    if step is None:
        return ["RUN DONE"]
    kind = step["kind"]
    lines = [
        f"NEXT {step['id']}  kind={kind}  status={step.get('status', 'pending')}",
        f"OPEN {KINDS.get(kind, '-')}",
        kind_agents.delegate_line(kind),
    ]
    if step.get("label"):
        lines.append(f"LABEL {step['label']}")
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
        if go_engine():
            lines.append(
                f"GATE workflow.py ask {step['id']}; the person answers in their own terminal "
                f"(idev gate approve <id>); then record PASS"
            )
        else:
            lines.append("GATE then record PASS with --by <person> --quote \"<their confirm words>\"")
    if needs_write_lease(run, step):
        lines.append(f"LEASE workflow.py delegate {step['id']} before the agent starts; it writes only arch.yaml includes")
    verifier = kind_agents.KIND_VERIFIER.get(kind)
    if verifier:
        lines.append(f"VERIFY {verifier} confirms before PASS: --verified-by {verifier} --verify-evidence <report>")
    if run["status"] == "blocked":
        lines.insert(0, "RUN BLOCKED; fix this step, then record it again")
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
    if run_path.is_file():
        old = load_yaml(run_path) or {}
        if old.get("status") in ("running", "blocked"):
            raise Blocked(f"run already live at {run_path}; continue it or abort it")
        run_path.rename(run_path.with_name(f"run-{dt.datetime.now():%Y%m%d-%H%M%S}.yaml"))
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
            {k: step[k] for k in ("id", "kind", "label", "with") if k in step}
            for step in recipe["steps"]
        ],
        "revisions": [],
        "feedback": {"status": "pending"},
    }
    dump_yaml(run_path, run)
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


def cmd_record(args: argparse.Namespace) -> int:
    path = find_run(args)
    status = args.status.upper()
    if status not in STEP_STATUS:
        raise SystemExit(f"status must be one of {sorted(STEP_STATUS)}")

    # Read, decide and write under one lock. Before this, two `record` calls
    # that overlapped each read the run, each applied its own step, and the
    # second write erased the first — both of them printing the next step as
    # if nothing had happened. check_run runs inside the lock too, so what is
    # validated is what gets written.
    done: dict = {}

    def mutate(run: dict) -> dict:
        if not run or "steps" not in run:
            raise Blocked(f"{path} is empty or unreadable; not overwriting it")
        if run["status"] not in ("running", "blocked"):
            raise Blocked(f"run is {run['status']}; start a new one")
        steps = {s["id"]: s for s in run["steps"]}
        step = steps.get(args.step)
        if step is None:
            raise Blocked(f"no step {args.step} in this run")
        cur = current_step(run)
        if cur is not None and step is not cur:
            if "status" not in step:
                raise Blocked(f"finish {cur['id']} first; record it SKIPPED to skip")
            if not args.note:
                raise Blocked(f"{step['id']} is already {step['status']}; changing it needs --note")
        if step["kind"] == "human.gate":
            if status == "PASS" and go_engine():
                if args.by or args.quote:
                    raise Blocked(
                        "the signature comes from the person's own terminal (idev gate approve), "
                        "not from --by / --quote; drop them"
                    )
                step["signoff"] = signed_answer(step)
            elif status == "PASS":
                if not people_whitelist():
                    # Blacklist-only stops agents, not a plausible invented
                    # name; a gate PASS is not signed on that basis (R2).
                    raise Blocked(
                        "human.gate PASS needs a people.yaml whitelist; "
                        "blacklist-only is not enough"
                    )
                if not is_human(args.by or ""):
                    raise Blocked("human.gate PASS needs --by with a person's name, not an agent")
                parsed = parse_confirm(args.quote or "")
                if not parsed.ok:
                    raise Blocked(
                        f"human.gate PASS needs --quote with the person's confirm words "
                        f"(确认 / 全签 / 同意 / LGTM); {WHY[parsed.reason]}"
                    )
                step["signoff"] = {"by": args.by.strip(), "quote": args.quote.strip(), "at": now()}
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
            step["verification"] = {"by": args.verified_by, "evidence": args.verify_evidence, "at": now()}
        held = step.get("lease") or {}
        if status == "PASS" and needs_write_lease(run, step):
            if not held.get("id"):
                raise Blocked(
                    f"{step['id']} writes product code and was never given a write lease: "
                    f"workflow.py delegate {step['id']} before the agent starts"
                )
            changed = changed_paths(path, step["id"])
            if changed:
                outside = idev("lease", "check", held["id"], *[a for p in changed for a in ("--path", p)]).get("outside") or []
                if outside:
                    raise Blocked(
                        f"{step['id']} changed files outside its lease (arch.yaml include): "
                        + ", ".join(outside)
                        + " — revert them, or include them in arch.yaml and delegate again"
                    )
        if held.get("token"):
            done["release"] = [(held["id"], held.pop("token"))]
            held["released_at"] = now()
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
        errors: list[str] = []
        check_run(run, path, errors)
        if errors:
            raise Blocked("; ".join(errors))
        write_report(path, run)
        done["run"] = run
        done["step"] = step
        return run

    safeyaml.save_locked(path, mutate)
    run, step = done["run"], done["step"]
    release_all(done.get("release") or [])
    if status in STEP_STOP:
        ask = (run.get("policy") or {}).get("on_fail") == "ask"
        print(f"BLOCKED {step['id']} {status}; " + ("ask the person how to go on" if ask else "stop; fix and record again"))
    print("\n".join(next_line(run)))
    return 0


def cmd_delegate(args: argparse.Namespace) -> int:
    """Hand the current step to its agent, with a write lease when it writes code."""
    path = find_run(args)
    marked: dict = {}

    def mark(run: dict) -> dict:
        if not run or "steps" not in run:
            raise Blocked(f"{path} is empty or unreadable; not overwriting it")
        if run["status"] not in ("running", "blocked"):
            raise Blocked(f"run is {run['status']}; start a new one")
        step = next((s for s in run["steps"] if s["id"] == args.step), None)
        if step is None:
            raise Blocked(f"no step {args.step} in this run")
        if step is not current_step(run):
            raise Blocked(f"{args.step} is not the current step")
        agent = kind_agents.KIND_AGENTS.get(step["kind"], "-")
        if agent == "-":
            raise Blocked(f"{step['kind']} stays with the conductor; nothing to delegate")
        held = step.get("lease") or {}
        if held.get("token"):
            raise Blocked(f"{args.step} already holds lease {held['id']}; record the step to release it")
        step["delegated"] = {"agent": agent, "at": now()}
        marked.update(
            agent=agent, lease=needs_write_lease(run, step), tier=risk_tier_of(run, path),
            feature_id=feature_id(run, path),
        )
        return run

    safeyaml.save_locked(path, mark)
    print(f"DELEGATE {args.step} -> {marked['agent']}")
    if not marked["lease"]:
        print("LEASE none (this kind does not write product code)")
        return 0
    paths = arch_includes(path)
    if not paths:
        raise Blocked(
            "a write lease needs the paths a person included in arch.yaml "
            "(impact_candidates[].include: true); none found"
        )
    out = idev(
        "lease", "acquire", "--run", str(path), "--step", args.step, "--risk", marked["tier"],
        "--feature-id", marked["feature_id"],
        *[a for p in paths for a in ("--write-path", p)],
    )

    def hold(run: dict) -> dict:
        step = next(s for s in run["steps"] if s["id"] == args.step)
        step["lease"] = {"id": out["lease_id"], "token": out["token"], "fencing": out["fencing"], "paths": paths}
        return run

    safeyaml.save_locked(path, hold)
    print(f"LEASE {out['lease_id']} fencing={out['fencing']} for {out['agent']} until {out['expires_at']}")
    print("LEASE paths " + ", ".join(paths))
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    """Open the person's question for the current human.gate."""
    if not go_engine():
        raise Blocked("IDEV_ENGINE=python has no gate channel; record PASS with --by / --quote")
    path = find_run(args)
    asked: dict = {}

    def mutate(run: dict) -> dict:
        if not run or "steps" not in run:
            raise Blocked(f"{path} is empty or unreadable; not overwriting it")
        if run["status"] not in ("running", "blocked"):
            raise Blocked(f"run is {run['status']}; start a new one")
        step = next((s for s in run["steps"] if s["id"] == args.step), None)
        if step is None:
            raise Blocked(f"no step {args.step} in this run")
        if step["kind"] != "human.gate":
            raise Blocked(f"{args.step} is {step['kind']}, not a human.gate; only a gate asks a person")
        if step is not current_step(run):
            raise Blocked(f"{args.step} is not the current step")
        prior = str((step.get("gate") or {}).get("id") or "")
        if prior and idev("gate", "status", prior).get("status") == "pending":
            raise Blocked(f"gate {prior} is still waiting: idev gate approve {prior}")
        out = idev(*gate_question(run, path, step))
        step["gate"] = {"id": out["gate_id"], "type": out["type"], "subject": out.get("subject") or []}
        asked.update(out)
        return run

    safeyaml.save_locked(path, mutate)
    print(f"GATE {asked['gate_id']} asked ({asked['type']}, {asked['risk']}, needs {asked['required_assurance']})")
    print(f"GATE the person runs in their own terminal: idev gate approve {asked['gate_id']}")
    print(f"GATE then: workflow.py record {args.step} PASS")
    return 0


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
    record = latest_delegation(path, args.step)
    if record is not None and args.signal.strip() not in [str(s) for s in record.get("signals") or []]:
        raise Blocked(
            f"--signal must be one of the signals of {args.step}: "
            + ("; ".join(str(s) for s in record.get("signals") or []) or "none recorded")
        )
    attempt = safeyaml.as_int((record or {}).get("attempt"), 1)
    ledger = decisions_path(path)
    entry: dict = {}

    def mutate(data: dict) -> dict:
        data = data or {}
        data.setdefault("schema_version", 1)
        items = data.setdefault("decisions", [])
        entry.update({
            "id": f"D{len(items) + 1}",
            "run_id": run.get("run_id", ""),
            "step": args.step,
            "attempt": attempt,
            "signal": args.signal.strip(),
            "question": args.question.strip(),
            "options": args.options.strip(),
            "ai_recommendation": args.recommend.strip(),
            "answer": args.answer.strip(),
            "quote": args.quote.strip(),
            "at": now(),
        })
        items.append(entry)
        return data

    safeyaml.save_locked(ledger, mutate)
    print(f"DECISION {entry['id']} {ledger}")
    left = unanswered(path, args.step)
    print("SIGNALS none left" if not left else "SIGNALS still open: " + "; ".join(left))
    return 0


def cmd_abort(args: argparse.Namespace) -> int:
    path = find_run(args)
    held: list = []

    def mutate(run: dict) -> dict:
        if not run or "steps" not in run:
            raise Blocked(f"{path} is empty or unreadable; not overwriting it")
        run["status"] = "aborted"
        run.setdefault("revisions", []).append({"at": now(), "note": f"aborted: {args.note}"})
        held.extend(release_held(run))
        write_report(path, run)
        return run

    safeyaml.save_locked(path, mutate)
    print(f"RUN ABORTED {path}")
    release_all(held)
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
    p.add_argument("step")
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
