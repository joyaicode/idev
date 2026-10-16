#!/usr/bin/env python3
"""ULIDs, so a run has a name that is stable across tools and machines.

A run is currently identified by the path of its run.yaml, which stops
working the moment the same run has to be named by a database row, a trace
span and a log line at once. ULID rather than UUIDv4 because the leading 48
bits are the timestamp: run ids sort chronologically, which is how anyone
reads a list of runs.

Written by hand because Python 3.9 has no ULID in the standard library and
the kernel takes no new dependencies. P1 replaces this with oklog/ulid on
the Go side; the encoding is the same, so ids written now stay valid.
"""
from __future__ import annotations

import datetime as dt
import secrets

# Crockford base32: no I, L, O or U, so a transcribed id cannot be ambiguous.
CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_LEN = 26


def ulid(when: dt.datetime | None = None) -> str:
    """A 26-character ULID: 48 bits of millisecond time, 80 bits random."""
    moment = when or dt.datetime.now(dt.timezone.utc)
    ms = int(moment.timestamp() * 1000)
    value = (ms << 80) | secrets.randbits(80)
    out = []
    for _ in range(ULID_LEN):
        out.append(CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


def is_ulid(text: str) -> bool:
    """True when `text` could have come from ulid()."""
    if not isinstance(text, str) or len(text) != ULID_LEN:
        return False
    return all(c in CROCKFORD for c in text)


if __name__ == "__main__":
    print(ulid())
