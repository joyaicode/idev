"""Run one root-cause probe inside gVisor.

`repl.py` calls this only when `--step rootcause`. The static guard in
`repl.py` is still a tripwire, not an isolation boundary. This module is
the boundary: it execs `runsc` and does not exec the snippet on the host.

`runsc do` is not used. That helper mounts the whole host filesystem, which
would expose home-directory credentials. The bundle bind-mounts the repo
read-only, standard interpreter prefixes read-only, and a scratch directory
outside the repo. It does not mount the home directory itself.

`execute` removes its temp parent before returning. Mount facts live on the
result; the deleted bundle path is not evidence.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

TIMEOUT_S = 120
RUNTIME_MARK = "runtime: runsc"
RO_PREFIXES = ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/opt/homebrew", "/opt/local")


@dataclass
class ProbeResult:
    exit_code: int
    stdout: str
    stderr: str
    launched: bool
    mounts: tuple[str, ...] = ()


def find_runsc() -> str | None:
    return shutil.which("runsc")


def container_layout(repo: Path, ticket: Path, kernel: Path) -> tuple[str, str, str]:
    """Paths the snippet sees. The kernel shares /repo when it is the repo."""
    repo_r = repo.resolve()
    kern_r = kernel.resolve()
    idev = "/repo" if kern_r == repo_r else "/idev"
    rel = ticket.resolve().relative_to(repo_r).as_posix()
    ticket_in = "/repo" if rel == "." else "/repo/" + rel
    return idev, "/repo", ticket_in


def _bind(source: str, dest: str, mode: str) -> dict:
    if mode not in ("ro", "rw"):
        raise ValueError("bind mode must be ro or rw")
    return {
        "destination": dest,
        "type": "bind",
        "source": source,
        "options": ["rbind", mode],
    }


def bundle_spec(repo: Path, kernel: Path, scratch: Path, snippet_in_container: str, exe: str) -> dict:
    mounts = [
        {"destination": "/proc", "type": "proc", "source": "proc"},
    ]
    for prefix in RO_PREFIXES:
        if Path(prefix).is_dir():
            mounts.append(_bind(prefix, prefix, "ro"))
    mounts.append(_bind(str(repo.resolve()), "/repo", "ro"))
    if kernel.resolve() != repo.resolve():
        mounts.append(_bind(str(kernel.resolve()), "/idev", "ro"))
    mounts.append(_bind(str(scratch.resolve()), "/scratch", "rw"))
    return {
        "ociVersion": "1.0.2",
        "process": {
            "terminal": False,
            "user": {"uid": os.getuid(), "gid": os.getgid()},
            "args": [exe, snippet_in_container],
            "env": ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"],
            "cwd": "/repo",
        },
        "root": {"path": "rootfs", "readonly": True},
        "hostname": "idev-rootcause",
        "mounts": mounts,
        "linux": {
            "namespaces": [
                {"type": "pid"},
                {"type": "ipc"},
                {"type": "uts"},
                {"type": "mount"},
            ]
        },
    }


def _argv(runsc: str, state: Path, bundle: Path, cid: str) -> list[str]:
    argv = [runsc, f"--root={state}", "--network=none"]
    if os.geteuid() != 0:
        argv.append("--rootless")
    argv += ["run", "--bundle", str(bundle), cid]
    return argv


def _inside(snippet: Path, repo: Path) -> str:
    rel = snippet.resolve().relative_to(repo.resolve()).as_posix()
    return "/repo/" + rel


def _prepare(parent: Path) -> tuple[Path, Path, Path]:
    """Bundle, container state, and scratch. The caller removes parent."""
    bundle = parent / "bundle"
    state = parent / "state"
    scratch = parent / "scratch"
    for path in (bundle, state, scratch, bundle / "rootfs"):
        path.mkdir()
    return bundle, state, scratch


def _run(argv: list[str]) -> tuple[str, str, int]:
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired:
        return "", "timed out after %ss" % TIMEOUT_S, 124
    return proc.stdout, proc.stderr, proc.returncode


def _delete(runsc: str, state: Path, cid: str) -> str:
    """Same timeout as run. Empty means delete finished; otherwise the failure."""
    argv = [runsc, "--root=%s" % state, "delete", "-f", cid]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired:
        return "delete timed out after %ss\n" % TIMEOUT_S
    except OSError as exc:
        return "delete failed: %s\n" % exc
    if proc.returncode == 0:
        return ""
    detail = (proc.stderr or proc.stdout or "").strip()
    text = "delete failed (%s)" % proc.returncode
    if detail:
        text = "%s: %s" % (text, detail)
    return text + "\n"


def _with_delete_note(err: str, note: str) -> str:
    if not note:
        return err
    if not err.strip():
        return note
    return err.rstrip() + "\n" + note


def _mount_line(mount: dict) -> str:
    options = mount.get("options") or []
    if "ro" in options:
        mode = "ro"
    elif "rw" in options:
        mode = "rw"
    else:
        mode = ""
    suffix = " " + mode if mode else ""
    return "mount: destination=%s source=%s%s" % (
        mount["destination"], mount.get("source", ""), suffix,
    )


def receipt_body(exit_code: int, mounts: tuple[str, ...]) -> str:
    lines = [RUNTIME_MARK, "network: none", "exit: %s" % exit_code]
    lines.extend(mounts)
    return "\n".join(lines) + "\n"


def execute(snippet: Path, repo: Path, kernel: Path) -> ProbeResult:
    """Run snippet under runsc. The temp parent is removed before return."""
    runsc = find_runsc()
    if not runsc:
        return ProbeResult(127, "", "SANDBOX_UNAVAILABLE runsc not on PATH", False)
    try:
        inside = _inside(snippet, repo)
    except ValueError:
        return ProbeResult(127, "", "SANDBOX_UNAVAILABLE snippet is outside the repo", False)
    parent = Path(tempfile.mkdtemp(prefix="idev-runsc-"))
    try:
        bundle, state, scratch = _prepare(parent)
        spec = bundle_spec(repo.resolve(), kernel, scratch, inside, sys_executable())
        (bundle / "config.json").write_text(json.dumps(spec), encoding="utf-8")
        cid = "idev%s" % os.getpid()
        out, err, rc = _run(_argv(runsc, state, bundle, cid))
        err = _with_delete_note(err, _delete(runsc, state, cid))
        return ProbeResult(rc, out, err, True, tuple(_mount_line(item) for item in spec["mounts"]))
    finally:
        shutil.rmtree(parent)


def sys_executable() -> str:
    import sys
    return sys.executable
