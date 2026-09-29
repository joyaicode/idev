#!/usr/bin/env python3
"""One turn: ticket home, stage pages, recipe, and workflow-defaults keys.

Agents call this when a product session starts or changes stage. It prints
OPEN lines for the deliver stage and for the scenario's extension stage
(S8 also lists s8). Page filter uses --product when the user named one,
otherwise the checkout marker id.

Ticket paths come from doc_home.py. A missing recipe prints RECIPE NONE and
does not fail. A recipe's ``doc:`` page is listed as OPEN. A declared
extension page or recipe doc that is missing exits 2.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from doc_home import homes  # noqa: E402
from product_marker import load_marker, resolve_extension_repo  # noqa: E402
from product_sink import product_repo  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None

SCENARIO_STAGES = {
    "S1": ("req-review",),
    "S2": (),
    "S3": ("verify-plan",),
    "S4": (),
    "S5": (),
    "S6": ("ops",),
    "S7": ("s7",),
    "S8": ("s8",),
}

DEFAULT_KEYS = (
    "coding_root",
    "commands.start",
    "commands.stop",
    "commands.status",
    "commands.approval_off",
    "commands.lifecycle",
    "commands.lint_fix",
)

_STAGE_LINE = re.compile(r"^stage:\s*['\"]?([A-Za-z0-9_-]+)")


def _stage_mod():
    path = Path(__file__).resolve().parent / "stage-extensions.py"
    spec = importlib.util.spec_from_file_location("idev_stage_extensions", path)
    if spec is None or spec.loader is None:
        raise SystemExit("stage-extensions.py missing")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def kernel_root() -> Path:
    return Path(__file__).resolve().parents[1]


def session_repo(raw: str) -> Path | None:
    if raw:
        start = Path(raw).expanduser().resolve()
        found = product_repo(start)
        return found or start
    return product_repo()


def read_stage(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in lines:
        match = _STAGE_LINE.match(line)
        if match:
            return match.group(1)
    return ""


def lookup(data: object, dotted: str) -> str | None:
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    if isinstance(cur, (dict, list)) or cur is None:
        return None
    text = str(cur).strip()
    return text or None


def resolve_recipe(repo: Path, workflow: str) -> Path | None:
    pages, err = resolve_extension_repo(repo)
    if err:
        print("FAIL " + err, file=sys.stderr)
        raise SystemExit(2)
    if pages is not None:
        candidate = pages / ".idev" / "workflows" / ("%s.yaml" % workflow)
        if candidate.is_file():
            return candidate
    kernel_one = kernel_root() / "workflows" / ("%s.yaml" % workflow)
    if kernel_one.is_file():
        return kernel_one
    return None


def recipe_doc(recipe: Path) -> tuple[Path | None, str]:
    """The recipe's ``doc:`` page, relative to the directory holding ``workflows/``."""
    if yaml is None:
        return None, ""
    try:
        data = yaml.safe_load(recipe.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return None, "%s: %s" % (recipe, exc)
    doc = data.get("doc") if isinstance(data, dict) else None
    if not doc:
        return None, ""
    page = recipe.parent.parent / str(doc)
    if not page.is_file():
        return None, "%s: doc %s does not exist" % (recipe, page)
    return page, ""


def list_open(repo: Path) -> int:
    names: set[str] = set()
    for base in (repo / "docs" / "task", repo / ".idev" / "task"):
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if child.is_dir() and (child / "deliver.yaml").is_file():
                names.add(child.name)
    for name in sorted(names):
        deliver = homes(repo, name)["deliver"]
        if not deliver.is_file():
            continue
        stage = read_stage(deliver) or "unknown"
        if stage == "done":
            continue
        print("OPEN_TICKET %s %s %s" % (name, stage, deliver))
    print("OK session-context")
    return 0


def stages_for(scenario: str, stage: str, known: set[str]) -> list[str]:
    chosen: list[str] = []
    if stage in known:
        chosen.append(stage)
    for item in SCENARIO_STAGES.get(scenario, ()):
        if item not in chosen:
            chosen.append(item)
    return chosen


def emit_pages(repo: Path, stages: list[str], product: str) -> int:
    script = Path(__file__).resolve().parent / "stage-extensions.py"
    failed = 0
    for stage in stages:
        cmd = [sys.executable, str(script), stage, "--repo", str(repo)]
        if product:
            cmd.append("--product")
            cmd.append(product)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        for line in (proc.stdout or "").splitlines():
            if line.startswith("OPEN "):
                print(line)
        if proc.returncode != 0:
            failed = proc.returncode
            err = (proc.stderr or proc.stdout or "").strip()
            if err:
                print(err, file=sys.stderr)
    return failed


def load_defaults(pages: Path | None) -> tuple[Path | None, dict]:
    if pages is None or yaml is None:
        return None, {}
    path = pages / ".idev" / "workflow-defaults.yaml"
    if not path.is_file():
        return None, {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return path, {}
    if not isinstance(data, dict):
        return path, {}
    return path, data


def print_defaults(data: dict, path: Path | None, product: str) -> None:
    print("DEFAULTS %s" % (path if path else "NONE"))
    keys = list(DEFAULT_KEYS)
    if product:
        keys.append("products.%s.dir" % product)
        keys.append("products.%s.server" % product)
    for key in keys:
        value = lookup(data, key)
        print("DEFAULT %s %s" % (key, value if value is not None else "MISSING"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="")
    parser.add_argument("--feature", default="")
    parser.add_argument("--scenario", default="", choices=["", *SCENARIO_STAGES])
    parser.add_argument("--stage", default="")
    parser.add_argument("--product", default="")
    parser.add_argument("--workflow", default="")
    parser.add_argument("--list-open", action="store_true")
    parser.add_argument(
        "--print",
        dest="print_key",
        default="",
        choices=["", "recipe", "lint", "ticket", "deliver"],
    )
    args = parser.parse_args(argv)
    repo = session_repo(args.repo)
    if repo is None:
        if args.print_key:
            return 1
        print("OK no current product")
        return 0
    if args.list_open:
        return list_open(repo)
    if args.print_key == "recipe":
        if not args.workflow:
            print("FAIL --workflow is required", file=sys.stderr)
            return 2
        found = resolve_recipe(repo, args.workflow)
        if found is None:
            return 1
        print(found)
        return 0
    if args.print_key == "lint":
        pages, err = resolve_extension_repo(repo)
        if err:
            print("FAIL " + err, file=sys.stderr)
            return 2
        _path, data = load_defaults(pages)
        value = lookup(data, "commands.lint_fix")
        if value:
            print(value)
        return 0

    found_homes = homes(repo, args.feature) if args.feature else None
    stage = args.stage.strip()
    if not stage and found_homes is not None:
        stage = read_stage(found_homes["deliver"])
    if args.print_key == "ticket":
        print("" if found_homes is None else found_homes["task"])
        return 0
    if args.print_key == "deliver":
        print("" if found_homes is None else found_homes["deliver"])
        return 0

    marker = load_marker(repo) or {}
    product = args.product.strip() or str(marker.get("id") or "")
    pages, err = resolve_extension_repo(repo)
    if err:
        print("FAIL " + err, file=sys.stderr)
        return 2
    layout = found_homes["layout"] if found_homes else ""
    print("LAYOUT %s" % (layout or "unknown"))
    print("TICKET %s" % (found_homes["task"] if found_homes else "NONE"))
    print("DELIVER %s" % (found_homes["deliver"] if found_homes else "NONE"))
    print("PLAN %s" % (found_homes["plan"] if found_homes else "NONE"))
    print("SPEC %s" % (found_homes["spec"] if found_homes else "NONE"))
    print("PATROL %s" % (found_homes["patrol"] if found_homes else "NONE"))
    print("STAGE %s" % (stage or "NONE"))
    print("PRODUCT %s" % (product or "NONE"))
    if args.workflow:
        recipe = resolve_recipe(repo, args.workflow)
        print("RECIPE %s" % (recipe if recipe else "NONE"))
        if recipe is not None:
            page, doc_err = recipe_doc(recipe)
            if doc_err:
                print("FAIL " + doc_err, file=sys.stderr)
                return 2
            if page is not None:
                print("OPEN %s" % page)
    else:
        print("RECIPE NONE")
    defaults_path, defaults = load_defaults(pages)
    print_defaults(defaults, defaults_path, product if args.product.strip() else "")
    if pages is None:
        print("OK no idev marker")
        return 0
    known = set(_stage_mod().STAGES)
    chosen = stages_for(args.scenario, stage, known)
    # Pass the session repo. stage-extensions follows extension_root and
    # filters {path, products} with --product, else the session marker id.
    code = emit_pages(repo, chosen, args.product.strip())
    if code != 0:
        print("FAIL session-context")
        return code
    print("OK session-context")
    return 0


if __name__ == "__main__":
    sys.exit(main())
