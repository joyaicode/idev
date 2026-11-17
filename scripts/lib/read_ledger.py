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

    Diff pruning (proposal 20261117-agent-loop-enhancement C1, grilling
    4a): when the working tree names changed symbols and the span's file is
    among them but the span sits outside the changed neighborhood, the span
    moves to `context_pruned` with the load instruction — visible, one line,
    never silently gone. Only `ast` mode (python) prunes; brace and file
    modes are PREP nominations and never touch a replay. No diff at all
    (`none` mode) leaves every span exactly as before this hook existed.
    The sha256 admission above still runs first: a changed file is stale by
    digest before it is ever a pruning question.
    """
    repo = repo.resolve()
    skipped = skip or set()
    rows = [
        row for row in load(ticket)
        if str(row.get("step") or "") == step and row.get("span") and row.get("sha256")
        and str(row["span"]) not in skipped
    ]
    prune = _symbol_pruner(repo)
    blocks: list[dict] = []
    stale: list[dict] = []
    omitted: list[dict] = []
    refused: list[dict] = []
    pruned: list[dict] = []
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
        reason = prune(path, start, end)
        if reason:
            pruned.append({"span": span, "sha256": digest, "reason": reason})
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
    if pruned:
        out["context_pruned"] = list(reversed(pruned))
    return out


def _symbol_pruner(repo: Path):
    """A path→(start,end)→reason gate, or a never-prune gate.

    Import lazily and fail to `none` (never prune) on any error: a pruning
    layer that throws would take the replay down with it, and a replay that
    cannot decide is safer unreduced — R3 in the proposal's own terms. The
    `ast`-mode restriction is the part grilling 4a settled: approximation
    modes that cannot name a symbol's true span get to nominate for the
    scan, not to edit what a delegated agent will read back.
    """
    try:
        import symbol_diff

        out = symbol_diff.spans(repo)
        table: dict[str, dict] = {}
        for row in out["changed"]:
            if row["mode"] == "ast":
                table[Path(row["path"]).as_posix()] = row

        def gate(path: str, start: int, end: int) -> str:
            row = table.get(Path(path).as_posix())
            if row is None:
                return ""
            lo, hi = row["neighborhood"]
            if start > hi or end < lo:
                return "区间在本次改动的函数邻域之外，需要时 load 这一段"
            return ""

        return gate
    except Exception:
        def never(path: str, start: int, end: int) -> str:
            return ""

        return never
