"""Confirmed prior art shared by stage entry and delegation briefs.

Two call sites need the same rows: the conductor entering a stage and an
executor receiving a cold-context brief. Both must see only rows that have
already cleared their own ledger's gate — an authoritative lesson or a kept
program. Candidates, retired rows, scores, and semantic search all stay out.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import doc_home  # noqa: E402

MAX = 3


def scopes(
    feature: str,
    stage: str = "",
    workflow: str = "",
    label: str = "",
    scope: str = "",
    writes: Iterable[str] = (),
    shard: str = "",
) -> list[str]:
    """Plain words a ledger row can name, from the facts both callers already have."""
    words = [feature, stage, workflow, label, scope]
    for rel in list(writes) + [shard]:
        head = str(rel).strip().strip("/").split("/")[0]
        if head and not head.startswith("."):
            words.append(head)
    out: list[str] = []
    for word in words:
        word = str(word).strip()
        if word and word not in out:
            out.append(word)
    return out


def _lesson_line(item: dict) -> str:
    return (
        f"{item.get('id')} [经验] 现象 {item.get('symptom')} | 动作 {item.get('action')}"
        f" | 不适用于 {item.get('not_when')} | 依据 {item.get('evidence')}"
    )


def _program_line(item: dict) -> str:
    return (
        f"{item.get('id')} [程序] {item.get('script')} — {item.get('claim')}"
        f" | 不适用于 {item.get('not_when')}"
    )


def lines(
    ticket: Path | None,
    kernel: Path,
    feature: str,
    stage: str = "",
    workflow: str = "",
    label: str = "",
    scope: str = "",
    writes: Iterable[str] = (),
    shard: str = "",
    top: int = MAX,
    repo: Path | None = None,
) -> list[str]:
    """Confirmed rows for this scope, formatted for a human or cold-context reader.

    ``kernel`` is the kernel ledger directory (``state/``), not the checkout
    root. Ticket lessons follow doc_home's intermediate layout; programs stay
    beside the ticket as sediment.py does. This is deliberately non-blocking:
    a broken optional ledger prints a WARN and returns what could be read. A
    stage entry or brief that fails to compose because optional advice is
    unreadable would be worse than one without the advice.
    """
    words = scopes(feature, stage, workflow, label, scope, writes, shard)
    if not words:
        return []

    # The ledger readers depend on PyYAML. session-context deliberately works
    # without it, and optional advice must not turn a stage entry into a
    # dependency failure.
    try:
        import lessons
        import sediment
    except ImportError:
        return []

    out: list[str] = []
    lesson_paths = [kernel / "lessons.yaml"]
    if repo is not None and feature:
        lesson_paths.insert(0, doc_home.intermediate(repo.resolve(), feature, "lessons.yaml"))
    elif ticket is not None:
        lesson_paths.insert(0, ticket / "lessons.yaml")
    try:
        for item in lessons.prior_art(lesson_paths, words, top):
            out.append(_lesson_line(item))
    except Exception as exc:  # noqa: BLE001 — optional advice must not block the caller
        print(f"WARN 经验台账读不了，这一步没有既往: {exc}", file=sys.stderr)

    program_paths = [kernel / "sediment.yaml"]
    if ticket is not None:
        program_paths.insert(0, ticket / "sediment.yaml")
    try:
        for item in sediment.prior_art(program_paths, words, max(0, top - len(out))):
            out.append(_program_line(item))
    except Exception as exc:  # noqa: BLE001
        print(f"WARN 沉淀台账读不了，这一步没有既往: {exc}", file=sys.stderr)
    return out[:top]
