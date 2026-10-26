#!/usr/bin/env python3
"""Validate idev workflow recipes and optional run.yaml instances.

Syntax comes from lib/workflow_spec.py. A product may keep many recipes, one
per scenario; a product recipe with a kernel id replaces the kernel one. Every
id and alias must name exactly one effective recipe, or routing would depend
on file order. A run.yaml that records its recipe must follow that recipe's steps.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import workflow_compose  # noqa: E402
from workflow_spec import check_catalog, check_recipe, check_run, check_tool_refs  # noqa: E402


def load(path: Path):
    text = path.read_text(encoding="utf-8")
    if yaml is None:
        # minimal fallback: refuse without pyyaml
        raise SystemExit("workflow-check requires PyYAML (python3 -c 'import yaml')")
    return yaml.safe_load(text)


# Latin words in an utterance that are not product names.
STOP_SLUGS = {
    "ui",
    "lifecycle",
    "full",
    "automation",
    "localdev",
    "start",
    "stop",
    "idev",
    "change",
    "lite",
    "review",
    "code",
    "repo",
    "commit",
    "push",
    "build",
    "scan",
    "coverage",
    "playbook",
    "evolve",
}


def recipe_aliases(data: dict) -> list[str]:
    names = []
    wid = data.get("id")
    if isinstance(wid, str) and wid:
        names.append(wid)
    for alias in data.get("aliases") or []:
        if isinstance(alias, str) and alias:
            names.append(alias)
    return names


def recipe_requires_product(data: dict) -> bool:
    for param in data.get("params") or []:
        if isinstance(param, dict) and param.get("name") == "product" and param.get("required"):
            return True
    return False


def named_products(utterance: str) -> list[str]:
    found = []
    for slug in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", utterance):
        low = slug.lower()
        if low in STOP_SLUGS or low in found:
            continue
        found.append(low)
    return found


def pick_recipe(utterance: str, catalog: dict[str, dict]) -> str | None:
    best_len = -1
    best_id = None
    for rid, meta in catalog.items():
        for alias in meta.get("aliases") or []:
            if not alias or alias not in utterance:
                continue
            n = len(alias)
            if n > best_len:
                best_len = n
                best_id = rid
    if best_id and catalog[best_id].get("require_product"):
        if len(named_products(utterance)) != 1:
            return None
    return best_id


def skill_description(skill: Path) -> str:
    text = skill.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    return parts[1] if len(parts) >= 3 else text


def check_discovery(
    skill: Path,
    kernel_ids: list[str],
    product_names: list[str],
    errors: list[str],
) -> None:
    """The entry lists every kernel recipe id and no product recipe name."""
    if not skill.is_file():
        errors.append(f"{skill}: missing SKILL.md for recipe discovery")
        return
    desc = skill_description(skill)
    for wid in kernel_ids:
        if wid not in desc:
            errors.append(f"{skill}: description missing kernel recipe {wid!r}")
    for name in product_names:
        if name in desc:
            errors.append(f"{skill}: description names product recipe {name!r}; keep it in .idev/workflows")


def check_alias_collisions(catalog: dict[str, dict], errors: list[str]) -> None:
    """One id or alias names one effective recipe."""
    owners: dict[str, list[str]] = {}
    for rid, meta in catalog.items():
        for name in dict.fromkeys(meta["aliases"]):
            owners.setdefault(name, []).append(rid)
    for name, rids in sorted(owners.items()):
        if len(rids) > 1:
            where = ", ".join(f"{r} ({catalog[r]['path']})" for r in rids)
            errors.append(f"alias {name!r} names more than one recipe: {where}")


def check_run_follows_recipe(run: dict, path: Path, errors: list[str]) -> None:
    recipe_path = run.get("recipe") if isinstance(run, dict) else None
    if not recipe_path:
        return
    recipe_file = Path(str(recipe_path))
    if not recipe_file.is_file():
        errors.append(f"{path}: recipe {recipe_file} no longer exists")
        return
    recipe = load(recipe_file)
    if not isinstance(recipe, dict):
        return
    if run.get("workflow_id") != recipe.get("id"):
        errors.append(f"{path}: workflow_id {run.get('workflow_id')!r} != recipe id {recipe.get('id')!r}")
    steps, compose_errors = workflow_compose.composed_steps(recipe, workflow_compose.recipes_under(recipe_file))
    errors.extend(f"{path}: {err}" for err in compose_errors)
    want = [(s.get("id"), s.get("kind")) for s in steps if isinstance(s, dict)]
    got = [(s.get("id"), s.get("kind")) for s in run.get("steps") or [] if isinstance(s, dict)]
    if got != want:
        errors.append(f"{path}: steps {got} differ from recipe {recipe_file} {want}")


def check_product_token_rule(errors: list[str]) -> None:
    """Exactly one product token starts a recipe that requires a product name."""
    catalog = {
        "sample-ui": {
            "aliases": ["UI自动化", "sample-ui"],
            "require_product": True,
        },
        "self-evolve-review": {
            "aliases": ["自进化", "self-evolve-review"],
            "require_product": False,
        },
    }
    cases = (
        ("UI自动化 acme", "sample-ui"),
        ("UI自动化", None),
        ("acme beta UI自动化", None),
        ("自进化", "self-evolve-review"),
    )
    for utter, want in cases:
        got = pick_recipe(utter, catalog)
        if got != want:
            errors.append(f"utterance {utter!r} matched {got!r} want {want!r}")


def _tool_ids(recipes_dir: Path | None, errors: list[str]) -> set[str]:
    root = recipes_dir.parent if recipes_dir else Path(__file__).resolve().parent.parent
    path = root / "references" / "tools.yaml"
    if not path.is_file():
        errors.append(f"{path}: missing tool catalog")
        return set()
    return set(check_catalog(load(path), path, errors))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--recipes-dir", type=Path, help="validate capability recipes (idev/workflows)")
    ap.add_argument("--product-recipes", type=Path, help="validate the current product's .idev/workflows")
    ap.add_argument("--run", type=Path, help="validate a run.yaml")
    ap.add_argument("paths", nargs="*", type=Path, help="recipe files")
    args = ap.parse_args()
    errors: list[str] = []
    kernel_files = sorted(args.recipes_dir.glob("*.yaml")) if args.recipes_dir else []
    product_files = sorted(args.product_recipes.glob("*.yaml")) if args.product_recipes else []
    files: list[Path] = list(args.paths) + kernel_files + product_files
    if not files and not args.run:
        ap.error("give --recipes-dir, --run, or recipe paths")
    known = _tool_ids(args.recipes_dir, errors)
    catalog: dict[str, dict] = {}
    kernel_ids: list[str] = []
    kernel_names: set[str] = set()
    product_names: list[str] = []
    for f in files:
        data = load(f)
        check_recipe(data, f, errors)
        check_tool_refs(data, known, f, errors)
        if isinstance(data, dict):
            _, compose_errors = workflow_compose.composed_steps(data, workflow_compose.recipes_under(f))
            errors.extend(compose_errors)
        wid = data.get("id") if isinstance(data, dict) else None
        if isinstance(wid, str) and wid:
            if wid in catalog and f not in product_files:
                errors.append(f"{f}: duplicate recipe id {wid} (also {catalog[wid]['path']})")
            catalog[wid] = {
                "aliases": recipe_aliases(data),
                "require_product": recipe_requires_product(data),
                "path": f,
            }
            if f in kernel_files:
                kernel_ids.append(wid)
                kernel_names.update(recipe_aliases(data))
            elif f in product_files:
                product_names.extend(recipe_aliases(data))
    product_names = [n for n in product_names if n not in kernel_names]
    if args.recipes_dir:
        check_discovery(args.recipes_dir.parent / "SKILL.md", kernel_ids, product_names, errors)
        check_product_token_rule(errors)
    check_alias_collisions(catalog, errors)
    if args.run:
        run = load(args.run)
        check_run(run, args.run, errors)
        check_run_follows_recipe(run, args.run, errors)
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
