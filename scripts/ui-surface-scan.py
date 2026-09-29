#!/usr/bin/env python3
"""Scan Vue views for interactive-surface candidates. Does not mark required."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CLASS_KEEP = re.compile(
    r"^(?:btn-|create-|search-|platform-|app-|filter-|op-|more-|name-|id-|"
    r"detail-|access-|field-|agent-|task-|disk-|plan-|risk-|"
    r".*(?:-select|-modal|-panel|-toolbar|-input|-link)$)"
)
CLASS_DROP = re.compile(r"^(ivu-|el-|v-|fa |icon-|col-|row-|span-|mt-|mb-|ml-|mr-)")
CJK = re.compile(r"[\u4e00-\u9fff]")
TEXT = re.compile(r">\s*([^<>{}]{2,30})\s*<")
ATTR = re.compile(
    r"""(?:data-testid|data-test|data-qa|placeholder|title)=["']([^"']{1,80})["']"""
)
CLASS_ATTR = re.compile(r"""class=["']([^"']+)["']""")
LABEL = re.compile(r"""label=["']([^"']{1,40})["']""")
QUOTED_CJK = re.compile(r"""['"]([\u4e00-\u9fff][^'"]{0,28})['"]""")
BARE_HOOK = re.compile(r"""['"]((?:[a-z0-9]+-)+(?:modal|select|panel|toolbar|input|link|btn)[a-z0-9-]*)['"]""")


def template_of(src: str) -> str:
    m = re.search(r"<template\b[^>]*>(.*)</template>", src, re.S | re.I)
    return m.group(1) if m else src


def iter_views(root: Path) -> list[Path]:
    src = root / "src"
    if not src.is_dir():
        return []
    views = [p for p in src.rglob("*.vue") if "views" in p.parts]
    if not views:
        views = list(src.rglob("*.vue"))
    return sorted(views)


def iter_i18n(root: Path) -> list[Path]:
    src = root / "src"
    if not src.is_dir():
        return []
    names = {"zh-cn.js", "zh-cn.json", "zh_CN.js", "zh_CN.json", "zh.js"}
    return sorted(p for p in src.rglob("*") if p.name in names)


def keep_class(name: str) -> bool:
    name = name.strip()
    if not name or CLASS_DROP.match(name):
        return False
    return bool(CLASS_KEEP.match(name))


def keep_text(text: str) -> bool:
    t = " ".join(text.split())
    if len(t) < 2 or len(t) > 30:
        return False
    if t.startswith("{{") or t.startswith("$t") or t in {"div", "span", "template"}:
        return False
    if any(ch in t for ch in "{}()"):
        return False
    return bool(CJK.search(t)) or t.replace("-", "").isalnum()


def scan_file(path: Path, root: Path) -> list[dict]:
    src = path.read_text(encoding="utf-8")
    tpl = template_of(src)
    rel = str(path.relative_to(root))
    out: list[dict] = []
    seen: set[str] = set()

    def add(kind: str, value: str) -> None:
        value = " ".join(value.split())
        if not value or value.startswith("$") or "{{" in value:
            return
        key = f"{kind}:{value}"
        if key in seen:
            return
        seen.add(key)
        out.append(
            {
                "id": value if kind in {"testid", "class"} else "",
                "text": value,
                "kind": kind,
                "page": rel,
                "view": rel,
                "required": False,
                "wave": "",
                "writes": False,
                "api": "",
            }
        )

    for m in ATTR.finditer(tpl):
        add("testid" if "data-" in m.group(0) else "attr", m.group(1))
    for m in LABEL.finditer(tpl):
        if keep_text(m.group(1)):
            add("label", m.group(1))
    for m in TEXT.finditer(tpl):
        if keep_text(m.group(1)):
            add("text", m.group(1))
    for m in CLASS_ATTR.finditer(tpl):
        for cls in m.group(1).split():
            if keep_class(cls):
                add("class", cls)
    for m in QUOTED_CJK.finditer(src):
        if keep_text(m.group(1)):
            add("text", m.group(1))
    for m in BARE_HOOK.finditer(src):
        add("class", m.group(1))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True, help="frontend package root")
    p.add_argument("--out", default="-", help="inventory json path or -")
    p.add_argument("--product", default="")
    args = p.parse_args()
    root = Path(args.root).resolve()
    views = iter_views(root)
    tokens: list[dict] = []
    pages = []
    for view in views:
        pages.append({"id": view.stem, "path": "", "view": str(view.relative_to(root))})
        tokens.extend(scan_file(view, root))
    for loc in iter_i18n(root):
        tokens.extend(scan_file(loc, root))
    doc = {
        "product": args.product or root.name,
        "root": str(root),
        "pages": pages,
        "tokens": tokens,
    }
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(text)
    else:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out} pages={len(pages)} tokens={len(tokens)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
