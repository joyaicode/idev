"""Where delegation records live. The writer and every reader ask here.

A run with a run_id keeps its records in delegations/<run_id>/, so a new
run's report-1.yaml does not collide with the last run's. A run without one
(an older run.yaml) writes the flat delegations/ directory.

A reader of one run reads exactly the directory the writer used for that
run. A reader across runs (metrics, export, the timeline) takes both layouts.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping, Optional

SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")

# Both layouts under one delegations/ directory: flat, then one level of run_id.
LEAVES = ("*.yaml", "*/*.yaml")

# The same, from a product checkout, for both doc_home layouts.
REPO_GLOBS = tuple(
    f"{home}/workflow/delegations/{leaf}"
    for home in ("docs/task/*", ".idev/task/*")
    for leaf in LEAVES
)


def is_slug(value: str) -> bool:
    return bool(SLUG.fullmatch(value)) and ".." not in value


def run_dir(base: Path, run: Optional[Mapping]) -> Path:
    """The records directory of one run, under a delegations/ directory."""
    rid = str((run or {}).get("run_id") or "").strip()
    return base / rid if rid and is_slug(rid) else base


def records(folder: Path) -> list[Path]:
    """The record files directly in one run's directory, sorted."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.yaml") if not p.name.endswith(".example.yaml"))
