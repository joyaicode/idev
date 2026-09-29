#!/usr/bin/env python3
"""Warn when workflow-defaults products.*.dir is a git root without an idev marker.

Does not guess a sibling. Exit 0 even when warnings are printed. Exit 1 when
the defaults file exists but cannot be read.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from product_marker import is_marked, resolve_extension_repo  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None


def kernel_root() -> Path:
    return Path(__file__).resolve().parents[1]


def install_product() -> Path | None:
    cfg = kernel_root() / "state" / "outbound-config.json"
    if not cfg.is_file():
        return None
    try:
        loaded = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    raw = str(loaded.get("product_root") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def git_root(path: Path) -> Path | None:
    if not path.exists():
        return None
    cur = path if path.is_dir() else path.parent
    for candidate in [cur, *cur.parents]:
        if (candidate / ".git").exists():
            return candidate.resolve()
    return None


def warn_repo(repo: Path) -> int:
    pages, err = resolve_extension_repo(repo)
    if err:
        print("FAIL " + err, file=sys.stderr)
        return 1
    if pages is None:
        print("OK  no idev marker")
        return 0
    if yaml is None:
        print("FAIL product-layout requires PyYAML", file=sys.stderr)
        return 1
    defaults = pages / ".idev" / "workflow-defaults.yaml"
    if not defaults.is_file():
        print("OK  no workflow-defaults")
        return 0
    try:
        data = yaml.safe_load(defaults.read_text(encoding="utf-8"))
    except OSError as exc:
        print("FAIL cannot read %s: %s" % (defaults, exc), file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("FAIL %s: not a mapping" % defaults, file=sys.stderr)
        return 1
    coding = str(data.get("coding_root") or "").strip()
    products = data.get("products") or {}
    if not coding or not isinstance(products, dict):
        print("OK  workflow-defaults has no products")
        return 0
    root = Path(coding).expanduser()
    warnings = 0
    for name, spec in products.items():
        if not isinstance(spec, dict):
            continue
        folder = str(spec.get("dir") or "").strip()
        if not folder:
            continue
        path = (root / folder).expanduser()
        found = git_root(path)
        if found is None:
            continue
        if is_marked(found):
            print("OK  products.%s.dir %s" % (name, found))
            continue
        warnings += 1
        print("WARN products.%s.dir git root has no idev marker: %s" % (name, found))
    if warnings == 0:
        print("product-layout OK")
    else:
        print("product-layout WARN %d" % warnings)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="", help="session checkout")
    parser.add_argument(
        "--from-install",
        action="store_true",
        help="use the install ledger product_root; this is not the session",
    )
    args = parser.parse_args(argv)
    if args.from_install:
        repo = install_product()
        if repo is None:
            print("OK  no install product_root")
            return 0
        print("note: install ledger product root %s" % repo)
        return warn_repo(repo)
    if not args.repo:
        parser.error("--repo or --from-install is required")
    return warn_repo(Path(args.repo).expanduser().resolve())


if __name__ == "__main__":
    sys.exit(main())
