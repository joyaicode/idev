#!/usr/bin/env python3
"""Marker idev writes into a product repo.

During delivery, idev persists recognized product-line characteristics under
<repo>/.idev/. marker.yaml (marker: idev) is part of that write, so a later
session can see the saved state. Self-purification discovers evolve: pilot
repos from that marker. The marker does not select the session by itself.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

SKIP_DIRS = {
    ".git",
    ".idea",
    ".gradle",
    "node_modules",
    "vendor",
    "dist",
    "target",
    "build",
    "out",
}


# One root resolver for all five callers; see roots.py. Imported under the
# old private name because `roots` is already a local variable in three
# functions below.
from roots import inside as _inside  # noqa: E402
from roots import kernel_root  # noqa: E402


def load_marker(repo: str | Path) -> dict[str, Any]:
    """Return a normalized marker, or {} when the repo has not opted in."""
    if yaml is None or not repo:
        return {}
    path = Path(repo) / ".idev" / "marker.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    if not isinstance(data, dict):
        return {}
    if str(data.get("marker") or "").strip() != "idev":
        return {}
    # Missing evolve stays off. First save writes evolve: false. Only an
    # explicit pilot value joins self-evolution.
    raw_evolve = data.get("evolve", False)
    if isinstance(raw_evolve, bool):
        evolve_pilot = raw_evolve
        evolve = "pilot" if raw_evolve else "off"
    else:
        evolve = str(raw_evolve).strip().lower() or "off"
        evolve_pilot = evolve == "pilot"
    return {
        "id": str(data.get("id") or "").strip(),
        "marker": "idev",
        "evolve": evolve,
        "evolve_pilot": evolve_pilot,
        "extension_root": str(data.get("extension_root") or "").strip(),
    }


def is_marked(repo: str | Path) -> bool:
    return bool(load_marker(repo))


def resolve_extension_repo(repo: str | Path) -> tuple[Path | None, str]:
    """Repo whose .idev holds pages, workflows, handoff, checks, and workflow-defaults.

    The session repo is the git checkout being delivered. extension_root, when
    set, is a relative path to another marked repo that holds the shared pages.
    One hop only: the target must not delegate again. Absolute paths are rejected
    so a checkout does not point at one machine.
    """
    repo_path = Path(repo).expanduser().resolve()
    marker = load_marker(repo_path)
    if not marker:
        return None, ""
    raw = str(marker.get("extension_root") or "").strip()
    if not raw:
        return repo_path, ""
    if raw.startswith("~") or Path(raw).is_absolute():
        return None, "extension_root must be a relative path: %s" % raw
    parts = Path(raw).parts
    if not parts or any(part in ("",) for part in parts):
        return None, "extension_root must be a relative path: %s" % raw
    dest = (repo_path / raw).resolve()
    target = load_marker(dest)
    if not target:
        return None, "extension_root has no idev marker: %s" % dest
    if str(target.get("extension_root") or "").strip():
        return None, "extension_root must not delegate again: %s" % dest
    return dest, ""


def read_strip_tokens(repo: str | Path) -> list[str]:
    """Literal product tokens from <repo>/.idev/strip-tokens.txt. Comments ignored."""
    path = Path(repo) / ".idev" / "strip-tokens.txt"
    if not path.is_file():
        return []
    found: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        token = line.split("#", 1)[0].strip()
        if token:
            found.append(token)
    return found


def pilot_strip_tokens(
    extra: list[str] | None = None,
    *,
    from_install: bool = True,
) -> list[str]:
    """Union of strip tokens from evolve: pilot repos. Kernel scripts do not embed a product list."""
    seen: set[str] = set()
    found: list[str] = []
    roots = collect_roots(extra, from_install=from_install)
    for row in discover(roots):
        for token in read_strip_tokens(row["repo"]):
            if token in seen:
                continue
            seen.add(token)
            found.append(token)
    return found


def install_roots(kernel: Path | None = None) -> list[Path]:
    """Search roots hinted by this machine's install ledger. Not a session pilot."""
    kernel = kernel or kernel_root()
    cfg = kernel / "state" / "outbound-config.json"
    if not cfg.is_file():
        return []
    try:
        loaded = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(loaded, dict):
        return []
    raw = str(loaded.get("product_root") or "").strip()
    if not raw:
        return []
    product = Path(raw).expanduser()
    roots = [product.parent, product]
    return [p for p in roots if p.is_dir() and not _inside(p, kernel)]


def collect_roots(
    extra: list[str] | None = None,
    *,
    from_install: bool = False,
    kernel: Path | None = None,
) -> list[Path]:
    kernel = kernel or kernel_root()
    found: list[Path] = []
    seen: set[Path] = set()

    def add(raw: str | Path) -> None:
        text = str(raw).strip()
        if not text:
            return
        path = Path(text).expanduser()
        if not path.is_dir() or _inside(path, kernel):
            return
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        found.append(resolved)

    for part in os.environ.get("IDEV_DISCOVER_ROOTS", "").split(os.pathsep):
        add(part)
    for item in extra or []:
        add(item)
    if from_install:
        for path in install_roots(kernel):
            add(path)
    return found


def discover(
    roots: list[Path],
    *,
    max_depth: int = 2,
    kernel: Path | None = None,
) -> list[dict[str, str]]:
    """Repos whose marker opts into self-evolution as a pilot."""
    kernel = kernel or kernel_root()
    found: list[dict[str, str]] = []
    seen: set[Path] = set()

    def consider(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        if resolved in seen or _inside(resolved, kernel):
            return
        marker = load_marker(resolved)
        if not marker or not marker.get("evolve_pilot"):
            return
        seen.add(resolved)
        found.append(
            {
                "id": str(marker.get("id") or resolved.name),
                "repo": str(resolved),
                "evolve": "pilot",
            }
        )

    def walk(path: Path, depth: int) -> None:
        if not path.is_dir():
            return
        consider(path)
        if (path / ".git").exists() or depth >= max_depth:
            return
        try:
            children = list(path.iterdir())
        except OSError:
            return
        for child in children:
            name = child.name
            if name in SKIP_DIRS or name.startswith("."):
                continue
            if child.is_dir():
                walk(child, depth + 1)

    for root in roots:
        walk(root, 0)
    found.sort(key=lambda row: (row["id"], row["repo"]))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", default=[], help="extra directory to scan")
    parser.add_argument("--from-install", action="store_true", help="also scan around the install ledger product_root")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--check", default="", help="print ok or empty for one repo; exit 0 either way")
    parser.add_argument(
        "--extension-repo",
        default="",
        help="print the repo that holds .idev pages for this checkout; exit 2 when extension_root is invalid",
    )
    parser.add_argument(
        "--strip-tokens",
        action="store_true",
        help="print strip tokens from evolve:pilot repos, one per line",
    )
    args = parser.parse_args(argv)
    if args.strip_tokens:
        for token in pilot_strip_tokens(args.root, from_install=True):
            print(token)
        return 0
    if args.extension_repo:
        dest, err = resolve_extension_repo(args.extension_repo)
        if err:
            print("FAIL " + err, file=sys.stderr)
            return 2
        print("" if dest is None else dest)
        return 0
    if args.check:
        marker = load_marker(args.check)
        if not marker:
            print("")
            return 0
        print(json.dumps(marker, ensure_ascii=False))
        return 0
    rows = discover(collect_roots(args.root, from_install=args.from_install), max_depth=args.depth)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
