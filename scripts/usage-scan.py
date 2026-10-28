#!/usr/bin/env python3
"""List recipes / scenarios with zero hits in the last N days (phase 2 §4).

    usage-scan.py --repo <product-checkout> [--days 60] [--apply]

Dry-run prints MOVE candidates. --apply relocates matching workflow YAML
files into attic/workflows/ and writes attic/MOVED.md.

Safety:
- refuses --apply when --repo is the kernel itself (no product evidence)
- never moves names listed in attic/PROTECTED.md
- cold-but-protected are printed as KEEP, not COLD
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from product_sink import kernel_root  # noqa: E402
import safeyaml  # noqa: E402

SCENARIO_RE = re.compile(r"(?m)^\s*scenario:\s*[\"']?(S[1-8])\b")
PROTECTED_LINE = re.compile(r"(?m)^\s*-\s+([A-Za-z0-9][\w.-]*)\s*$")


def workflow_files(root: Path) -> list[Path]:
    folder = root / "workflows"
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.yaml") if p.is_file())


def protected_names(root: Path) -> set[str]:
    path = root / "attic" / "PROTECTED.md"
    if not path.is_file():
        return set()
    return set(PROTECTED_LINE.findall(path.read_text(encoding="utf-8", errors="replace")))


def scenario_hits(repo: Path, since: dt.datetime) -> dict[str, int]:
    hits = {f"S{i}": 0 for i in range(1, 9)}
    for home in (repo / "docs" / "task", repo / ".idev" / "task", repo / ".idev" / "traces"):
        if not home.exists():
            continue
        for path in home.rglob("*.yaml"):
            try:
                if path.stat().st_mtime < since.timestamp():
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = SCENARIO_RE.search(text)
            if m:
                hits[m.group(1)] = hits.get(m.group(1), 0) + 1
    return hits


def recipe_hits(repo: Path, root: Path, since: dt.datetime) -> dict[str, int]:
    counts = {p.stem: 0 for p in workflow_files(root)}
    for home in (repo / "docs" / "task", repo / ".idev" / "task"):
        if not home.is_dir():
            continue
        for path in home.rglob("run.yaml"):
            try:
                if path.stat().st_mtime < since.timestamp():
                    continue
                data = safeyaml.mapping(path) or {}
            except OSError:
                continue
            wid = str(data.get("workflow_id") or "").strip()
            if wid in counts:
                counts[wid] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--kernel", type=Path, default=None, help="kernel root (default: this checkout)")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    root = (args.kernel or kernel_root()).resolve()
    if args.apply and repo == root:
        print(
            "BLOCKED --apply against the kernel itself; pass a product --repo "
            "with real tickets so cold recipes are evidenced",
            file=sys.stderr,
        )
        return 2
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max(0, args.days))
    recipes = recipe_hits(repo, root, since)
    scenarios = scenario_hits(repo, since)
    protected = protected_names(root)
    cold_recipes = sorted(name for name, n in recipes.items() if n == 0 and name not in protected)
    kept_cold = sorted(name for name, n in recipes.items() if n == 0 and name in protected)
    cold_scenarios = sorted(sid for sid, n in scenarios.items() if n == 0)
    print(f"# usage-scan repo={repo} kernel={root} days={args.days} apply={args.apply}")
    print(
        f"cold_recipes={len(cold_recipes)} protected_cold={len(kept_cold)} "
        f"cold_scenarios={len(cold_scenarios)}"
    )
    for name in kept_cold:
        print(f"KEEP recipe {name} (attic/PROTECTED.md)")
    for name in cold_recipes:
        print(f"COLD recipe {name}")
    for sid in cold_scenarios:
        print(f"COLD scenario {sid} (informational; scenarios are not moved)")
    if not args.apply:
        if cold_recipes:
            print("hint: re-run with --apply on a product --repo to move unprotected cold recipes")
        return 0
    attic = root / "attic" / "workflows"
    attic.mkdir(parents=True, exist_ok=True)
    moved = []
    for name in cold_recipes:
        src = root / "workflows" / f"{name}.yaml"
        if not src.is_file():
            continue
        dest = attic / src.name
        if dest.exists():
            print(f"SKIP {name}: already in attic")
            continue
        shutil.move(str(src), str(dest))
        moved.append(name)
        print(f"MOVE workflows/{name}.yaml -> attic/workflows/{name}.yaml")
    log = root / "attic" / "MOVED.md"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    block = f"\n## {stamp} from {repo.name}\n\n" + "\n".join(f"- `{n}`" for n in moved) + "\n"
    if moved:
        prev = log.read_text(encoding="utf-8") if log.is_file() else "# Moved to attic\n"
        log.write_text(prev.rstrip() + block, encoding="utf-8")
    print(f"usage-scan PASS moved={len(moved)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
