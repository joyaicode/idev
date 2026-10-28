"""Explicit break-glass for IDEV_ENGINE=python when the Go binary is present (E1.3).

Env alone is not enough once `idev` is on PATH: a file must name the reason
and an expiry. While the window is open, write/verify leases stay mandatory —
the break-glass only allows the Python driver to own YAML bytes, not to skip
fencing.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import safeyaml  # noqa: E402


def data_dir() -> Path:
    raw = (os.environ.get("IDEV_DATA") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".idev").resolve()


def break_glass_path() -> Path:
    override = (os.environ.get("IDEV_PYTHON_BREAK_GLASS") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return data_dir() / "break-glass" / "python-engine.yaml"


def _parse_expiry(raw: str) -> dt.datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def active() -> tuple[bool, str]:
    """Return (ok, detail). ok means a non-expired break-glass file is present."""
    path = break_glass_path()
    if not path.is_file():
        return False, f"missing {path}"
    doc = safeyaml.mapping(path)
    if doc is None:
        return False, f"unreadable {path}"
    reason = str(doc.get("reason") or "").strip()
    by = str(doc.get("by") or "").strip()
    expires = _parse_expiry(str(doc.get("expires") or ""))
    if not reason or not by or expires is None:
        return False, f"{path} needs reason, by, and expires (ISO-8601)"
    now = dt.datetime.now(dt.timezone.utc)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)
    if expires <= now:
        return False, f"{path} expired at {expires.isoformat()}"
    return True, f"break-glass until {expires.isoformat()} by {by}: {reason}"


def require_or_explain(idev_present: bool) -> str | None:
    """None when python is allowed; otherwise a BLOCKED message."""
    if not idev_present:
        return None
    ok, detail = active()
    if ok:
        return None
    path = break_glass_path()
    return (
        "IDEV_ENGINE=python is refused while the idev binary is available "
        f"({detail}). Write {path} with reason/by/expires to break glass; "
        "write and verify leases stay mandatory during the window"
    )
