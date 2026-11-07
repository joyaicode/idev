#!/usr/bin/env python3
"""Say what a short reply is, so the conductor does not stop on it.

    python3 scripts/nudge.py --quote "验收"

NUDGE proceed
    Do the open step of the current stage. Do not edit a sealed baseline's
    goal, items, or non_goal. Do not record a stop or a next. Do not restate
    that a gate was not written. A failed check is the work, not a pause.

NUDGE named
    The reply names an unseal or a rollback.

NUDGE reply
    A question, a refusal, a hesitation, or an empty reply.

NUDGE work
    Anything else. Do that work.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import workflow_spec  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quote", required=True)
    args = parser.parse_args(argv)
    kind = workflow_spec.nudge_kind(args.quote)
    print("NUDGE %s" % kind)
    if kind == "proceed":
        print("BASELINE_ITEMS no")
        print("STOP no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
