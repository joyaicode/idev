#!/usr/bin/env python3
"""Export delegation records and traces to Langfuse's ingestion shape.

    langfuse-export.py --feature F [--out FILE]
    langfuse-export.py --repo DIR [--days N] [--out FILE]
    langfuse-export.py --feature F --post        # needs env + the SDK

Offline on purpose. The delivery path must not grow a network dependency:
if a conductor's round can fail because an observability service is down,
observability has become a gate — and this layer's rule is that it never is.
So the records land on disk first (they already do), and this turns them
into Langfuse's shape whenever you want to look at them elsewhere.

Mapping, so the semantics survive the trip:

    one run (a feature's workflow)   -> trace
    one delegation (step + attempt)  -> span under that trace
    checks / BLOCKED class / metrics -> span metadata
    duration_s                       -> span start/end
    report STATUS                    -> span level (DEFAULT / WARNING / ERROR)

What is deliberately NOT exported:
  - the brief and report bodies. They carry product source, ticket contents
    and sometimes credentials-adjacent paths. A delegation brief is the most
    sensitive artifact this layer produces; shipping it to a third party by
    default would be the wrong call to make on someone's behalf. Pass
    --include-bodies if you have decided otherwise for your deployment.
  - any score. The kernel forbids score gates (verify/references/evolve.md),
    so this exports counts and statuses, never a quality number.

--post only works when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are set and
the sdk is importable; without them it says so and writes the file instead.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402

GLOBS = (
    "docs/task/*/workflow/delegations/*.yaml",
    ".idev/task/*/workflow/delegations/*.yaml",
)
STATUS_LINE = re.compile(r"(?mi)^\s*STATUS:\s*(\S+)")
EVIDENCE_LINE = re.compile(r"(?mi)^\s*EVIDENCE:\s*(.+?)\s*$")


def status_of(record: dict) -> str:
    report = record.get("report") or {}
    if report.get("status"):
        return str(report["status"]).upper()
    hit = STATUS_LINE.search(str(report.get("raw", "")))
    return hit.group(1).upper() if hit else ""


def evidence_of(record: dict) -> str:
    report = record.get("report") or {}
    if report.get("evidence"):
        return str(report["evidence"])
    hit = EVIDENCE_LINE.search(str(report.get("raw", "")))
    return hit.group(1).strip() if hit else ""


def duration_of(record: dict) -> int | None:
    explicit = record.get("duration_s")
    if explicit not in (None, ""):
        return safeyaml.as_int(explicit, 0) or None
    started, finished = record.get("started_at"), record.get("finished_at")
    if not started or not finished:
        return None
    try:
        a = dt.datetime.fromisoformat(str(started))
        b = dt.datetime.fromisoformat(str(finished))
        return max(0, int((b - a).total_seconds()))
    except (TypeError, ValueError):
        return None


def level_of(status: str, checks: dict) -> str:
    """Langfuse observation level. Derived, never a score."""
    if any(str(v).startswith("FAIL") for v in checks.values()):
        return "ERROR"
    if status.startswith("BLOCKED") or status.startswith("FAIL"):
        return "ERROR"
    if status.startswith("UNPROVEN"):
        return "WARNING"
    return "DEFAULT"


def collect(repo: Path, feature: str | None, days: int | None) -> list[dict]:
    out: list[dict] = []
    cutoff = dt.datetime.now().astimezone() - dt.timedelta(days=days) if days else None
    for pattern in GLOBS:
        for path in sorted(repo.glob(pattern)):
            if path.name.endswith(".example.yaml"):
                continue
            record = safeyaml.mapping(path)
            if record is None:
                print(f"WARN unreadable or not a mapping, skipped: {path}", file=sys.stderr)
                continue
            if feature and str(record.get("feature")) != feature:
                continue
            if cutoff is not None:
                try:
                    if dt.datetime.fromisoformat(str(record.get("at", ""))) < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass
            out.append(record)
    return out


def build(records: list[dict], include_bodies: bool) -> list[dict]:
    """Group into one trace per feature, one span per delegation."""
    by_feature: dict[str, list[dict]] = {}
    for r in records:
        by_feature.setdefault(str(r.get("feature", "-")), []).append(r)

    traces: list[dict] = []
    for feature, items in sorted(by_feature.items()):
        items.sort(key=lambda r: str(r.get("at", "")))
        spans = []
        for r in items:
            status = status_of(r)
            checks = r.get("checks") or {}
            seconds = duration_of(r)
            start = str(r.get("started_at") or r.get("at") or "")
            end = str(r.get("finished_at") or r.get("at") or "")

            meta = {
                "kind": r.get("kind"),
                "attempt": safeyaml.as_int(r.get("attempt"), 1),
                "outcome": r.get("outcome"),
                "status": status or None,
                "evidence": evidence_of(r) or None,
                "checks": {k: str(v) for k, v in checks.items()},
                "check_fail": sorted(k for k, v in checks.items() if str(v).startswith("FAIL")),
                "duration_s": seconds,
                "suggest": (r.get("suggest") or None),
            }
            blocked = re.search(r"BLOCKED\((\w+)\)", status)
            if blocked:
                meta["blocked_class"] = blocked.group(1)
            if isinstance(r.get("metrics"), dict):
                meta["metrics"] = {k: v for k, v in r["metrics"].items()}

            span = {
                "name": f"{r.get('step')}#{meta['attempt']}",
                "startTime": start,
                "endTime": end,
                "level": level_of(status, checks),
                # The agent is what did the work, so it belongs where a
                # Langfuse reader looks for "who".
                "metadata": {"agent": r.get("agent"), **{k: v for k, v in meta.items() if v is not None}},
            }
            if include_bodies:
                span["input"] = r.get("brief")
                span["output"] = (r.get("report") or {}).get("raw")
            spans.append(span)

        traces.append({
            "name": f"idev/{feature}",
            "sessionId": feature,
            "tags": ["idev", "delegation"],
            "metadata": {
                "delegated": len(items),
                "agents": sorted({str(r.get("agent")) for r in items}),
                "retried": sum(1 for r in items if safeyaml.as_int(r.get("attempt"), 1) > 1),
                "rejected": sum(1 for r in items if str(r.get("outcome")) == "rejected"),
                "bodies_included": include_bodies,
            },
            "observations": spans,
        })
    return traces


def post(traces: list[dict]) -> int:
    pub = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    sec = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    if not pub or not sec:
        print("BLOCKED --post needs LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY", file=sys.stderr)
        return 2
    try:
        from langfuse import Langfuse  # noqa: PLC0415
    except ImportError:
        print("BLOCKED the langfuse sdk is not installed (pip install langfuse)", file=sys.stderr)
        print("HINT    without --post this writes the payload to a file instead", file=sys.stderr)
        return 2

    client = Langfuse(public_key=pub, secret_key=sec, host=os.environ.get("LANGFUSE_HOST") or None)
    for t in traces:
        trace = client.trace(name=t["name"], session_id=t["sessionId"],
                             tags=t["tags"], metadata=t["metadata"])
        for span in t["observations"]:
            trace.span(name=span["name"], start_time=span.get("startTime") or None,
                       end_time=span.get("endTime") or None, level=span["level"],
                       metadata=span["metadata"], input=span.get("input"),
                       output=span.get("output"))
    client.flush()
    print(f"OK   posted {len(traces)} trace(s), {sum(len(t['observations']) for t in traces)} span(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="product checkout (default: cwd)")
    parser.add_argument("--feature", help="only this feature")
    parser.add_argument("--days", type=int, help="only records newer than N days")
    parser.add_argument("--out", type=Path, help="write the payload here (default: stdout)")
    parser.add_argument("--include-bodies", action="store_true",
                        help="also export brief and report bodies (they carry product source)")
    parser.add_argument("--post", action="store_true", help="send via the langfuse sdk instead of writing")
    args = parser.parse_args()

    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"BLOCKED no such checkout: {repo}", file=sys.stderr)
        return 2

    records = collect(repo, args.feature, args.days)
    if not records:
        print("(no delegation records to export)", file=sys.stderr)
        return 0
    traces = build(records, args.include_bodies)
    payload = {"schema": "langfuse/traces@1", "traces": traces}

    if args.post:
        return post(traces)

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"OK   {args.out}  ({len(traces)} trace(s), {len(records)} span(s))")
        if not args.include_bodies:
            print("NOTE brief / report bodies omitted; --include-bodies to add them")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
