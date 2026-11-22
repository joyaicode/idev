#!/usr/bin/env python3
"""Terminal-friendly rendering for the things a person reviews.

    from termview import link, row_table, paint

Every "review this before you sign" surface — the trace short table, the
check-feature verdict block, the lean-review lens roster — used to paste
Markdown source into the chat. Markdown tables read fine in a renderer
and badly in a terminal: pipes everywhere, no alignment, paths that
cannot be clicked.

Three primitives, one policy:

  paint(text, role)   color only when stdout is a TTY and NO_COLOR is unset
                      (FAIL red / PASS green / headings bold), plain text
                      otherwise — CI logs and pipes stay byte-identical
  link(label, path, line)  OSC 8 hyperlink when the TTY test passes
                      (iTerm2, Apple Terminal, Kitty, most modern terms),
                      bare "path:line" text otherwise — a pipe reading it
                      still gets the location
  row_table(rows, widths)  aligned two-column list, no pipes: the
                      terminal-native replacement for "| k | v |" blocks

Nothing here scores, gates, or decides anything: rendering only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ESC = "\x1b"

# SGR codes, kept to the 8-color baseline so every terminal has them.
_STYLES = {
    "FAIL": (_ESC + "[31m", _ESC + "[39m"),    # red
    "WARN": (_ESC + "[33m", _ESC + "[39m"),    # yellow
    "PASS": (_ESC + "[32m", _ESC + "[39m"),    # green
    "HINT": (_ESC + "[36m", _ESC + "[39m"),   # cyan
    "OPEN": (_ESC + "[36m", _ESC + "[39m"),   # cyan
    "HEAD": (_ESC + "[1m", _ESC + "[22m"),     # bold
    "DIM": (_ESC + "[2m", _ESC + "[22m"),     # dim
    "RESET": ("", ""),
}


def _interactive(stream=None) -> bool:
    """Color and hyperlinks only for a person at a terminal.

    NO_COLOR (https://no-color.org) and a non-TTY stdout both mean plain
    text: pipes and CI logs must stay byte-stable, and golden snapshots
    record the plain lane.
    """
    if os.environ.get("NO_COLOR"):
        return False
    stream = stream if stream is not None else sys.stdout
    return hasattr(stream, "isatty") and stream.isatty()


def paint(text: str, role: str, stream=None) -> str:
    """Wrap text in the role's SGR pair; plain when not interactive."""
    start, end = _STYLES.get(role, ("", ""))
    if not start or not _interactive(stream):
        return text
    return start + text + end


def link(label: str, path: str, line: int | None = None, stream=None) -> str:
    """Clickable path when the terminal speaks OSC 8, else bare text.

    file:// URLs make the path openable from iTerm2/Apple Terminal/Kitty
    with a Cmd+Click. The fallback is the conventional "path:line" — the
    thing every editor greps for — so a piped reader loses nothing.
    """
    text = "%s:%d" % (path, line) if line else path
    if not _interactive(stream):
        return text
    # Resolve so the URL survives relative-path ambiguity in the terminal.
    try:
        abs_path = str(Path(path).expanduser().resolve())
    except OSError:
        return text
    url = "file://" + abs_path
    open_seq = "%s]8;;%s%s" % (_ESC, url, _ESC + "\\")
    close_seq = "%s]8;;%s" % (_ESC, _ESC + "\\")
    return open_seq + (label or text) + close_seq


def row_table(rows: list[tuple[str, str]], indent: int = 0, stream=None) -> str:
    """Aligned two-column rows — the terminal answer to "| k | v |".

    Column width follows the longest key so every value starts at the
    same column; wide values wrap naturally because nothing is padded on
    the right. Keys carry no trailing colon (the gutter is the separator),
    and empty values render as an em dash so a blank row still shows.
    """
    if not rows:
        return ""
    width = max(len(k) for k, _ in rows)
    pad = " " * indent
    out = []
    for key, value in rows:
        value = (value or "").strip() or "—"
        # A value holding real newlines keeps its own shape under the key.
        if "\n" in value:
            first, *rest = value.splitlines()
            out.append("%s%s  %s" % (pad, key.ljust(width), first))
            out.extend("%s%s  %s" % (pad, " " * width, r) for r in rest)
        else:
            out.append("%s%s  %s" % (pad, key.ljust(width), value))
    return "\n".join(out)


def heading(text: str, stream=None) -> str:
    """A section header without Markdown '#': bold when interactive."""
    return paint(text, "HEAD", stream)


def strip_md_table(lines: list[str]) -> list[tuple[str, str]]:
    """Parse a '| k | v |' block into rows — for renderers migrating over."""
    rows: list[tuple[str, str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= {"-", " ", ":"}:
            continue  # header separator or malformed
        rows.append((cells[0], " | ".join(cells[1:])))
    return rows
