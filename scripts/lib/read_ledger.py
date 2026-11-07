"""Spans a step already loaded, replayed into the next fresh attempt."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import safeyaml

MAX_BLOCKS = 4
MAX_CHARS = 4000
MAX_LINES = 80
MAX_LINE_CHARS = 500
SPAN_RE = re.compile(r"^([^:\s][^:\n]*):(\d+):(\d+)$")


def ledger_path(ticket: Path) -> Path:
    return ticket / "workflow" / "reads.yaml"


def load(ticket: Path) -> list[dict]:
    data = safeyaml.mapping(ledger_path(ticket)) or {}
    return [row for row in data.get("reads") or [] if isinstance(row, dict)]


def note(ticket: Path, step: str, span: str, digest: str) -> None:
    if not step or not span or not digest:
        return

    def apply(data: dict) -> dict:
        rows = [row for row in (data or {}).get("reads") or [] if isinstance(row, dict)]
        rows = [row for row in rows if not (row.get("step") == step and row.get("span") == span)]
        rows.append({"step": step, "span": span, "sha256": digest})
        data = data or {}
        data["reads"] = rows
        return data

    safeyaml.save_locked(ledger_path(ticket), apply)


def parse_span(span: str) -> tuple[str, int, int] | None:
    match = SPAN_RE.match(span)
    if match is None:
        return None
    path, start_s, end_s = match.group(1), match.group(2), match.group(3)
    if path.startswith("/") or ".." in Path(path).parts:
        return None
    start, end = int(start_s), int(end_s)
    if start < 1 or end < start:
        return None
    return path, start, end


def _contained(repo: Path, full: Path) -> bool:
    try:
        full.relative_to(repo)
    except ValueError:
        return False
    return True


def _clip(line: str) -> str:
    if len(line) <= MAX_LINE_CHARS:
        return line
    return line[:MAX_LINE_CHARS] + "…TRUNCATED_LINE"


def project(ticket: Path, step: str, repo: Path, skip: set[str] | None = None) -> dict:
    """Replay this step's admitted spans into a new attempt.

    A matching sha256 contributes the file text. A changed file, a span that
    no longer exists, or a path outside the repo contributes no text.
    """
    repo = repo.resolve()
    skipped = skip or set()
    rows = [
        row for row in load(ticket)
        if str(row.get("step") or "") == step and row.get("span") and row.get("sha256")
        and str(row["span"]) not in skipped
    ]
    blocks: list[dict] = []
    stale: list[dict] = []
    omitted: list[dict] = []
    refused: list[dict] = []
    remaining = MAX_CHARS
    for row in reversed(rows):
        span = str(row["span"])
        parsed = parse_span(span)
        if parsed is None:
            refused.append({"span": span})
            continue
        path, start, end = parsed
        full = (repo / path).resolve()
        if not _contained(repo, full):
            refused.append({"span": span})
            continue
        if not full.is_file():
            stale.append({"span": span, "reason": "文件不在"})
            continue
        digest = hashlib.sha256(full.read_bytes()).hexdigest()
        if digest != str(row["sha256"]):
            stale.append({"span": span, "reason": "文件已变"})
            continue
        lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
        if start > len(lines):
            stale.append({"span": span, "reason": "区间已不在文件里"})
            continue
        last = min(end, len(lines))
        window = lines[start - 1:last][:MAX_LINES]
        body = "\n".join(f"{start + i}|{_clip(line)}" for i, line in enumerate(window))
        if last - start + 1 > len(window):
            body += f"\nTRUNCATED next={path}:{start + len(window)}:{last}"
        if len(blocks) >= MAX_BLOCKS or remaining <= 0:
            omitted.append({"span": span, "sha256": digest})
            continue
        if len(body) > remaining:
            body = body[:remaining] + "\nTRUNCATED"
        blocks.append({"span": span, "sha256": digest, "text": body})
        remaining -= len(body)
    out: dict = {}
    if blocks:
        out["context_blocks"] = list(reversed(blocks))
    if stale:
        out["context_stale"] = list(reversed(stale))
    if omitted:
        out["context_omitted"] = list(reversed(omitted))
    if refused:
        out["context_refused"] = list(reversed(refused))
    return out
