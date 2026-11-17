#!/usr/bin/env python3
"""stop / Stop: start skill-up when the kernel tree changed.

Best-effort. The hook returns immediately. The child decides whether the
tree changed, and a missing CLI is a skip, not a blocked stop.
Set SKILL_UP_EVAL=0 to keep the hook quiet (tests, selfcheck).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def kernel_root() -> Path:
    return Path(__file__).resolve().parents[1]


def argv(root: Path) -> list[str]:
    return [sys.executable, str(root / "scripts" / "skill-up-eval.py")]


def spawn(root: Path) -> None:
    log = root / "state" / "skill-up" / "hook.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = log.open("a", encoding="utf-8")
    try:
        subprocess.Popen(
            argv(root), cwd=str(root), stdin=subprocess.DEVNULL,
            stdout=handle, stderr=subprocess.STDOUT, start_new_session=True,
        )
    finally:
        handle.close()


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", default="cursor", choices=("cursor", "claude"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    if os.environ.get("SKILL_UP_EVAL", "1") == "0":
        return lib.allow()
    spawn(kernel_root())
    return lib.allow()


if __name__ == "__main__":
    raise SystemExit(main())
