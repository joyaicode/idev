#!/usr/bin/env python3
"""Column padding that counts CJK characters as two display columns.

The views in this layer mix Chinese headers with ASCII data. f-string
padding and str.ljust count characters, not columns, so 「步骤」 (2 chars,
4 columns) and `report` (6 chars, 6 columns) pad to the same character
count but different widths — and the whole table shifts right of the first
Chinese cell.

Shared rather than copied into each view, so the tables stay aligned with
each other as columns are added.
"""
from __future__ import annotations

import unicodedata

# W = wide, F = fullwidth. Both occupy two terminal columns.
_WIDE = ("W", "F")


def width(text: str) -> int:
    """Display columns `text` occupies in a monospace terminal."""
    return sum(2 if unicodedata.east_asian_width(c) in _WIDE else 1 for c in str(text))


def ljust(text: str, columns: int) -> str:
    text = str(text)
    return text + " " * max(0, columns - width(text))


def rjust(text: str, columns: int) -> str:
    text = str(text)
    return " " * max(0, columns - width(text)) + text
