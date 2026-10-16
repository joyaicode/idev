#!/usr/bin/env python3
"""Where the idev kernel is. One answer, so five callers cannot disagree.

This used to be five functions. `kind_agents` honoured IDEV_ROOT; the other
four — `product_sink`, `product_marker`, `session-context` and
`product-layout-check` — ignored it and walked up from their own file. So
`IDEV_ROOT=/other/checkout` moved the agent table and nothing else: the sink
still wrote into this checkout's state/, the marker still described this
checkout, and the two layout checks still audited this checkout. A split
brain that only showed up when someone actually used the override.

The anchor is this file, not the caller's file. That is why the old
`parents[2]` (for scripts/lib/*) and `parents[1]` (for scripts/*) collapse
into one expression: callers no longer measure their own depth.

IDEV_ROOT has two meanings in flight. Before the Go rewrite it named the
kernel checkout itself; the idevd design names a data root that *contains*
the kernel at $IDEV_ROOT/kernel. Both are probed, so the same value keeps
working across the migration.

A set-but-unusable IDEV_ROOT falls back rather than exploding — a temp dir
in a test harness must not take down every script that imports this. But
the fallback is recorded in `resolve().note`, so `--kernel` can still tell
a person their override is being ignored instead of silently using the
wrong kernel.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

# Files only the kernel has. Kept here because every probe below needs them;
# kind_agents re-exports the name so its existing importers keep working.
KERNEL_MARKERS = ("scripts/lib/workflow_spec.py", "conventions/SKILL.md")

# This file is <kernel>/scripts/lib/roots.py.
_CHECKOUT = Path(__file__).resolve().parents[2]


class Resolution(NamedTuple):
    """Where the root came from, for diagnostics that name the cause."""

    path: Path
    source: str  # "IDEV_ROOT" | "IDEV_ROOT/kernel" | "checkout"
    note: str  # "" when nothing surprising happened


def is_kernel(path: Path) -> bool:
    """True when every kernel marker file is present under `path`."""
    base = Path(path).expanduser()
    return all((base / marker).is_file() for marker in KERNEL_MARKERS)


def inside(child: Path, parent: Path) -> bool:
    """True when `child` is at or under `parent`, both fully resolved.

    product_sink and product_marker each carried a verbatim copy of this.
    """
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def resolve() -> Resolution:
    """The kernel root and how it was found."""
    env = os.environ.get("IDEV_ROOT", "").strip()
    if env:
        root = Path(env).expanduser().resolve()
        if is_kernel(root):
            return Resolution(root, "IDEV_ROOT", "")
        nested = root / "kernel"
        if is_kernel(nested):
            return Resolution(nested.resolve(), "IDEV_ROOT/kernel", "")
        return Resolution(
            _CHECKOUT,
            "checkout",
            f"IDEV_ROOT={env} is not an idev root and has no kernel/ inside it; "
            f"using this checkout instead",
        )
    return Resolution(_CHECKOUT, "checkout", "")


def kernel_root() -> Path:
    """The idev root. The one implementation; everyone else imports this."""
    return resolve().path


def main(argv: list[str] | None = None) -> int:
    """Print the resolved root, so shell scripts stop hardcoding a path."""
    import argparse

    parser = argparse.ArgumentParser(description="print the resolved idev kernel root")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 2 when IDEV_ROOT is set but unusable, instead of falling back",
    )
    parser.add_argument("--why", action="store_true", help="also print how it was found")
    args = parser.parse_args(argv)

    found = resolve()
    if found.note:
        import sys

        print(f"WARN {found.note}", file=sys.stderr)
        if args.strict:
            return 2
    print(found.path)
    if args.why:
        print(f"source={found.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
