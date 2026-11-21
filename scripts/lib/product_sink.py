#!/usr/bin/env python3
"""Resolve where a session's intermediate files go.

When a product uses idev, the kernel's intermediates for that product
(traces, proposals, reviews, inbox, console, ticketless workflow runs, react loops)
go to <repo>/.idev/. Product characteristics stay in the same directory.
The kernel state/ directory is only for a conductor session that has no
current product. The console directory holds the control-page thread and
the live agent list. It is not the verify inbox.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

KINDS = {
    "traces": ("state/traces", ".idev/traces"),
    "proposals": ("state/proposals", ".idev/proposals"),
    "reviews": ("state/reviews", ".idev/reviews"),
    "inbox": ("verify/state/inbox", ".idev/inbox"),
    "console": ("state/console", ".idev/console"),
    "workflow-runs": ("state/workflow-runs", ".idev/workflow-runs"),
    "react": ("state/react", ".idev/react"),
}


# kernel_root and the "is this path inside the kernel" helper both live in
# roots.py now. This file's copy ignored IDEV_ROOT while kind_agents honoured
# it, so an override moved the agent table but not the sink.
from roots import inside as _inside  # noqa: E402
from roots import kernel_root  # noqa: E402


def product_repo(start: Path | None = None) -> Path | None:
    """Product checkout, or None when the session is the conductor itself."""
    kernel = kernel_root()
    explicit = os.environ.get("IDEV_PRODUCT_REPO", "").strip()
    if explicit:
        repo = Path(explicit).expanduser().resolve()
        if _inside(repo, kernel):
            return None
        return repo
    cur = (start or Path.cwd()).resolve()
    if _inside(cur, kernel):
        return None
    for candidate in [cur, *cur.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


_GITIGNORE_BLOCK = """
# idev: execution residue stays untracked; durable product characteristics stay
.idev/*
!.idev/memory.md
!.idev/marker.yaml
!.idev/extensions.yaml
!.idev/handoff.yaml
!.idev/workflow-defaults.yaml
!.idev/strip-tokens.txt
!.idev/pack/
!.idev/workflows/
!.idev/checks/
!.idev/task/
!.idev/task/**
!.idev/docs/
!.idev/docs/**
"""


_GITIGNORE_KEEP = (
    "!.idev/memory.md",
    "!.idev/marker.yaml",
    "!.idev/extensions.yaml",
    "!.idev/handoff.yaml",
    "!.idev/workflow-defaults.yaml",
    "!.idev/strip-tokens.txt",
    "!.idev/pack/",
    "!.idev/workflows/",
    "!.idev/checks/",
    "!.idev/task/",
    "!.idev/task/**",
    "!.idev/docs/",
    "!.idev/docs/**",
)


def _append_gitignore(repo: Path) -> None:
    path = repo / ".gitignore"
    existing = ""
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            return
    if "!.idev/memory.md" not in existing:
        prefix = ""
        if existing and not existing.endswith("\n"):
            prefix = "\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(prefix + _GITIGNORE_BLOCK.lstrip("\n"))
            if not _GITIGNORE_BLOCK.endswith("\n"):
                handle.write("\n")
        return
    missing = [line for line in _GITIGNORE_KEEP if line not in existing]
    if not missing:
        return
    with path.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write("\n".join(missing) + "\n")


# Durable paths that stay tracked on purpose. _GITIGNORE_KEEP mixes exact
# files (.idev/memory.md) with directory governs (.idev/pack/, .idev/task/**):
# ls-files lists files, so every rule is normalized to a directory prefix
# match — an exact rule keeps exactly that path, a dir rule keeps anything
# under it.
def _durable_prefix(rule: str) -> str | None:
    """Normalized prefix for one keep rule, or None when it cannot decide."""
    body = rule.lstrip("!")
    if not body.startswith(".idev/"):
        return None
    path = "/" + body.rstrip("*").rstrip("/")
    return path if len(path) > len("/.idev") else None


_DURABLE_RULES = tuple(
    prefix
    for prefix in (_durable_prefix(rule) for rule in _GITIGNORE_KEEP)
    if prefix
)


def _report_tracked_process_files(repo: Path) -> None:
    tracked = _tracked_process_files(repo)
    for path in tracked:
        print(
            "WARN idev process file already git-tracked (untrack is yours to "
            f"decide, not automatic): {path}",
            file=sys.stderr,
        )


def _tracked_process_files(repo: Path) -> list[str]:
    """Process paths git already tracks. The ignore block below only stops
    *new* files; ones tracked before it landed stay in the index and keep
    receiving diffs. Report them — cancelling the tracking is the person's
    call, never ours (learned from joy-dev's prepare-workspace)."""
    tracked = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--", ".idev/"],
        capture_output=True, text=True, check=False,
    )
    if tracked.returncode != 0:
        return []
    durable = []
    for line in tracked.stdout.splitlines():
        path = "/" + line.strip()
        if not path or path == "/":
            continue
        if any(
            path == rule or path.startswith(rule + "/")
            for rule in _DURABLE_RULES
        ):
            continue
        durable.append(path)
    return sorted(set(durable))


def ensure_marker(repo: Path) -> None:
    path = repo / ".idev" / "marker.yaml"
    if path.is_file():
        _append_gitignore(repo)
        _report_tracked_process_files(repo)
        return
    ident = re.sub(r"[^A-Za-z0-9._-]+", "-", repo.name).strip("-") or "product"
    idev = path.parent
    idev.mkdir(parents=True, exist_ok=True)
    (idev / "checks").mkdir(parents=True, exist_ok=True)
    path.write_text(
        "schema_version: 1\nmarker: idev\nid: %s\nevolve: false\n" % ident,
        encoding="utf-8",
    )
    extensions = idev / "extensions.yaml"
    if not extensions.is_file():
        extensions.write_text("schema_version: 1\nstages: {}\n", encoding="utf-8")
    keep = idev / "checks" / ".gitkeep"
    if not keep.is_file():
        keep.write_text("", encoding="utf-8")
    tokens = idev / "strip-tokens.txt"
    if not tokens.is_file():
        tokens.write_text("# one product token per line\n", encoding="utf-8")
    _append_gitignore(repo)
    _report_tracked_process_files(repo)


def sink_dir(kind: str, *, mkdir: bool = False, start: Path | None = None) -> Path:
    if kind not in KINDS:
        raise SystemExit("unknown sink kind: %s" % kind)
    kernel_rel, product_rel = KINDS[kind]
    repo = product_repo(start)
    if repo is None:
        dest = kernel_root() / kernel_rel
    else:
        dest = repo / product_rel
        if mkdir:
            ensure_marker(repo)
    if mkdir:
        dest.mkdir(parents=True, exist_ok=True)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", nargs="?", choices=sorted(KINDS))
    parser.add_argument("--mkdir", action="store_true")
    parser.add_argument("--print-repo", action="store_true", help="print the current product repo, or nothing")
    args = parser.parse_args(argv)
    if args.print_repo:
        repo = product_repo()
        print("" if repo is None else repo)
        return 0
    if not args.kind:
        parser.error("kind is required unless --print-repo")
    print(sink_dir(args.kind, mkdir=args.mkdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
