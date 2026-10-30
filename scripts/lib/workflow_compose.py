"""Expand pipeline references and tool groups into concrete steps.

A recipe step may name a registered tool, a tool group, or another recipe.
`adjust` can skip, reorder, replace the label/with/react of a member, or
extend the list. Expansion is what `workflow.py start` stores and what
`workflow-check` compares a run against. It does not run a tool.
"""
from __future__ import annotations

from pathlib import Path

import safeyaml
from product_sink import kernel_root

NEST_CAP = 8
OVERLAY = {"label", "with", "react"}


def tool_catalog() -> dict:
    path = kernel_root() / "references" / "tools.yaml"
    return safeyaml.mapping(path) or {}


def tool_contract(tool_id: str, catalog: dict | None = None) -> tuple[list[str], list[str]]:
    book = tool_catalog() if catalog is None else catalog
    for tool in book.get("tools") or []:
        if isinstance(tool, dict) and tool.get("id") == tool_id:
            return _names(tool.get("inputs")), _names(tool.get("outputs"))
    return [], []


def _names(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def tool_command(tool_id: str, catalog: dict | None = None) -> str:
    return _tool_text(tool_id, "command", catalog)


def tool_limit(tool_id: str, catalog: dict | None = None) -> str:
    return _tool_text(tool_id, "limit", catalog)


def _tool_text(tool_id: str, field: str, catalog: dict | None) -> str:
    book = tool_catalog() if catalog is None else catalog
    for tool in book.get("tools") or []:
        if isinstance(tool, dict) and tool.get("id") == tool_id:
            return str(tool.get(field) or "")
    return ""


def recipes_under(recipe_path: Path) -> dict[str, dict]:
    """Kernel recipes, then the recipe's own directory so a product id wins."""
    found: dict[str, dict] = {}
    kernel = kernel_root() / "workflows"
    folders = [kernel]
    if recipe_path.parent.resolve() != kernel.resolve():
        folders.append(recipe_path.parent)
    for folder in folders:
        _read_folder(folder, found)
    return found


def composed_steps(recipe: dict, recipes: dict[str, dict], catalog: dict | None = None) -> tuple[list[dict], list[str]]:
    book = tool_catalog() if catalog is None else catalog
    return _compose(recipe, recipes, book, [])


def _read_folder(folder: Path, found: dict[str, dict]) -> None:
    if not folder.is_dir():
        return
    for path in sorted(folder.glob("*.yaml")):
        data = safeyaml.mapping(path)
        if isinstance(data, dict) and isinstance(data.get("id"), str):
            found[str(data["id"])] = data


def _compose(recipe: dict, recipes: dict[str, dict], catalog: dict, stack: list[str]) -> tuple[list[dict], list[str]]:
    rid = str(recipe.get("id") or "")
    if rid in stack or len(stack) >= NEST_CAP:
        return [], [_nest_message(stack, rid)]
    errors: list[str] = []
    out: list[dict] = []
    for i, step in enumerate(recipe.get("steps") or []):
        out.extend(_expand(step, recipes, catalog, stack + [rid], errors, "%s[%d]" % (rid, i)))
    return out, errors


def _expand(step: object, recipes: dict[str, dict], catalog: dict, stack: list[str], errors: list[str], where: str) -> list[dict]:
    if not isinstance(step, dict):
        errors.append("%s not a mapping" % where)
        return []
    if step.get("use"):
        return _expand_use(step, recipes, catalog, stack, errors, where)
    if step.get("tool_group"):
        return _expand_group(step, recipes, catalog, stack, errors, where)
    return [_leaf(step, _commands(catalog), where, errors)]


def _expand_use(step: dict, recipes: dict[str, dict], catalog: dict, stack: list[str], errors: list[str], where: str) -> list[dict]:
    target_id = str(step.get("use") or "")
    target = recipes.get(target_id)
    if not isinstance(target, dict):
        errors.append("%s unknown pipeline %s" % (where, target_id))
        return []
    if target_id in stack or len(stack) >= NEST_CAP:
        errors.append(_nest_message(stack, target_id))
        return []
    return _flatten(step, list(target.get("steps") or []), recipes, catalog, stack + [target_id], errors, where, target_id)


def _expand_group(step: dict, recipes: dict[str, dict], catalog: dict, stack: list[str], errors: list[str], where: str) -> list[dict]:
    name = str(step.get("tool_group") or "")
    members = _groups(catalog).get(name)
    if members is None:
        errors.append("%s unknown tool group %s" % (where, name))
        return []
    tools = _by_id(catalog)
    synthetic = [_tool_step(tid, tools) for tid in members]
    return _flatten(step, synthetic, recipes, catalog, stack, errors, where, name)


def _flatten(step: dict, source: list, recipes: dict[str, dict], catalog: dict, stack: list[str], errors: list[str], where: str, name: str) -> list[dict]:
    before = len(errors)
    chosen = _apply(source, step.get("adjust") or {}, where, errors)
    leaves: list[dict] = []
    for i, piece in enumerate(chosen):
        inner = _expand(piece, recipes, catalog, stack, errors, "%s[%d]" % (where, i))
        leaves.extend(_prefix(step.get("id"), inner))
    if not leaves and len(errors) == before:
        errors.append("%s %s expanded to nothing" % (where, name))
    return leaves


def _tool_step(tool_id: str, tools: dict[str, dict]) -> dict:
    summary = str((tools.get(tool_id) or {}).get("summary") or tool_id)
    return {"id": tool_id, "tool": tool_id, "label": summary}


def _apply(steps: list, adjust: object, where: str, errors: list[str]) -> list:
    spec = adjust if isinstance(adjust, dict) else {}
    skip = set(spec.get("skip") or [])
    replace = spec.get("replace") if isinstance(spec.get("replace"), dict) else {}
    extend = list(spec.get("extend") or [])
    ids = [step.get("id") for step in steps if isinstance(step, dict)]
    _unknown(skip, replace, ids, where, errors)
    kept = [_merge(step, replace.get(step.get("id"))) for step in steps if isinstance(step, dict) and step.get("id") not in skip]
    kept.extend(item for item in extend if isinstance(item, dict))
    _dupes(kept, where, errors)
    if spec.get("order") is None:
        return kept
    return _reorder(kept, spec.get("order"), where, errors)


def _merge(step: dict, patch: object) -> dict:
    merged = dict(step)
    if not isinstance(patch, dict):
        return merged
    for key in OVERLAY:
        if key in patch:
            merged[key] = patch[key]
    return merged


def _unknown(skip: set, replace: dict, ids: list, where: str, errors: list[str]) -> None:
    known = set(ids)
    missing = sorted(str(name) for name in (skip | set(replace)) - known)
    if missing:
        errors.append("%s unknown step %s" % (where, ", ".join(missing)))
    both = sorted(str(name) for name in skip & set(replace))
    if both:
        errors.append("%s skipped and replaced %s" % (where, ", ".join(both)))


def _dupes(steps: list, where: str, errors: list[str]) -> None:
    seen: set[str] = set()
    for step in steps:
        sid = str(step.get("id"))
        if sid in seen:
            errors.append("%s duplicate step %s" % (where, sid))
        seen.add(sid)


def _reorder(steps: list, order: object, where: str, errors: list[str]) -> list:
    if not isinstance(order, list):
        errors.append("%s order must be a list" % where)
        return steps
    by_id = {step.get("id"): step for step in steps}
    if set(order) != set(by_id) or len(order) != len(by_id):
        errors.append("%s order must list each remaining step once" % where)
        return steps
    return [by_id[name] for name in order]


def _prefix(host: object, leaves: list[dict]) -> list[dict]:
    out = []
    for leaf in leaves:
        copied = dict(leaf)
        copied["id"] = "%s--%s" % (host, leaf.get("id"))
        out.append(copied)
    return out


def _leaf(step: dict, commands: dict[str, str], where: str, errors: list[str]) -> dict:
    out = {key: value for key, value in step.items() if key not in ("adjust", "use", "tool_group")}
    tool = out.get("tool")
    if not tool:
        return out
    if tool not in commands:
        errors.append("%s unknown tool %s" % (where, tool))
    out["kind"] = "tool.step"
    return out


def _commands(catalog: dict) -> dict[str, str]:
    found = {}
    for tool in catalog.get("tools") or []:
        if isinstance(tool, dict) and isinstance(tool.get("id"), str):
            found[str(tool["id"])] = str(tool.get("command") or "")
    return found


def _groups(catalog: dict) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for group in catalog.get("groups") or []:
        if isinstance(group, dict) and isinstance(group.get("id"), str):
            tools = group.get("tools") if isinstance(group.get("tools"), list) else []
            found[str(group["id"])] = [str(name) for name in tools]
    return found


def _by_id(catalog: dict) -> dict[str, dict]:
    return {str(tool["id"]): tool for tool in catalog.get("tools") or [] if isinstance(tool, dict) and tool.get("id")}


def _nest_message(stack: list[str], target: str) -> str:
    chain = " -> ".join([*stack, target])
    if target in stack:
        return "pipeline cycle %s" % chain
    return "pipeline nest deeper than %d: %s" % (NEST_CAP, chain)
