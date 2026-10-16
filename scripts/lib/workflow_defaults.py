#!/usr/bin/env python3
"""Resolve workflow-defaults.yaml on the extension root.

Session checkouts may point at a shared .idev with extension_root. Recipes,
handoff, checks, and this parameter file all live there. A missing file or a
missing key is a preflight block, not a guess.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from product_marker import resolve_extension_repo  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None

# Step kinds that read a command from workflow-defaults.yaml.
try:
    import _generated_kinds as _gen
except ImportError:  # loaded as lib.<module>, with scripts/ on the path
    from lib import _generated_kinds as _gen  # type: ignore[no-redef]

# Generated from registry/kinds.yaml (the `command_key` field).
KIND_COMMANDS = _gen.KIND_COMMANDS


def defaults_file(repo: str | Path) -> tuple[Path | None, str]:
    """Path of workflow-defaults.yaml for this session, or an error."""
    dest, err = resolve_extension_repo(repo)
    if err:
        return None, err
    if dest is None:
        return None, ""
    return dest / ".idev" / "workflow-defaults.yaml", ""


def _lookup(data: dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def required_keys(recipe: dict[str, Any]) -> list[str]:
    """Keys a recipe reads from workflow-defaults. Empty means the file is unused."""
    found: list[str] = []
    seen: set[str] = set()

    def add(key: str) -> None:
        if key and key not in seen:
            seen.add(key)
            found.append(key)

    for param in recipe.get("params") or []:
        if not isinstance(param, dict) or param.get("from") != "product":
            continue
        add(str(param.get("product_key") or param.get("name") or "").strip())
    for step in recipe.get("steps") or []:
        if not isinstance(step, dict):
            continue
        kind = str(step.get("kind") or "").strip()
        add(KIND_COMMANDS.get(kind, ""))
        payload = step.get("with") if isinstance(step.get("with"), dict) else {}
        if kind == "shell.confirmed" and str(payload.get("command") or "").strip() == "status":
            add("commands.status")
    return found


def check_recipe(repo: str | Path, recipe_path: str | Path) -> tuple[int, list[str]]:
    """0 when the recipe does not need defaults, or the extension-root file has every key.

    2 when a required file or key is missing, or extension_root is invalid.
    """
    if yaml is None:
        return 2, ["BLOCKED workflow-defaults: PyYAML is required"]
    path = Path(recipe_path)
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return 2, ["BLOCKED workflow-defaults: cannot read %s: %s" % (path, exc)]
    if not isinstance(loaded, dict):
        return 2, ["BLOCKED workflow-defaults: %s is not a mapping" % path]
    keys = required_keys(loaded)
    if not keys:
        return 0, []
    dest, err = defaults_file(repo)
    if err:
        return 2, ["BLOCKED workflow-defaults: %s" % err]
    if dest is None:
        return 2, ["BLOCKED workflow-defaults: no marked repo for %s" % repo]
    if not dest.is_file():
        return 2, [
            "BLOCKED workflow-defaults: missing %s (read the extension root, not a second copy)"
            % dest
        ]
    try:
        data = yaml.safe_load(dest.read_text(encoding="utf-8"))
    except OSError as exc:
        return 2, ["BLOCKED workflow-defaults: cannot read %s: %s" % (dest, exc)]
    if not isinstance(data, dict):
        return 2, ["BLOCKED workflow-defaults: %s is not a mapping" % dest]
    missing = []
    for key in keys:
        value = _lookup(data, key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(key)
    if missing:
        return 2, [
            "BLOCKED workflow-defaults: %s missing %s" % (dest, ", ".join(missing))
        ]
    return 0, ["OK  defaults %s" % dest]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="session checkout")
    parser.add_argument("--recipe", required=True, help="workflow yaml")
    args = parser.parse_args(argv)
    code, lines = check_recipe(args.repo, args.recipe)
    for line in lines:
        stream = sys.stderr if line.startswith("BLOCKED") else sys.stdout
        print(line, file=stream)
    return code


if __name__ == "__main__":
    sys.exit(main())
