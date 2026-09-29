#!/usr/bin/env python3
"""List the current product's pages for one lifecycle stage.

The product declares them in <repo>/.idev/extensions.yaml. Paths are
relative to that .idev directory. No marker, or no extensions file:
print nothing and exit 0. A declared path that is missing or escapes
.idev exits 2.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from product_marker import load_marker, resolve_extension_repo  # noqa: E402
from product_sink import product_repo  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None

STAGES = (
    "req-review",
    "req",
    "arch",
    "code",
    "test",
    "ops",
    "verify-plan",
    "s7",
    "s8",
)


def _fail(msg: str) -> None:
    print("FAIL " + msg, file=sys.stderr)
    raise SystemExit(2)


def _page_entry(path: Path, stage: str, item: object) -> tuple[str, list[str] | None]:
    if isinstance(item, str) and item.strip():
        return item.strip(), None
    if isinstance(item, dict):
        rel = str(item.get("path") or "").strip()
        products = item.get("products")
        if (
            not rel
            or not isinstance(products, list)
            or not products
            or not all(isinstance(product, str) and product.strip() for product in products)
        ):
            _fail("%s: stages.%s entries are a path or {path, products}" % (path, stage))
        return rel, [str(product).strip() for product in products]
    _fail("%s: stages.%s entries are a path or {path, products}" % (path, stage))
    return "", None


def load_stage_map(repo: Path) -> dict[str, list[tuple[str, list[str] | None]]] | None:
    """None when this checkout has not opted in. {} when opted in but undeclared.

    A string entry applies to every product id. `{path, products}` applies
    only when the session marker id is in that list.
    """
    if yaml is None:
        _fail("stage-extensions requires PyYAML")
    if not repo or not load_marker(repo):
        return None
    path = repo / ".idev" / "extensions.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        _fail("cannot read %s: %s" % (path, exc))
    if not isinstance(data, dict):
        _fail("%s: not a mapping" % path)
    if data.get("schema_version") != 1:
        _fail("%s: schema_version must be 1" % path)
    stages = data.get("stages") or {}
    if not isinstance(stages, dict):
        _fail("%s: stages must be a mapping" % path)
    out: dict[str, list[tuple[str, list[str] | None]]] = {}
    for name, pages in stages.items():
        if name not in STAGES:
            _fail("%s: unknown stage %s" % (path, name))
        if pages is None:
            out[str(name)] = []
            continue
        if not isinstance(pages, list):
            _fail("%s: stages.%s must be a list" % (path, name))
        out[str(name)] = [_page_entry(path, str(name), item) for item in pages]
    return out


def page_path(repo: Path, rel: str) -> Path:
    if rel.startswith("/") or "\\" in rel:
        _fail("extension path must stay inside .idev: %s" % rel)
    parts = Path(rel).parts
    if not parts or any(part in ("..", "") for part in parts):
        _fail("extension path must stay inside .idev: %s" % rel)
    root = (repo / ".idev").resolve()
    dest = (root / rel).resolve()
    try:
        dest.relative_to(root)
    except ValueError:
        _fail("extension path must stay inside .idev: %s" % rel)
    return dest


def selected_pages(
    stage_map: dict[str, list[tuple[str, list[str] | None]]],
    stage: str,
    product_id: str,
) -> list[str]:
    chosen: list[str] = []
    for rel, products in stage_map.get(stage, []):
        if products is None or product_id in products:
            chosen.append(rel)
    return chosen


def emit(
    repo: Path,
    stage: str,
    stage_map: dict[str, list[tuple[str, list[str] | None]]],
    product_id: str,
) -> int:
    missing = 0
    for rel in selected_pages(stage_map, stage, product_id):
        dest = page_path(repo, rel)
        if not dest.is_file():
            print("FAIL missing .idev/%s" % rel, file=sys.stderr)
            missing += 1
            continue
        print("OPEN %s" % dest)
    return 2 if missing else 0


def check_all(repo: Path, stage_map: dict[str, list[tuple[str, list[str] | None]]]) -> int:
    missing = 0
    for stage in STAGES:
        for rel, _products in stage_map.get(stage, []):
            dest = page_path(repo, rel)
            if not dest.is_file():
                print("FAIL %s missing .idev/%s" % (stage, rel), file=sys.stderr)
                missing += 1
            else:
                print("OK  %s %s" % (stage, rel))
    return 2 if missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", nargs="?", choices=STAGES)
    parser.add_argument("--repo", default="", help="product checkout; default is the current product")
    parser.add_argument("--product", default="", help="session product id; default is the checkout marker id")
    parser.add_argument("--check-all", action="store_true", help="every declared page must exist")
    args = parser.parse_args(argv)
    if args.repo:
        repo = Path(args.repo).expanduser().resolve()
    else:
        found = product_repo()
        if found is None:
            print("OK  no current product")
            return 0
        repo = found
    pages_repo, err = resolve_extension_repo(repo)
    if err:
        _fail(err)
    if pages_repo is None:
        print("OK  no idev marker")
        return 0
    stage_map = load_stage_map(pages_repo)
    if stage_map is None:
        print("OK  no idev marker")
        return 0
    if args.check_all:
        code = check_all(pages_repo, stage_map)
        print("stage-extensions PASS" if code == 0 else "stage-extensions FAIL")
        return code
    if not args.stage:
        parser.error("stage is required unless --check-all")
    session = load_marker(repo) or {}
    product_id = args.product or str(session.get("id") or "")
    code = emit(pages_repo, args.stage, stage_map, product_id)
    if code == 0 and not selected_pages(stage_map, args.stage, product_id):
        print("OK  no extensions for %s" % args.stage)
    return code


if __name__ == "__main__":
    sys.exit(main())
