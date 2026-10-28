"""Where every script finds the idev binary. One answer, not five.

IDEV_BIN decides when it is set: a path means that file and nothing else,
and `off` means this process has no Go binary at all — the Python lane, the
way a machine without a build runs. A path that does not exist is not
quietly swapped for some other binary; the caller reports it missing.

Unset, the kernel's own bin/idev is used while it is at least as new as the
Go sources it is built from. A stale one is rebuilt in place when `go` is on
PATH and named on stderr when it is not: a binary older than the code beside
it answers with yesterday's rules, and nothing else would say so. PATH is
the last resort.

    python3 scripts/lib/idev_bin.py          # prints the path, or nothing
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

KERNEL = Path(__file__).resolve().parents[2]
OFF = frozenset({"off", "none", "0"})
SOURCE_DIRS = ("cmd", "internal", "pkg", "api")
EMBEDDED = frozenset({".go", ".json", ".sql", ".yaml"})

_auto: list[str | None] = []


def disabled() -> bool:
    return (os.environ.get("IDEV_BIN") or "").strip().lower() in OFF


def newest_source(root: Path | None = None) -> float:
    """The mtime of the newest file that ends up inside the binary."""
    root = root or KERNEL
    latest = 0.0
    for name in ("go.mod", "go.sum"):
        p = root / name
        if p.is_file():
            latest = max(latest, p.stat().st_mtime)
    for top in SOURCE_DIRS:
        for dirpath, _dirs, files in os.walk(root / top):
            for name in files:
                if name.endswith("_test.go") or os.path.splitext(name)[1] not in EMBEDDED:
                    continue
                latest = max(latest, os.stat(os.path.join(dirpath, name)).st_mtime)
    return latest


def stale(binary: Path, root: Path | None = None) -> bool:
    return binary.stat().st_mtime < newest_source(root)


def build(out: Path, root: Path | None = None) -> bool:
    """go build ./cmd/idev into out, swapped in whole. False when it cannot."""
    root = root or KERNEL
    go = shutil.which("go")
    if not go or not (root / "cmd" / "idev").is_dir():
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.{os.getpid()}.tmp")
    proc = subprocess.run(
        [go, "build", "-o", str(tmp), "./cmd/idev"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        print(f"WARN go build ./cmd/idev failed: {detail[0] if detail else proc.returncode}", file=sys.stderr)
        return False
    os.replace(tmp, out)
    return True


def _kernel_build(rebuild: bool) -> str | None:
    built = KERNEL / "bin" / "idev"
    if not built.is_file():
        return None
    if not (KERNEL / "cmd" / "idev").is_dir() or not stale(built):
        return str(built)
    if rebuild and build(built):
        print(f"NOTE rebuilt {built}: the Go sources were newer than the binary", file=sys.stderr)
        return str(built)
    print(
        f"WARN {built} is older than the Go sources beside it; "
        f"rebuild with: cd {KERNEL} && go build -o bin/idev ./cmd/idev",
        file=sys.stderr,
    )
    return str(built)


def path(rebuild: bool = True) -> str | None:
    """The binary this process should run, or None when it has none."""
    explicit = (os.environ.get("IDEV_BIN") or "").strip()
    if explicit:
        if explicit.lower() in OFF:
            return None
        return explicit if Path(explicit).is_file() else None
    if not _auto:
        _auto.append(_kernel_build(rebuild) or shutil.which("idev"))
    return _auto[0]


if __name__ == "__main__":
    found = path()
    if found:
        print(found)
