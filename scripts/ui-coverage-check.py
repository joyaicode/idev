#!/usr/bin/env python3
"""Fail if required inventory tokens are missing from e2e sources."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def e2e_blob(e2e: Path) -> str:
    parts: list[str] = []
    for folder in ("flows", "helpers"):
        d = e2e / folder
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if f.suffix in {".ts", ".js", ".cjs"}:
                parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", required=True)
    p.add_argument("--e2e", required=True)
    args = p.parse_args()
    inv = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    blob = e2e_blob(Path(args.e2e))
    missing = []
    required = []
    for tok in inv.get("tokens") or []:
        if not tok.get("required"):
            continue
        required.append(tok)
        needles = [x for x in (tok.get("id"), tok.get("text")) if x]
        if not needles:
            missing.append({"reason": "empty", "token": tok})
            continue
        if not any(n in blob for n in needles):
            missing.append({"needles": needles, "page": tok.get("page"), "wave": tok.get("wave")})
    unassigned = [t for t in required if t.get("required") and not t.get("wave")]
    print(
        f"coverage required={len(required)} missing={len(missing)} unassigned_wave={len(unassigned)}"
    )
    for item in missing[:50]:
        print("MISSING", json.dumps(item, ensure_ascii=False))
    for t in unassigned[:50]:
        print("UNASSIGNED", t.get("id") or t.get("text"), t.get("page"))
    return 1 if missing or unassigned else 0


if __name__ == "__main__":
    raise SystemExit(main())
