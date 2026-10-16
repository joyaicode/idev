#!/usr/bin/env python3
"""Drive an S8 run from its recipe yaml.

The recipe is the artifact; run.yaml is its instance. This tool binds
params, writes run.yaml, names the next step and the page that executes it,
and records step results. It never executes a step: the agent does that in
the module the step lands on.

  workflow.py resolve <id>
  workflow.py start <id> [--feature F] [--param k=v ...]
  workflow.py next    [--feature F | --run PATH]
  workflow.py record  <step> <STATUS> [--evidence P] [--by NAME --quote TEXT] [--note TEXT]
  workflow.py status  [--feature F | --run PATH]
  workflow.py abort   --note TEXT [--feature F | --run PATH]

Exit codes: 0 ok, 1 usage or invalid recipe, 2 BLOCKED (missing inputs or a
rule refused the write).
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
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
    check_recipe,
    check_run,
    is_human,
    parse_confirm,
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
        lines.append(f"GATE stop here; post this line and the proof: {will_write_line(step)}")
        lines.append("GATE then record PASS with --by <person> --quote \"<their confirm words>\"")
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
            if status == "PASS":
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
                raise Blocked("a gate is skipped only with --evidence of the earlier signoff")
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
    if status in STEP_STOP:
        ask = (run.get("policy") or {}).get("on_fail") == "ask"
        print(f"BLOCKED {step['id']} {status}; " + ("ask the person how to go on" if ask else "stop; fix and record again"))
    print("\n".join(next_line(run)))
    return 0


def cmd_abort(args: argparse.Namespace) -> int:
    path = find_run(args)

    def mutate(run: dict) -> dict:
        if not run or "steps" not in run:
            raise Blocked(f"{path} is empty or unreadable; not overwriting it")
        run["status"] = "aborted"
        run.setdefault("revisions", []).append({"at": now(), "note": f"aborted: {args.note}"})
        write_report(path, run)
        return run

    safeyaml.save_locked(path, mutate)
    print(f"RUN ABORTED {path}")
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
    p = sub.add_parser("record")
    p.add_argument("step")
    p.add_argument("status")
    p.add_argument("--evidence", default="")
    p.add_argument("--by", default="")
    p.add_argument("--quote", default="")
    p.add_argument("--note", default="")
    locate(p)
    p.set_defaults(func=cmd_record)
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
