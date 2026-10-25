#!/usr/bin/env python3
"""Changed source files for the language plugins. Same scope as java_hygiene."""
from __future__ import annotations

import subprocess
from pathlib import Path

SKIP = {
    ".git",
    "node_modules",
    "dist",
    "target",
    "vendor",
    "build",
    "generated",
    "generatedverify",
}


def _git(repo: Path, args: list[str]) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def changed(repo: Path, suffixes: tuple[str, ...], label: str) -> tuple[list[str], str]:
    repo = repo.resolve()
    if not _git(repo, ["rev-parse", "--is-inside-work-tree"]):
        return [], "no git (0 %s)" % label
    names: set[str] = set()
    scope = "working tree"
    for base in ("origin/master", "master", "origin/main", "main"):
        if not _git(repo, ["rev-parse", "--verify", "--quiet", base]):
            continue
        head = _git(repo, ["merge-base", "HEAD", base])
        if head:
            names.update(
                _git(
                    repo,
                    ["diff", "--name-only", "--diff-filter=ACMR", "%s...HEAD" % head[0]],
                )
            )
            scope = "diff %s...HEAD" % head[0][:12]
        break
    names.update(_git(repo, ["diff", "--name-only", "--diff-filter=ACMR", "HEAD"]))
    names.update(_git(repo, ["diff", "--name-only", "--cached", "--diff-filter=ACMR"]))
    names.update(_git(repo, ["ls-files", "--others", "--exclude-standard"]))
    rels = []
    for rel in sorted(names):
        if set(Path(rel).parts) & SKIP:
            continue
        if Path(rel).suffix.lower() not in suffixes:
            continue
        if not (repo / rel).is_file():
            continue
        rels.append(rel)
    return rels, "%s (%d %s)" % (scope, len(rels), label)
