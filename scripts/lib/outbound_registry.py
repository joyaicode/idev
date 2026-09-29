#!/usr/bin/env python3
"""Load a product's .idev/handoff.yaml. The kernel registry stays empty."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None


def idev_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def load_registry(root: Path | None = None) -> dict[str, Any]:
    if yaml is None:
        raise SystemExit("outbound registry requires PyYAML (python3 -c 'import yaml')")
    root = root or idev_root_from_here()
    path = root / "handoffs" / "registry.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("%s: registry must be a mapping" % path)
    packs = data.get("packs")
    if packs is None:
        data["packs"] = {}
    elif not isinstance(packs, dict):
        raise SystemExit("%s: packs must be a mapping" % path)
    return data


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(x) for x in value if str(x).strip()]


def _slot_names(slot: Any) -> list[str]:
    if isinstance(slot, str):
        return [slot]
    if isinstance(slot, dict):
        return _as_str_list(slot.get("names") or slot.get("name"))
    return []


def _slot_label(slot: Any, fallback: str) -> str:
    if isinstance(slot, dict):
        label = str(slot.get("label") or "").strip()
        if label:
            return label
    names = _slot_names(slot)
    return names[0] if names else fallback


def pack_slots(pack: dict[str, Any], required: bool) -> list[dict[str, Any]]:
    key = "required" if required else "optional"
    out = []
    for i, slot in enumerate(pack.get(key) or []):
        names = _slot_names(slot)
        if not names:
            continue
        out.append(
            {
                "label": _slot_label(slot, "slot-%s" % i),
                "required": required,
                "names": names,
            }
        )
    return out


def all_skill_names(registry: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    for pack in (registry.get("packs") or {}).values():
        if not isinstance(pack, dict):
            continue
        for slot in pack_slots(pack, True) + pack_slots(pack, False):
            for name in slot["names"]:
                if name not in seen:
                    seen.append(name)
    return seen


def _yml_needle(repo: str, needle: str) -> bool:
    if not needle:
        return False
    try:
        proc = subprocess.run(
            [
                "rg",
                "-q",
                "--glob",
                "application*.yml",
                "--glob",
                "application*.yaml",
                needle,
                repo,
            ],
            check=False,
        )
        return proc.returncode == 0
    except OSError:
        return False


def load_handoff(repo: str) -> dict[str, Any]:
    """Current product's outbound registration.

    Empty unless <repo>/.idev/marker.yaml says marker: idev. A handoff file
    alone does not turn the repo into specialized control.
    """
    if yaml is None or not repo:
        return {}
    from product_marker import is_marked, resolve_extension_repo

    if not is_marked(repo):
        return {}
    dest, err = resolve_extension_repo(repo)
    if err or dest is None:
        return {}
    path = dest / ".idev" / "handoff.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return data if isinstance(data, dict) else {}


def matches_detect(repo: str, detect: dict[str, Any]) -> bool:
    repo = os.path.abspath(repo)
    for fragment in _as_str_list(detect.get("path_contains")):
        if fragment and fragment in repo:
            return True
    for rel in _as_str_list(detect.get("marker_files")):
        if rel and Path(repo, rel).is_file():
            return True
    needle = str(detect.get("yml_needle") or "").strip()
    if needle and _yml_needle(repo, needle):
        return True
    return False


def read_pilot(cfg: Path) -> str:
    if not cfg.is_file():
        return ""
    try:
        loaded = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(loaded, dict):
        return ""
    return str(loaded.get("pilot") or "").strip()


def pack_link_names(registry: dict[str, Any], pack_id: str) -> dict[str, list[str]]:
    pack = (registry.get("packs") or {}).get(pack_id) or {}
    link = pack.get("link_from_repo") or {}
    return {
        "required": _as_str_list(link.get("required")),
        "optional": _as_str_list(link.get("optional")),
    }


def discover_paths(registry: dict[str, Any], home: str = "") -> list[str]:
    """Disk-discovery roots declared by packs (registry-driven, not hardcoded in shell).

    Each pack's ``discover.paths`` entry is joined to ``home`` (or $HOME) unless
    already absolute. Product paths belong in that product's handoff, not here.
    """
    base = home or os.environ.get("HOME") or ""
    out: list[str] = []
    for pack in (registry.get("packs") or {}).values():
        if not isinstance(pack, dict):
            continue
        for p in _as_str_list((pack.get("discover") or {}).get("paths")):
            out.append(p if os.path.isabs(p) else os.path.join(base, p))
    return out


def detect_pack(
    registry: dict[str, Any],
    repo: str = "",
    env_pilot: str = "",
    discovered: bool = False,
    config_pilot: str = "",
    install_pack: str = "",
) -> tuple[str, str]:
    """Return (pack_id, note).

    The session pilot is the current product repo. Its id comes from that
    repo's .idev/handoff.yaml. IDEV_PILOT selects a session only when it
    matches that handoff, or a pack still listed in the kernel registry.
    state/outbound-config.json is an install ledger; it selects a pack only
    when install_pack is passed (--install) and that id is in the kernel
    registry. Empty pack_id means this product has no handoff, or there is
    no current product.
    """
    _ = discovered  # disk presence must not select a pack
    _ = config_pilot  # ledger field must not select the session
    packs = registry.get("packs") or {}
    handoff = load_handoff(repo) if repo else {}
    handoff_id = str(handoff.get("id") or "").strip()
    env_pilot = (env_pilot or os.environ.get("IDEV_PILOT") or "").strip()
    if env_pilot:
        if env_pilot in packs:
            return env_pilot, "IDEV_PILOT=%s" % env_pilot
        if handoff_id and env_pilot == handoff_id:
            return env_pilot, "当前产品 handoff"
        return "", "IDEV_PILOT=%s 未登记，当前产品没有 handoff" % env_pilot
    if repo and handoff:
        return handoff_id or Path(repo).name, "当前产品 handoff"
    if repo:
        for pack_id, pack in packs.items():
            if isinstance(pack, dict) and matches_detect(repo, pack.get("detect") or {}):
                return pack_id, "当前产品 %s" % pack_id
        return "", "当前产品还没有 handoff"
    install_pack = (install_pack or "").strip()
    if install_pack:
        if install_pack in packs:
            return install_pack, "本机安装记录 %s" % install_pack
        return "", "安装记录 %s 未登记，不当成当前产品" % install_pack
    return "", "没有当前产品"


def resolve(
    registry: dict[str, Any],
    repo: str = "",
    env_pilot: str = "",
    discovered: bool = False,
    config_pilot: str = "",
    install_pack: str = "",
) -> dict[str, Any]:
    pack_id, note = detect_pack(
        registry,
        repo=repo,
        env_pilot=env_pilot,
        discovered=discovered,
        config_pilot=config_pilot,
        install_pack=install_pack,
    )
    handoff = load_handoff(repo) if repo else {}
    pack = (registry.get("packs") or {}).get(pack_id) or {}
    if handoff and (not pack or str(handoff.get("id") or "") == pack_id):
        pack = handoff
    slots = []
    if pack_id:
        slots = pack_slots(pack, True) + pack_slots(pack, False)
    names = all_skill_names(registry)
    for slot in pack_slots(handoff, True) + pack_slots(handoff, False):
        for name in slot["names"]:
            if name not in names:
                names.append(name)
    return {
        "pack": pack_id,
        "note": note,
        "slots": slots,
        "all_names": names,
    }


def write_config(
    cfg: Path,
    product_root: str,
    pack_id: str = "",
    registry: dict[str, Any] | None = None,
    force_pack: bool = False,
) -> Path:
    existing: dict[str, Any] = {}
    if cfg.is_file():
        try:
            loaded = json.loads(cfg.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {}
    existing_pilot = str(existing.get("pilot") or "").strip()
    # Install ledger only. Empty pack keeps an already recorded install id.
    # This field does not choose the session's current product.
    requested = (pack_id or existing_pilot).strip()
    if existing_pilot and existing_pilot != requested and not force_pack:
        print(
            "KEEP existing pilot %s (not overwriting with %s)" % (existing_pilot, requested),
            file=sys.stderr,
        )
        return cfg
    registry = registry or load_registry()
    pack_id = requested
    pack = (registry.get("packs") or {}).get(pack_id) or {}
    handoff = load_handoff(product_root)
    if handoff and (not pack or str(handoff.get("id") or "") == pack_id or not pack_id):
        pack = handoff
        if not pack_id:
            pack_id = str(handoff.get("id") or pack_id)
    required = [n for slot in pack_slots(pack, True) for n in slot["names"]]
    optional = [n for slot in pack_slots(pack, False) for n in slot["names"]]
    data = dict(existing)
    data["pilot"] = pack_id
    data["product_root"] = product_root
    data["skills_subdir"] = existing.get("skills_subdir") or ".cursor/skills"
    data["required"] = required or existing.get("required") or []
    data["optional"] = optional or existing.get("optional") or []
    data["link_targets"] = existing.get("link_targets") or [
        "~/.cursor/skills",
        "~/.agents/skills",
    ]
    data["updated_at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cfg


def _cmd_resolve(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else idev_root_from_here()
    registry = load_registry(root)
    install_pack = ""
    if args.install:
        install_pack = read_pilot(root / "state" / "outbound-config.json")
    print(
        json.dumps(
            resolve(
                registry,
                repo=args.repo or "",
                env_pilot=os.environ.get("IDEV_PILOT", ""),
                discovered=args.discovered,
                install_pack=install_pack,
            ),
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_write_config(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else idev_root_from_here()
    cfg = Path(args.cfg) if args.cfg else root / "state" / "outbound-config.json"
    path = write_config(
        cfg,
        args.product_root,
        pack_id=args.pack or "",
        registry=load_registry(root),
        force_pack=args.force_pack,
    )
    print(path)
    return 0


def _cmd_read_pilot(args: argparse.Namespace) -> int:
    if args.cfg:
        cfg = Path(args.cfg)
    else:
        root = Path(args.root) if args.root else idev_root_from_here()
        cfg = root / "state" / "outbound-config.json"
    print(read_pilot(cfg))
    return 0


def _cmd_pack_link(args: argparse.Namespace) -> int:
    pack = (args.pack or "").strip()
    repo = (args.repo or "").strip()
    if repo:
        handoff = load_handoff(repo)
        if handoff:
            hid = str(handoff.get("id") or "").strip()
            if pack and hid and pack != hid:
                print("FAIL: --pack %s does not match product handoff %s" % (pack, hid), file=sys.stderr)
                return 2
            link = handoff.get("link_from_repo") or {}
            print(json.dumps({
                "required": _as_str_list(link.get("required")),
                "optional": _as_str_list(link.get("optional")),
            }, ensure_ascii=False))
            return 0
    if not pack:
        print("FAIL: pack-link requires --pack <id> or --repo with .idev/handoff.yaml", file=sys.stderr)
        return 2
    root = Path(args.root) if args.root else idev_root_from_here()
    print(json.dumps(pack_link_names(load_registry(root), pack), ensure_ascii=False))
    return 0


def _cmd_names(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else idev_root_from_here()
    for name in all_skill_names(load_registry(root)):
        print(name)
    return 0


def _cmd_discover_paths(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else idev_root_from_here()
    for p in discover_paths(load_registry(root)):
        print(p)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("resolve", help="detect pack and emit JSON")
    r.add_argument("--root", default="")
    r.add_argument("--repo", default="")
    r.add_argument("--discovered", action="store_true")
    r.add_argument("--config-pilot", default="", help="accepted, ignored; the session pack is the current product")
    r.add_argument("--ignore-config", action="store_true", help="accepted; session resolve never reads the install ledger")
    r.add_argument("--install", action="store_true", help="use the install ledger instead of the current product")
    r.set_defaults(func=_cmd_resolve)

    w = sub.add_parser("write-config", help="merge outbound-config.json; persist pilot")
    w.add_argument("--root", default="")
    w.add_argument("--cfg", default="")
    w.add_argument("--product-root", required=True)
    w.add_argument("--pack", default="", help="pack id written to the install ledger; empty keeps the recorded id")
    w.add_argument("--force-pack", action="store_true")
    w.set_defaults(func=_cmd_write_config)

    p = sub.add_parser("read-pilot", help="print outbound-config.json pilot")
    p.add_argument("--root", default="")
    p.add_argument("--cfg", default="")
    p.set_defaults(func=_cmd_read_pilot)

    l = sub.add_parser("pack-link", help="names to symlink from a product repo")
    l.add_argument("--root", default="")
    l.add_argument("--pack", default="", help="pack id; optional when --repo has .idev/handoff.yaml")
    l.add_argument("--repo", default="", help="product repo; reads .idev/handoff.yaml")
    l.set_defaults(func=_cmd_pack_link)

    n = sub.add_parser("names", help="all skill names across packs")
    n.add_argument("--root", default="")
    n.set_defaults(func=_cmd_names)

    dp = sub.add_parser("discover-paths", help="disk-discovery roots declared by packs")
    dp.add_argument("--root", default="")
    dp.set_defaults(func=_cmd_discover_paths)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
