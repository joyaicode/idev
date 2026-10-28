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


def lock_path(path) -> Path:
    """The file load_locked and save_locked flock beside a ledger."""
    path = Path(path)
    return path.with_suffix(path.suffix + ".lock")


def load_locked(path, read):
    """Call read(data) while the lock is held. Does not write.

    The critical section stays a read. A subprocess or anything else that
    waits belongs after this returns, and the write is a later save_locked.
    """
    import fcntl

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path(path), "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            data = mapping(path)
            if data is None:
                data = {}
            return read(data)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def save_locked(path, mutate):
    """Read, mutate and write a ledger without losing a concurrent write.

    Three ledgers (hypotheses, lessons, and anything else sharing one file
    across entries) are read-modify-write. Plain write_text loses data the
    moment two processes overlap: each reads the same state, each writes its
    own entry, and the last one wins. Ten concurrent appends left one entry
    — with every call reporting OK, which is the dangerous part.

    `mutate(data)` receives the freshly-read mapping and returns what to
    write. It runs while the lock is held, so it must not block.
    """
    import fcntl
    import os
    import tempfile

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path(path), "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            data = mapping(path)
            if data is None:
                data = {}
            result = mutate(data)
            # Write to a sibling temp file and rename: a reader never sees a
            # half-written ledger, even if this process dies mid-write.
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(dump(result))
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return result


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
