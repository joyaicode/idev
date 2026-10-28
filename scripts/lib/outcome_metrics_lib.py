"""Shared WIP / rework counts for outcome-metrics.py and console.py."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from pathlib import Path

import record_paths  # noqa: E402
import safeyaml  # noqa: E402

STAGES = ("req", "arch", "code", "test", "done", "ops")


def parse_at(raw) -> dt.datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            if fmt.endswith("Z") and text.endswith("Z"):
                return dt.datetime.strptime(text, fmt).replace(tzinfo=dt.timezone.utc)
            return dt.datetime.strptime(text.replace("Z", "+0000"), fmt)
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def ticket_dirs(repo: Path) -> list[Path]:
    roots = [repo / "docs" / "task", repo / ".idev" / "task", repo / "task"]
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "deliver.yaml").is_file():
                found.append(child)
    return found


def load_deliver(path: Path) -> dict:
    data = safeyaml.mapping_from_text(path.read_text(encoding="utf-8", errors="replace"))
    return data if isinstance(data, dict) else {}


def stage_of(deliver: dict) -> str:
    stage = str(deliver.get("stage") or "").strip().lower()
    if stage in STAGES:
        return stage
    for key in ("status", "lifecycle"):
        nested = deliver.get(key)
        if isinstance(nested, dict):
            stage = str(nested.get("stage") or "").strip().lower()
            if stage in STAGES:
                return stage
    return "unknown"


def wip_rows(tickets: list[Path], now: dt.datetime | None = None) -> list[dict]:
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = []
    for ticket in tickets:
        deliver_path = ticket / "deliver.yaml"
        stage = stage_of(load_deliver(deliver_path))
        if stage == "done":
            continue
        mtime = dt.datetime.fromtimestamp(deliver_path.stat().st_mtime, tz=dt.timezone.utc)
        age_days = max(0, int((now - mtime).total_seconds() // 86400))
        rows.append({
            "feature": ticket.name,
            "stage": stage,
            "age_days": age_days,
            "path": str(deliver_path),
        })
    rows.sort(key=lambda r: (-r["age_days"], r["feature"]))
    return rows


def rework_from_records(repo: Path, since: dt.datetime | None) -> dict:
    out = {
        "records": 0,
        "retried": 0,
        "rejected": 0,
        "check_fail": 0,
        "by_agent": defaultdict(lambda: {"retried": 0, "rejected": 0, "check_fail": 0, "records": 0}),
    }
    for pattern in record_paths.REPO_GLOBS:
        for path in sorted(repo.glob(pattern)):
            if path.name.endswith(".example.yaml"):
                continue
            record = safeyaml.mapping(path)
            if not isinstance(record, dict):
                continue
            at = parse_at(record.get("at") or record.get("finished_at"))
            if since and at and at < since:
                continue
            out["records"] += 1
            agent = str(record.get("agent") or "?")
            bucket = out["by_agent"][agent]
            bucket["records"] += 1
            try:
                attempt = int(record.get("attempt") or 1)
            except (TypeError, ValueError):
                attempt = 1
            if attempt > 1:
                out["retried"] += 1
                bucket["retried"] += 1
            if str(record.get("outcome") or "") == "rejected":
                out["rejected"] += 1
                bucket["rejected"] += 1
            checks = record.get("checks") or {}
            if isinstance(checks, dict):
                fails = sum(1 for v in checks.values() if str(v).startswith("FAIL"))
                if fails:
                    out["check_fail"] += fails
                    bucket["check_fail"] += fails
    out["by_agent"] = dict(out["by_agent"])
    return out


def stage_histogram(tickets: list[Path]) -> dict[str, int]:
    hist = {s: 0 for s in STAGES}
    hist["unknown"] = 0
    for ticket in tickets:
        stage = stage_of(load_deliver(ticket / "deliver.yaml"))
        hist[stage] = hist.get(stage, 0) + 1
    return hist


def report_for(repo: Path, *, days: int = 60) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=max(0, days))
    tickets = ticket_dirs(repo)
    wip = wip_rows(tickets, now)
    rework = rework_from_records(repo, since)
    return {
        "at": now.isoformat(),
        "repo": str(repo),
        "days": days,
        "tickets": len(tickets),
        "stage_histogram": stage_histogram(tickets),
        "wip": {
            "count": len(wip),
            "oldest_age_days": wip[0]["age_days"] if wip else 0,
            "rows": wip[:30],
        },
        "rework": rework,
        "unproven": [
            "stage lead times (need migration events)",
            "human wait vs agent work (need prompts.log + subagent-stops join)",
            "escape defects (need ship signal)",
            "per-ticket tokens",
        ],
    }
