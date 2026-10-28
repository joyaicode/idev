"""Where delegation records live. The writer and every reader ask here.

A run with a run_id keeps its records in delegations/<run_id>/, so a new
run's report-1.yaml does not collide with the last run's. A run without one
(an older run.yaml) writes the flat delegations/ directory.

A reader of one run reads exactly the directory the writer used for that
run. A reader across runs (metrics, export, the timeline) takes both layouts,
and counts with attempt_kinds: a record copied into its run's directory is
one delegation, a verifier's record is not an attempt, and the flat layout's
attempt numbers ran on across runs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Mapping, Optional

try:
    import kind_agents
except ImportError:  # imported as lib.record_paths
    from lib import kind_agents  # type: ignore[no-redef]

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


def run_of(path: Path) -> str:
    """The run a record file belongs to; "" for the flat layout."""
    name = path.parent.name
    return name if name != "delegations" and is_slug(name) else ""


def distinct(pairs: Iterable[tuple[Path, dict]]) -> list[tuple[Path, dict]]:
    """One entry per delegation, keeping the copy in its run's directory."""
    seen: set[str] = set()
    out = []
    for path, record in sorted(pairs, key=lambda pair: (run_of(pair[0]) == "", str(pair[0]))):
        key = json.dumps(record, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append((path, record))
    return out


def is_verification(record: Mapping) -> bool:
    """A verifier's report on the writer's attempt, including ones written before role existed."""
    if str(record.get("role") or "").strip().lower() == "verifier":
        return True
    agent, kind = str(record.get("agent") or ""), str(record.get("kind") or "")
    return agent == kind_agents.KIND_VERIFIER.get(kind) and agent != kind_agents.agent_for(kind)


def _attempt(record: Mapping) -> int:
    try:
        return int(str(record.get("attempt") or 1).strip())
    except ValueError:
        return 1


def attempt_kinds(pairs: Iterable[tuple[Path, dict]]) -> dict[Path, str]:
    """first, retry, verification, or unscoped for each record.

    In a run's directory a step's records after its lowest attempt are
    retries. The flat layout numbered attempts across runs, so attempt > 1
    there is a retry or a later run's first try — unscoped, for a person to
    read in brief.prior_failure.
    """
    out: dict[Path, str] = {}
    lowest: dict[tuple[str, str, str], int] = {}
    scoped = []
    for path, record in pairs:
        if is_verification(record):
            out[path] = "verification"
            continue
        run = run_of(path)
        if not run:
            out[path] = "first" if _attempt(record) <= 1 else "unscoped"
            continue
        key = (run, str(record.get("step") or ""), str(record.get("shard") or ""))
        lowest[key] = min(lowest.get(key, _attempt(record)), _attempt(record))
        scoped.append((path, key, _attempt(record)))
    for path, key, attempt in scoped:
        out[path] = "first" if attempt == lowest[key] else "retry"
    return out
