#!/usr/bin/env python3
"""preToolUse / PreToolUse / beforeShellExecution: refuse the four oversteps.

1. Writing reopen_baseline into ticket YAML by hand (name it through the gate).
2. `git push` that is not clearly preceded by a green gate (best-effort).
3. Writing outside a held lease when IDEV_LEASE_ID is set (calls idev lease check).
4. Setting IDEV_ENGINE=python or IDEV_BIN=off in a shell command.

Not a security boundary: a person can still run the same commands outside the
agent. The record-side checks stay.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

SIGNOFF_IN_CONTENT = re.compile(lib.SIGNOFF_FIELD_RE)
# Signoff fields are read only from ticket and run YAML. Source, tests and docs
# quote them, and the client sends the whole file with an edit.
SIGNOFF_FILE = re.compile(
    r"(?:^|/)(?:docs|\.idev)/task/[^/]+/.+\.ya?ml$"
    r"|(?:^|/)(?:state|\.idev)/workflow-runs/.+\.ya?ml$",
    re.IGNORECASE,
)
ENGINE_PYTHON = re.compile(
    r"(?:^|[\s;|&])(?:export\s+)?IDEV_ENGINE\s*=\s*python\b"
    r"|(?:^|[\s;|&])env\s+[^\n]*\bIDEV_ENGINE=python\b",
    re.IGNORECASE,
)
BIN_OFF = re.compile(
    r"(?:^|[\s;|&])(?:export\s+)?IDEV_BIN\s*=\s*['\"]?(?:off|none|0)['\"]?(?:\s|$|;|&|\|)"
    r"|(?:^|[\s;|&])env\s+[^\n]*\bIDEV_BIN=['\"]?(?:off|none|0)['\"]?(?:\s|$)",
    re.IGNORECASE,
)
GIT_PUSH = re.compile(r"(?:^|[;&|\s])git\s+push\b", re.IGNORECASE)


def tool_name(payload: dict) -> str:
    for key in ("tool_name", "toolName", "tool", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def tool_input(payload: dict) -> dict:
    for key in ("tool_input", "input", "arguments", "args"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def shell_command(payload: dict, tin: dict) -> str:
    for key in ("command", "cmd", "shell_command"):
        for src in (tin, payload):
            value = src.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return ""


def write_path(tin: dict) -> str:
    for key in ("path", "file_path", "filePath", "target_file", "file"):
        value = tin.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def write_content(tin: dict) -> str:
    for key in ("contents", "content", "new_string", "text", "body"):
        value = tin.get(key)
        if isinstance(value, str):
            return value
    return ""


def refuse_signoff_edit(path: str, content: str) -> str:
    """Block only a reopen written by hand.

    Delivery fields (sealed, accepted, aligned, resolved) are written when
    the stage check passes. They are not a confirmation. Reopen still has
    to name the action, and that write goes through the gate.
    """
    if path and not SIGNOFF_FILE.search(path.replace("\\", "/")):
        return ""
    if not content or not re.search(r"(?m)^\s*reopen_baseline\s*:\s*true\b", content):
        return ""
    where = path or "a file"
    return (
        f"refusing to write reopen_baseline via the agent into {where}; "
        "name the reopen and record it through the gate"
    )


def refuse_engine_python(command: str) -> str:
    if command and ENGINE_PYTHON.search(command):
        return "refusing IDEV_ENGINE=python in the agent shell; use the Go engine"
    if command and BIN_OFF.search(command):
        return "refusing IDEV_BIN=off in the agent shell; it skips the store checks"
    return ""


def refuse_git_push(command: str) -> str:
    if command and GIT_PUSH.search(command):
        # A person can still push from their own terminal. Inside the agent we
        # stop the silent push; an explicit gate-approved path is stage 1.6+.
        return "refusing git push from the agent; a person pushes after the gate"
    return ""


def refuse_lease(path: str) -> str:
    lease_id = (os.environ.get("IDEV_LEASE_ID") or "").strip()
    if not lease_id or not path:
        return ""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
    import idev_bin

    idev = idev_bin.path(rebuild=False)
    if not idev:
        return ""
    proc = subprocess.run(
        [idev, "lease", "check", lease_id, "--path", path],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return f"lease {lease_id} refused path {path}: {(proc.stderr or proc.stdout).strip()}"
    try:
        import json
        data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except Exception:
        return ""
    outside = data.get("outside") or []
    if outside:
        return f"path {path} is outside lease {lease_id}: {', '.join(map(str, outside))}"
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", default="cursor", choices=("cursor", "claude"))
    args = parser.parse_args(argv)
    payload = lib.read_stdin()
    tin = tool_input(payload)
    name = tool_name(payload)
    command = shell_command(payload, tin)
    path = write_path(tin)
    content = write_content(tin)

    # beforeShellExecution may only send the command.
    if not name and command:
        name = "Shell"

    reasons = []
    if name in ("Shell", "Bash", "shell") or command:
        reasons.append(refuse_engine_python(command))
        reasons.append(refuse_git_push(command))
    if name in ("Write", "Edit", "StrReplace", "search_replace", "WriteFile") or path:
        reasons.append(refuse_signoff_edit(path, content))
        reasons.append(refuse_lease(path))

    for reason in reasons:
        if reason:
            return lib.deny(reason)
    return lib.allow({"client": args.client})


if __name__ == "__main__":
    raise SystemExit(main())
