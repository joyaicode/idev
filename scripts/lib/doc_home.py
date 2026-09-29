#!/usr/bin/env python3
"""Resolve where a product's idev documents and stage state live.

Directory layout follows setup-agents-docs (Matt Pocock). Question text
follows grilling. This module does not define a third layout.

When the repo already has both (feature slug in AGENTS.md or
docs/agents/issue-tracker.md, and grilling named there or in a
docs/task grill.md), read and write:

    docs/prd/<feature>.md
    docs/spec/<feature>.md
    docs/test-case/<feature>.md
    docs/task/<feature>/

A repo whose AGENTS.md or issue tracker names ``docs/specs/`` keeps its
specs there; that declaration overrides the setup-agents-docs default.
Those files win when the same name also exists under ``.idev/``.
A repo that does not have that pair yet does not get a new ``docs/``
tree. Stage state goes under ``.idev/task/`` and human drafts under
``.idev/docs/``. A ticket that already exists on only one side stays
there. This module does not create directories.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_GRILL_LINE = re.compile(r"(?m)^convention:\s*grilling\s*$")
_GRILLING_WORD = re.compile(r"(?i)\bgrilling\b")


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _slug_blob(repo: Path) -> str:
    return _text(repo / "docs" / "agents" / "issue-tracker.md") + "\n" + _text(repo / "AGENTS.md")


def product_spec_dir(repo: Path) -> str:
    """``specs`` when the repo declares the plural spec directory, else ``spec``."""
    return "specs" if "docs/specs/" in _slug_blob(repo) else "spec"


def matt_ready(repo: Path) -> bool:
    """True when the repo publishes the setup-agents-docs feature slug."""
    tracker = repo / "docs" / "agents" / "issue-tracker.md"
    agents = repo / "AGENTS.md"
    blob = _slug_blob(repo)
    has_prd = "docs/prd/" in blob
    has_spec = "docs/spec/" in blob or "docs/specs/" in blob
    has_task = "docs/task/" in blob
    if tracker.is_file() and (has_prd or has_spec or has_task):
        return True
    return agents.is_file() and has_prd and has_spec and has_task


def grilling_ready(repo: Path) -> bool:
    """True when product docs already use the grilling question convention."""
    for path in (repo / "docs" / "agents" / "issue-tracker.md", repo / "AGENTS.md"):
        if _GRILLING_WORD.search(_text(path)):
            return True
    task = repo / "docs" / "task"
    if not task.is_dir():
        return False
    for path in task.rglob("grill.md"):
        if path.is_file() and _GRILL_LINE.search(_text(path)):
            return True
    return False


def uses_product_docs(repo: Path) -> bool:
    return matt_ready(repo) and grilling_ready(repo)


def _has_ticket(path: Path) -> bool:
    if not path.is_dir():
        return False
    for name in ("deliver.yaml", "baseline.yaml", "ops.yaml"):
        if (path / name).is_file():
            return True
    return (path / "verify" / "plan.yaml").is_file()


def layout_for(repo: Path, feature: str) -> str:
    """Return ``product`` when Matt Pocock + grilling docs apply, else ``native``."""
    product = repo / "docs" / "task" / feature
    native = repo / ".idev" / "task" / feature
    product_hit = _has_ticket(product)
    native_hit = _has_ticket(native)
    if uses_product_docs(repo):
        if product_hit or not native_hit:
            return "product"
        return "native"
    if product_hit:
        return "product"
    return "native"


def spec_pair(repo: Path, feature: str, layout: str) -> tuple[Path, Path]:
    """Return (conforming spec file, the other spelling)."""
    if layout == "product":
        base = repo / "docs"
        keep = product_spec_dir(repo)
    else:
        base = repo / ".idev" / "docs"
        keep = "spec"
    other = "spec" if keep == "specs" else "specs"
    name = "%s.md" % feature
    return base / keep / name, base / other / name


def _spec_file(repo: Path, feature: str, layout: str) -> Path:
    modern, legacy = spec_pair(repo, feature, layout)
    if legacy.is_file() and not modern.is_file():
        return legacy
    return modern


def reconcile_spec(repo: Path, feature: str, layout: str) -> Path:
    """When both spec files exist, keep the conforming path and drop the other.

    Body that is only in the other spelling is appended to the conforming
    file first. A lone file under the other spelling is left in place.
    """
    modern, legacy = spec_pair(repo, feature, layout)
    if not (modern.is_file() and legacy.is_file()):
        return _spec_file(repo, feature, layout)
    modern_text = modern.read_text(encoding="utf-8")
    legacy_text = legacy.read_text(encoding="utf-8")
    legacy_body = legacy_text.strip()
    if legacy_body and legacy_body not in modern_text:
        if not modern_text.strip():
            written = legacy_text if legacy_text.endswith("\n") else legacy_text + "\n"
            modern.write_text(written, encoding="utf-8")
        else:
            sep = "" if modern_text.endswith("\n") else "\n"
            modern.write_text(modern_text + sep + "\n" + legacy_body + "\n", encoding="utf-8")
    legacy.unlink()
    return modern


def homes(repo: Path, feature: str) -> dict:
    layout = layout_for(repo, feature)
    if layout == "product":
        base_docs = repo / "docs"
        task = base_docs / "task" / feature
    else:
        base_docs = repo / ".idev" / "docs"
        task = repo / ".idev" / "task" / feature
    return {
        "layout": layout,
        "task": task,
        "deliver": task / "deliver.yaml",
        "plan": task / "verify" / "plan.yaml",
        "prd": base_docs / "prd" / ("%s.md" % feature),
        "spec": _spec_file(repo, feature, layout),
        "test-case": base_docs / "test-case" / ("%s.md" % feature),
        "patrol": base_docs / "test-case" / ("%s-patrol.yaml" % feature),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--feature", default="")
    parser.add_argument(
        "--key",
        default="task",
        choices=["layout", "task", "deliver", "plan", "prd", "spec", "test-case", "patrol"],
    )
    args = parser.parse_args(argv)
    repo = Path(args.repo).expanduser().resolve()
    if args.key == "layout" and not args.feature:
        print("product" if uses_product_docs(repo) else "native")
        return 0
    if not args.feature:
        print("FAIL --feature is required", file=sys.stderr)
        return 2
    found = homes(repo, args.feature)
    if args.key == "layout":
        print(found["layout"])
        return 0
    print(found[args.key])
    return 0


if __name__ == "__main__":
    sys.exit(main())
