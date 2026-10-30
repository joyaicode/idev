"""Extract structured fields from a trace before prose is folded into memory.

Phase 2 §2: the user citation (invoke), decisions, paths not taken,
delegation outcomes, recorded step status and evidence paths, and call
results stay under .idev/timeline/. memory.md keeps one prose line.
"""
from __future__ import annotations

import re
from pathlib import Path

import safeyaml  # noqa: E402

KEEP_KEYS = (
    "schema_version",
    "at",
    "feature",
    "intent",
    "invoke",
    "route",
    "rejected",
    "decisions",
    "thinking",
    "opened",
    "extensions",
    "calls",
    "delegations",
    "recorded",
    "check_feature",
)


def extract_trace_facts(path: Path) -> dict | None:
    """Return the structured subset of a trace YAML, or None if unreadable."""
    data = safeyaml.mapping(path)
    if not isinstance(data, dict):
        return None
    out = {k: data[k] for k in KEEP_KEYS if k in data}
    # Also pull scenario if only nested under route.
    if "route" in out and isinstance(out["route"], dict):
        pass
    elif "scenario" in data:
        out.setdefault("route", {})
        if isinstance(out["route"], dict):
            out["route"]["scenario"] = data["scenario"]
    if not out.get("feature") and not out.get("at"):
        # Bare prose file — nothing structured to keep.
        if not any(k in data for k in ("calls", "route", "extensions", "schema_version")):
            return None
    out["_source"] = path.name
    return out


def timeline_path(dirs: dict[str, Path], feature: str) -> Path:
    safe = re.sub(r"[^\w.-]+", "_", (feature or "unknown").strip()) or "unknown"
    root = dirs.get("timeline")
    if root is None:
        # Sibling of memory.md: .idev/timeline/ or state/timeline/
        memory = dirs["memory"]
        root = memory.parent / "timeline"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{safe}.yaml"


def append_facts(dirs: dict[str, Path], path: Path) -> Path | None:
    """Append structured facts from path into the feature timeline. Returns the timeline file."""
    facts = extract_trace_facts(path)
    if facts is None:
        return None
    feature = str(facts.get("feature") or "unknown")
    dest = timeline_path(dirs, feature)
    existing = safeyaml.mapping(dest) if dest.is_file() else None
    events = []
    if isinstance(existing, dict) and isinstance(existing.get("events"), list):
        events = list(existing["events"])
    events.append(facts)
    body = {
        "schema_version": 1,
        "feature": feature,
        "events": events,
    }
    dest.write_text(safeyaml.dump(body), encoding="utf-8")
    return dest
