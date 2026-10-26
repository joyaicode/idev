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


def ensure_marker(repo: Path) -> None:
    """First save in a product checkout writes the opt-in scaffold.

    Later sessions recognize the directory by marker: idev. evolve stays
    off until the product asks to join self-evolution. An existing marker
    is left unchanged. The scaffold is an empty stage list, a checks
    directory, an empty strip-token file, and a gitignore that keeps memory.md,
    native tickets (.idev/task, .idev/docs), and the other durable files.
    An existing marker is not rewritten. A later save still fills any
    gitignore keep-lines that the first scaffold missed.
    """
    path = repo / ".idev" / "marker.yaml"
    if path.is_file():
        _append_gitignore(repo)
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
