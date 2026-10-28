"""Who holds which role on this checkout, and what that does to a question.

The conductor asks a person only about the roles that person holds. One
person holding every role is one batch. Several people are several
batches, one per person, never one question per role. A team with no role
map is one assignment question, then a file, then no further guessing.

Policy text lives in references/chat-confirm-signoff.md. This module only
decides the mode from files it can read.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from roots import kernel_root
from workflow_spec import _by_blacklisted

ROLES = ("product", "design", "arch", "dev", "test", "delivery", "ops")

ROLE_LABEL = {
    "product": "产品",
    "design": "设计",
    "arch": "架构",
    "dev": "开发",
    "test": "测试",
    "delivery": "交付",
    "ops": "排障",
}

# A recipe gate type, when it names one. step_confirm falls through to the
# ticket stage. accepted_plan is the implementation review: the plan is not
# its own signature.
GATE_ROLE = {
    "accepted_req": "product",
    "accepted_arch": "arch",
    "accepted_plan": "dev",
    "aligned": "test",
    "resolved": "ops",
    "reopen_baseline": "product",
    "defect_origin": "dev",
}

STAGE_ROLE = {
    "req-review": "product",
    "req": "product",
    "arch": "arch",
    "code": "dev",
    "test": "test",
    "verify-plan": "dev",
    "ops": "ops",
}


@dataclass
class Staffing:
    mode: str  # solo | collaborative | unassigned
    source: str
    people: list[str] = field(default_factory=list)
    roles: dict[str, list[str]] = field(default_factory=dict)
    chat: str = ""
    ask: str = "none"  # none | name | chat | assign

    def holds(self, person: str, role: str) -> bool:
        return any(person.casefold() == name.casefold() for name in self.roles.get(role, []))


def git_user() -> str:
    try:
        done = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (done.stdout or "").strip()


def role_for(gate: str, stage: str) -> str:
    if gate and gate != "step_confirm":
        mapped = GATE_ROLE.get(gate, "")
        if mapped:
            return mapped
    return STAGE_ROLE.get(stage, "")


def resolve(repo: Path | None, kernel: Path | None = None, chat: str = "", git_name: str = "") -> Staffing:
    """The staffing this checkout already records.

    A product `.idev/people.yaml` is the team. It does not pick up the
    kernel operator. The kernel list is the fallback when the product has
    not named anyone. One name holds every role. Two names and no role file
    stay unassigned until someone writes the map.
    """
    kernel = kernel or kernel_root()
    staff_path = _staff_path(repo)
    if staff_path is not None:
        loaded = _from_staff_file(staff_path)
        if loaded is not None:
            return _finish(loaded, chat, git_name)
    names, source = _team_names(repo, kernel)
    if source in ("people-unreadable", "staffing-unreadable"):
        return _finish(Staffing("unassigned", source, names, {}, "", "assign"), chat, git_name)
    distinct = _distinct(names)
    if len(distinct) == 1:
        only = distinct[0]
        return _finish(
            Staffing("solo", source, [only], {role: [only] for role in ROLES}, only, "none"),
            chat,
            git_name,
        )
    if len(distinct) > 1:
        return _finish(Staffing("unassigned", source, distinct, {}, "", "assign"), chat, git_name)
    if source == "product-people":
        return Staffing("unassigned", source, [], {}, "", "name")
    who = git_name.strip()
    if who and not _by_blacklisted(who.casefold()):
        return _finish(
            Staffing("solo", "git-user", [who], {role: [who] for role in ROLES}, who, "none"),
            chat,
            git_name,
        )
    return Staffing("unassigned", "none", [], {}, "", "name")


def signer_refusal(
    repo: Path | None,
    by: str,
    gate: str,
    stage: str,
    kernel: Path | None = None,
    git_name: str | None = None,
) -> str:
    """Why this person cannot sign this gate, or "" when they can.

    Solo does not add a check: the whitelist already names the one person.
    Unassigned refuses every signature until the role map is written.
    Collaborative refuses a person who does not hold the gate's role.
    """
    if git_name is None:
        git_name = git_user()
    staff = resolve(repo, kernel, git_name=git_name)
    return refusal(staff, by, gate, stage)


def refusal(staff: Staffing, by: str, gate: str, stage: str) -> str:
    if staff.mode == "solo":
        return ""
    if staff.mode == "unassigned":
        return (
            "staffing is unassigned; ask the role map once and write it "
            "with staffing.py write before anyone signs"
        )
    role = role_for(gate, stage)
    if not role:
        if not any(by.casefold() == person.casefold() for person in staff.people):
            return f"{by} is not on this staffing"
        return ""
    if staff.holds(by, role):
        return ""
    holders = ", ".join(staff.roles.get(role) or []) or "nobody"
    return f"{ROLE_LABEL[role]}（{role}）由 {holders} 签；{by} 不在这个岗位上"


def status_line(repo: Path | None, chat: str = "", git_name: str | None = None) -> str:
    staff = resolve(repo, chat=chat, git_name=git_user() if git_name is None else git_name)
    return format_line(staff)


def format_line(staff: Staffing) -> str:
    hold, wait = _split(staff)
    return (
        f"STAFFING mode={staff.mode} source={staff.source} chat={staff.chat or '-'} "
        f"ask={staff.ask} people={','.join(staff.people) or '-'} "
        f"hold={hold or '-'} wait={wait or '-'}"
    )


def note_line(staff: Staffing) -> str:
    if staff.ask == "none":
        return ""
    if staff.ask == "name":
        return "NOTE 名单是空的。只问一次名字，并进当前消息。不问岗位。"
    if staff.ask == "chat":
        people = " / ".join(staff.people)
        return f"NOTE 一次问清当前对话的人是 {people} 中的谁。不问岗位。"
    labels = "、".join(ROLE_LABEL[role] for role in ROLES)
    people = "、".join(staff.people) or "（名单空）"
    who = ""
    if not staff.chat and staff.people:
        who = "同时问清当前对话的人是其中谁。"
    return (
        f"NOTE 岗位还没对应到人。只问一次：{labels} 各是谁（人选：{people}）。"
        f"{who}同一人兼任就各岗填同一人，并 staffing.py write --solo <名字>。"
        "写完之前不签字、不再拆开问。"
    )


def write_map(repo: Path, roles: dict[str, list[str]]) -> Path:
    """Write `.idev/staffing.yaml`. Every role is required."""
    missing = [role for role in ROLES if not roles.get(role)]
    if missing:
        raise ValueError("missing roles: " + ", ".join(missing))
    unknown = sorted(set(roles) - set(ROLES))
    if unknown:
        raise ValueError("unknown roles: " + ", ".join(unknown))
    cleaned: dict[str, list[str]] = {}
    for role in ROLES:
        names = _distinct([str(name).strip() for name in roles[role] if str(name).strip()])
        if not names:
            raise ValueError(f"missing roles: {role}")
        for name in names:
            if _by_blacklisted(name.casefold()):
                raise ValueError(f"{name} is not a person")
        cleaned[role] = names
    path = repo / ".idev" / "staffing.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["schema_version: 1", "roles:"]
    for role in ROLES:
        lines.append(f"  {role}:")
        for name in cleaned[role]:
            lines.append(f"    - {_yaml_scalar(name)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _finish(staff: Staffing, chat: str, git_name: str) -> Staffing:
    staff.chat = _pick_chat(staff.people, chat, git_name)
    if staff.mode == "collaborative" and not staff.chat:
        staff.ask = "chat"
    elif staff.mode == "unassigned" and staff.ask == "none":
        staff.ask = "assign"
    return staff


def _pick_chat(people: list[str], chat: str, git_name: str) -> str:
    for candidate in (chat, git_name):
        found = _match(candidate, people)
        if found:
            return found
    distinct = _distinct(people)
    if len(distinct) == 1:
        return distinct[0]
    return ""


def _match(name: str, people: list[str]) -> str:
    for person in people:
        if person.casefold() == name.strip().casefold():
            return person
    return ""


def _split(staff: Staffing) -> tuple[str, str]:
    if staff.mode == "unassigned" or not staff.chat:
        return "", ""
    held: dict[str, list[str]] = {}
    waiting: dict[str, list[str]] = {}
    for role in ROLES:
        names = staff.roles.get(role) or []
        bucket = held if staff.holds(staff.chat, role) else waiting
        for name in names:
            if not staff.holds(staff.chat, role) or name.casefold() == staff.chat.casefold():
                bucket.setdefault(name, []).append(role)
            elif staff.holds(staff.chat, role):
                # The chat user holds it too. Another holder can also sign,
                # and that is not a question waiting on them.
                pass
    return _pack(held), _pack(waiting)


def _pack(groups: dict[str, list[str]]) -> str:
    parts = []
    for name, roles in groups.items():
        ordered = [role for role in ROLES if role in roles]
        parts.append(f"{','.join(ordered)}={name}")
    return " ".join(parts)


def _staff_path(repo: Path | None) -> Path | None:
    if repo is None:
        return None
    path = repo / ".idev" / "staffing.yaml"
    return path if path.is_file() else None


def _team_names(repo: Path | None, kernel: Path) -> tuple[list[str], str]:
    if repo is not None:
        product = repo / ".idev" / "people.yaml"
        loaded = _people_file(product)
        if loaded == "broken":
            return [], "people-unreadable"
        if loaded is not None:
            return loaded, "product-people"
    kernel_people = kernel / "config" / "people.yaml"
    loaded = _people_file(kernel_people)
    if loaded == "broken":
        return [], "people-unreadable"
    if loaded is not None:
        return loaded, "kernel-people"
    return [], "none"


def _from_staff_file(path: Path) -> Staffing | None:
    data = _yaml(path)
    if data == "broken" or not isinstance(data, dict):
        return Staffing("unassigned", "staffing-unreadable", [], {}, "", "assign")
    raw = data.get("roles")
    if not isinstance(raw, dict):
        return Staffing("unassigned", "staffing-incomplete", [], {}, "", "assign")
    roles: dict[str, list[str]] = {}
    people: list[str] = []
    for role in ROLES:
        value = raw.get(role)
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not value:
            return Staffing("unassigned", "staffing-incomplete", _distinct(people), roles, "", "assign")
        names = []
        for item in value:
            name = str(item).strip()
            if not name or _by_blacklisted(name.casefold()):
                return Staffing("unassigned", "staffing-invalid", [], {}, "", "assign")
            names.append(name)
        roles[role] = _distinct(names)
        people.extend(roles[role])
    people = _distinct(people)
    mode = "solo" if len(people) == 1 else "collaborative"
    ask = "none"
    return Staffing(mode, "staffing.yaml", people, roles, "", ask)


def _people_file(path: Path):
    """A list of names, None when the file is absent, or \"broken\"."""
    if not path.is_file():
        return None
    data = _yaml(path)
    if data == "broken":
        return "broken"
    if isinstance(data, dict):
        data = data.get("people") if data.get("people") is not None else data.get("humans")
    if data is None:
        data = []
    if not isinstance(data, list):
        return "broken"
    names = []
    for item in data:
        if isinstance(item, dict):
            item = item.get("name") or item.get("id") or ""
        name = str(item).strip()
        if not name or _by_blacklisted(name.casefold()):
            continue
        names.append(name)
    return names


def _yaml(path: Path):
    try:
        import yaml
    except ImportError:
        return "broken"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return "broken"


def _distinct(names: list[str]) -> list[str]:
    out: list[str] = []
    for name in names:
        if name and not any(name.casefold() == seen.casefold() for seen in out):
            out.append(name)
    return out


def _yaml_scalar(name: str) -> str:
    if name and all(ch.isalnum() or ch in "._-" for ch in name):
        return name
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
