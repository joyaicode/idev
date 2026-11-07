"""Run conductor-owned steps until an agent, a person, or a failure.

A single agent step is assessed before return. SERIAL prints the brief.
FANOUT prints one brief per shard. MERGE with no SHARD runs the merge.
A PARALLEL wave prints one brief per member. A kernel-script PREP runs before those briefs.
ASK slot is printed unchanged.
Nothing here spawns an agent.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import kind_agents
import workflow_compose

CAP = 8
EXECUTABLE = ("preflight.inputs", "scope.baseline", "shell.confirmed", "tool.step")


def _has_line(text: str, needle: str) -> bool:
    return any(needle in line for line in text.splitlines())


def wake(text: str) -> bool:
    if "DELEGATE idev-" in text:
        return True
    if text.startswith("PARALLEL ") or "\nPARALLEL " in text:
        return True
    return "ASK slot" in text


def parse_next(text: str) -> dict | None:
    for line in text.splitlines():
        if not line.startswith("NEXT "):
            continue
        parts = line.split()
        kind = next((p.split("=", 1)[1] for p in parts if p.startswith("kind=")), "")
        if len(parts) >= 2 and kind:
            return {"id": parts[1], "kind": kind}
    return None


def command_for(kind: str, step: dict, repo: Path, feature: str, workflow_id: str):
    kernel = kind_agents.kernel_root()
    if kind == "preflight.inputs":
        script = str(kernel / "scripts" / "s8-preflight.sh")
        return ["bash", script, feature, workflow_id or "lite-change"], repo
    if kind == "scope.baseline":
        script = str(kernel / "scripts" / "scope-baseline.py")
        return [sys.executable, script, "--repo", str(repo), "--feature", feature], repo
    payload = step.get("with") or {}
    if kind == "shell.confirmed":
        cmd = str(payload.get("cmd") or "").strip()
        return (cmd, repo) if cmd else None
    if kind == "tool.step":
        tool = str(payload.get("tool") or step.get("tool") or "")
        base = workflow_compose.tool_command(tool)
        if not base:
            return None
        argv = shlex.split(base)
        inputs, _outputs = workflow_compose.tool_contract(tool)
        if "feature" in inputs and feature and "--feature" not in argv:
            argv += ["--feature", feature]
        return argv, kernel
    return None


def run_logged(spec, cwd: Path, repo: Path) -> tuple[int, str]:
    env = dict(os.environ, IDEV_REPO=str(repo), IDEV_PRODUCT_REPO=str(repo))
    if isinstance(spec, str):
        proc = subprocess.run(
            spec, cwd=cwd, shell=True, capture_output=True, text=True, timeout=120, env=env,
        )
    else:
        proc = subprocess.run(
            list(spec), cwd=cwd, capture_output=True, text=True, timeout=120, env=env,
        )
    return proc.returncode, proc.stdout + proc.stderr


def _step_row(load, step_id: str) -> dict:
    run = load() or {}
    return next((row for row in run.get("steps") or [] if row.get("id") == step_id), {})


def _evidence(ticket: Path, repo: Path, step_id: str) -> str:
    path = ticket / "workflow" / f"drive-{step_id}.log"
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return str(path)


def _prepare(text: str, code: int, step: dict | None, hooks: dict):
    """Hand an agent step, or a whole wave, to the hook that prints briefs."""
    if code != 0 or step is None or not wake(text) or not hooks.get("handoff"):
        return None
    if "ASK slot" in text:
        return None
    return hooks["handoff"](text)


def drive(repo: Path, ticket: Path, hooks: dict) -> int:
    feature = str(hooks.get("feature") or "")
    workflow_id = str(hooks.get("workflow_id") or "")
    load = hooks["load"]
    for _ in range(CAP):
        code, text = hooks["show_next"]()
        step = parse_next(text)
        if code != 0 or step is None or wake(text):
            prepared = _prepare(text, code, step, hooks)
            if prepared is not None:
                hcode, hout = prepared
                sys.stdout.write(hout)
                return hcode
            sys.stdout.write(text)
            return code
        if step["kind"] == "human.gate":
            if _has_line(text, "DECISION"):
                sys.stdout.write(text)
                return 0
            status = "AUTO" if _has_line(text, "record AUTO") else "PASS" if _has_line(text, "GATE pass") else ""
            if not status:
                sys.stdout.write(text)
                return 0
            code, out = hooks["record"](step["id"], status, "")
            sys.stdout.write(out)
            if code != 0:
                return code
            continue
        if step["kind"] not in EXECUTABLE:
            sys.stdout.write(text)
            return 0
        spec = command_for(step["kind"], _step_row(load, step["id"]), repo, feature, workflow_id)
        if spec is None:
            sys.stdout.write(text)
            return 0
        cmd, cwd = spec
        status, log = run_logged(cmd, cwd, repo)
        dest = ticket / "workflow" / f"drive-{step['id']}.log"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(log, encoding="utf-8")
        if status != 0:
            sys.stdout.write(log)
            return 1
        code, out = hooks["record"](step["id"], "PASS", _evidence(ticket, repo, step["id"]))
        sys.stdout.write(out)
        if code != 0:
            return code
    print("BLOCKED drive stopped after 8 conductor steps", file=sys.stderr)
    return 2
