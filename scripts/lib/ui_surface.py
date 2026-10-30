#!/usr/bin/env python3
"""Names and pending state on one screen. No components."""
from __future__ import annotations

ACTION_KEYS = (
    ("on_success", "成功后用户看到什么"),
    ("on_failure", "失败后用户看到什么、能不能重试"),
    ("on_pending", "进行中用户看到什么。点击返回还不是完成"),
)


def action_findings(iid: str, actions: list) -> list[str]:
    out: list[str] = []
    for action in actions:
        out.extend(one_action(iid, action))
    return out


def one_action(iid: str, action: object) -> list[str]:
    if not isinstance(action, dict):
        return [f"items[{iid}].ui.actions 有非 mapping 条目"]
    name = str(action.get("name") or "").strip()
    shown = name or "?"
    out = []
    if not name:
        out.append(f"items[{iid}].ui.actions 缺 name —— 这个动作靠名字被点中")
    for key, why in ACTION_KEYS:
        if not str(action.get(key) or "").strip():
            out.append(f"items[{iid}].ui.actions[{shown}] 缺 {key} —— {why}")
    out.extend(state_text(iid, shown, action))
    return out


def state_text(iid: str, shown: str, action: dict) -> list[str]:
    pending = str(action.get("on_pending") or "").strip()
    success = str(action.get("on_success") or "").strip()
    failure = str(action.get("on_failure") or "").strip()
    out = []
    if pending and pending == success:
        out.append(f"items[{iid}].ui.actions[{shown}] 进行中和成功是同一句")
    if failure and failure == success:
        out.append(f"items[{iid}].ui.actions[{shown}] 失败和成功是同一句")
    return out


def entries(value: object) -> list:
    if isinstance(value, list):
        return value
    return []


def remember(found: dict, key: tuple) -> None:
    if key[2]:
        found[key] = found.get(key, 0) + 1


def collect_names(items: list) -> dict:
    found: dict = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("ui"), dict):
            continue
        ui = item["ui"]
        screen = str(ui.get("screen") or "").strip() or "?"
        for action in entries(ui.get("actions")):
            if isinstance(action, dict):
                name = str(action.get("name") or "").strip()
                scope = str(action.get("scope") or "").strip()
                remember(found, (screen, "动作", name, scope))
        for field in entries(ui.get("fields")):
            if isinstance(field, dict):
                remember(found, (screen, "字段", str(field.get("label") or "").strip()))
    return found


def same_name(items: list) -> list[str]:
    out = []
    for key, count in collect_names(items).items():
        if count > 1:
            out.append(clash(key, count))
    return out


def clash(key: tuple, count: int) -> str:
    screen, kind, text = key[0], key[1], key[2]
    return (
        f"界面「{screen}」的{kind}「{text}」出现了 {count} 次 —— "
        "同一范围里要能单独点中"
    )
