"""Tests get their own store and a binary built from the code under test.

pin() points IDEV_DATA at a throwaway directory and pins IDEV_BIN: to the
kernel's bin/idev while it is current, to a fresh build in the throwaway
directory when it is not, and to `off` when there is no Go toolchain. A test
run then never writes into the person's ~/.idev, and the same commit gives
the same answers whether or not someone left a build lying around.

A harness that already chose (selfcheck exports both) is left alone, except
that IDEV_DATA naming the person's own store is never kept.

    python3 scripts/lib/testenv.py bin <dir>   # the IDEV_BIN a shell harness should export
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import idev_bin

_scratch: list[Path] = []


def _own_dir() -> Path:
    if not _scratch:
        made = Path(tempfile.mkdtemp(prefix="idev-test-"))
        atexit.register(shutil.rmtree, made, True)
        _scratch.append(made)
    return _scratch[0]


def binary_for_tests(scratch: Path) -> str:
    built = idev_bin.KERNEL / "bin" / "idev"
    if built.is_file() and not idev_bin.stale(built):
        return str(built)
    out = scratch / "bin" / "idev"
    if idev_bin.build(out):
        return str(out)
    return "off"


def go_binary() -> str | None:
    """The binary a Go-lane test drives, even when the harness pinned the python lane."""
    pinned = (os.environ.get("IDEV_BIN") or "").strip()
    if pinned and Path(pinned).is_file():
        return pinned
    made = binary_for_tests(_own_dir())
    return None if made == "off" else made


def personal_store(value: str) -> bool:
    if not value.strip():
        return True
    home = Path.home() / ".idev"
    return Path(value).expanduser().resolve() == home.resolve()


def pin() -> None:
    if personal_store(os.environ.get("IDEV_DATA") or ""):
        data = _own_dir() / "data"
        data.mkdir(parents=True, exist_ok=True)
        os.environ["IDEV_DATA"] = str(data)
    if not (os.environ.get("IDEV_BIN") or "").strip():
        os.environ["IDEV_BIN"] = binary_for_tests(_own_dir())


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "bin":
        raise SystemExit("usage: testenv.py bin <scratch-dir>")
    print(binary_for_tests(Path(sys.argv[2])))
