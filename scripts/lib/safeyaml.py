#!/usr/bin/env python3
"""Reading yaml that a person or an agent may have written badly.

The ledgers in this layer — delegation records, fix attempts, hypotheses —
are hand-written or agent-written, so a malformed file is a normal event,
not an exceptional one. One bad file must not take down a whole view: a
timeline that raises on the third record of twenty is useless exactly when
you need it most.

So these return None and let the caller skip and warn, which is what
agent-metrics already did. Shared rather than copied into each reader, so
the three ledgers cannot drift into three different failure behaviours.
"""
from __future__ import annotations

from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment problem, not logic
    raise SystemExit("BLOCKED pyyaml is required (the idev contracts are all yaml)") from exc


def mapping(path: Path) -> dict | None:
    """The file as a dict. None when unreadable, unparseable, or not a mapping.

    An empty file comes back as {} rather than None: "nothing recorded yet"
    is a valid state, while "this file is broken" is not.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return mapping_from_text(text)


def mapping_from_text(text: str) -> dict | None:
    """Same contract, for yaml that arrived on stdin."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if data is None:
        return {}
    return data if isinstance(data, dict) else None


def dump(data: dict) -> str:
    """One serializer for all three ledgers, so their files look alike."""
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def as_int(value: object, default: int = 0) -> int:
    """An int from whatever a ledger happens to hold in that field.

    Ledger fields get filled in by hand and by agents, so `delta: 很多` is
    a thing that happens. Counting it as the default beats crashing the
    tripwire check that was supposed to stop a runaway fix loop.
    """
    if isinstance(value, bool):
        return default
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def as_list(value: object) -> list:
    """A list from a field that should hold one."""
    return value if isinstance(value, list) else []
