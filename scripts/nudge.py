#!/usr/bin/env python3
"""Say what a short reply is, so the conductor does not stop on it.

    python3 scripts/nudge.py --quote "验收"

NUDGE proceed
    Do the open step of the current stage. Do not edit a sealed baseline's
    goal, items, or non_goal. Do not record a stop or a next. Do not restate
    that a gate was not written. A failed check is the work, not a pause.

NUDGE drive-auto / drive-assisted
    The reply only toggles drive_mode. Applied immediately; then continue.

NUDGE named
    The reply names an unseal or a rollback.

NUDGE reply
    A question, a refusal, a hesitation, or an empty reply.

NUDGE work
    Anything else. Do that work.

NUDGE adopt-recommend
    The reply only adopts the AI recommendation (按建议 / 听你的 / …).
    Under drive=auto, decide --source auto with that recommend; do not ask again.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import drive_mode  # noqa: E402
import workflow_spec  # noqa: E402
from product_sink import product_repo  # noqa: E402
from roots import kernel_root  # noqa: E402

ADOPT_RECOMMEND = (
    "按建议", "按建議", "就按建议", "就按建議", "听你的", "聽你的",
    "按推荐", "按推薦", "按这个建议", "按這個建議",
    "adopt recommend", "as recommended",
)


def _is_adopt(quote: str) -> bool:
    raw = drive_mode._normalize_text(quote).strip()  # noqa: SLF001
    if not raw:
        return False
    text = raw.lower()
    for phrase in ADOPT_RECOMMEND:
        if raw == phrase or text == phrase.lower():
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quote", required=True)
    args = parser.parse_args(argv)
    toggle = drive_mode.quote_mode(args.quote)
    if toggle:
        path = drive_mode.set_mode(product_repo(), toggle, kernel_state=kernel_root() / "state")
        mode, source = drive_mode.resolve(product_repo(), kernel_root() / "state")
        print("NUDGE drive-%s" % toggle)
        print(drive_mode.format_line(mode, source))
        print("WROTE %s" % path)
        print("STOP no")
        return 0
    if _is_adopt(args.quote):
        mode, source = drive_mode.resolve(product_repo(), kernel_root() / "state")
        print("NUDGE adopt-recommend")
        print(drive_mode.format_line(mode, source))
        if mode == "auto":
            print(
                "DRIVE_HINT decide --all-open --source auto --recommend <档> "
                "--quote auto:recommend (do not ask again)"
            )
        else:
            print(
                "DRIVE_HINT decide with --answer <档> --quote 按建议 "
                "(adopt the packaged AI recommendation)"
            )
        print("STOP no")
        return 0
    kind = workflow_spec.nudge_kind(args.quote)
    print("NUDGE %s" % kind)
    if kind == "proceed":
        print("BASELINE_ITEMS no")
        print("STOP no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
