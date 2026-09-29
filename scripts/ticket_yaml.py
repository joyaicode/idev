#!/usr/bin/env python3
"""Load deliver / verify / ops ticket YAML. Not a semantic / falsifiability judge."""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None


class TicketYamlError(Exception):
    """File exists but is not a YAML mapping we can gate on."""


def as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def load_ticket_yaml(path: Path) -> dict:
    if yaml is None:
        raise SystemExit("check-feature requires PyYAML (python3 -c 'import yaml')")
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TicketYamlError("%s: %s" % (path, exc)) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TicketYamlError("%s: ticket YAML must be a mapping" % path)
    return data


def scalar(data: dict, key: str) -> str:
    if not isinstance(data, dict):
        return ""
    return as_str(data.get(key))


def entries(data: dict, heading: str) -> list[dict[str, str]]:
    raw = data.get(heading) if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    keys = (
        "id",
        "baseline_item_id",
        "slice_id",
        "status",
        "evidence",
        "must",
        "must_not",
        "dimension",
    )
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = {k: as_str(item.get(k)) for k in keys}
        out.append(row)
    return out


def section_ids(data: dict, heading: str) -> list[str]:
    return [row["id"] for row in entries(data, heading) if row.get("id")]


def field_list(data: dict, heading: str, key: str) -> list[str]:
    raw = data.get(heading) if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    vals: list[str] = []
    for item in raw:
        if isinstance(item, dict) and item.get(key) is not None:
            vals.append(as_str(item.get(key)))
    return vals


def yaml_str_list(data: dict, key: str) -> list[str]:
    raw = data.get(key) if isinstance(data, dict) else None
    if raw is None:
        return []
    if isinstance(raw, list):
        return [as_str(x) for x in raw if as_str(x)]
    text = as_str(raw)
    return [text] if text else []


def nonempty_list(data: dict, key: str) -> bool:
    raw = data.get(key) if isinstance(data, dict) else None
    if raw is None:
        return False
    if isinstance(raw, list):
        return len(raw) > 0
    return bool(as_str(raw))


def signoff_bys(data: dict) -> list[str]:
    if not isinstance(data, dict):
        return []
    vals: list[str] = []
    top = as_str(data.get("by"))
    if top:
        vals.append(top)
    hs = data.get("human_signoff")
    if isinstance(hs, dict):
        who = as_str(hs.get("by"))
        if who:
            vals.append(who)
    elif isinstance(hs, list):
        for item in hs:
            if isinstance(item, dict):
                who = as_str(item.get("by"))
                if who:
                    vals.append(who)
    return vals


def has_open_status(obj: Any) -> bool:
    if isinstance(obj, dict):
        if as_str(obj.get("status")) == "open":
            return True
        return any(has_open_status(v) for v in obj.values())
    if isinstance(obj, list):
        return any(has_open_status(v) for v in obj)
    return False


def collect_hops(obj: Any) -> list[int]:
    found: list[int] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "hop" in node:
                try:
                    found.append(int(node["hop"]))
                except (TypeError, ValueError):
                    pass
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(obj)
    return found


def dimensions_from_surfaces(raw: Any) -> set[str]:
    dims: set[str] = set()
    if not isinstance(raw, list):
        return dims
    for item in raw:
        if isinstance(item, dict):
            dim = as_str(item.get("dimension")).lower()
            if dim:
                dims.add(dim)
    return dims
