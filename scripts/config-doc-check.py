#!/usr/bin/env python3
"""Fail when extension-config.md drops a key the kernel reads.

The page is the only explanation of marker.yaml, extensions.yaml, and
workflow-defaults.yaml. A new lookup in code has to land there first.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "references" / "extension-config.md"

MARKER_KEYS = ("marker", "id", "evolve", "extension_root")
EXTENSION_KEYS = ("schema_version", "stages", "path", "products")
PRODUCT_KEYS = ("products.<id>.dir", "products.<id>.server")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _need(text: str, key: str, errors: list[str]) -> None:
    if "`%s`" % key not in text:
        errors.append("extension-config.md missing `%s`" % key)


def main() -> int:
    if not PAGE.is_file():
        print("FAIL missing %s" % PAGE, file=sys.stderr)
        return 1
    text = PAGE.read_text(encoding="utf-8")
    errors: list[str] = []
    session = _load("session_context", ROOT / "scripts" / "session-context.py")
    stages = _load("stage_extensions", ROOT / "scripts" / "stage-extensions.py")
    for key in session.DEFAULT_KEYS:
        _need(text, key, errors)
    for key in stages.STAGES:
        _need(text, key, errors)
    for key in MARKER_KEYS + EXTENSION_KEYS + PRODUCT_KEYS:
        _need(text, key, errors)
    if text.count("```yaml") < 3:
        errors.append("extension-config.md needs one yaml example per file")
    if yaml is not None:
        for path in sorted((ROOT / "workflows").glob("*.yaml")):
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                continue
            for param in loaded.get("params") or []:
                if not isinstance(param, dict) or param.get("from") != "product":
                    continue
                key = str(param.get("product_key") or param.get("name") or "").strip()
                if key:
                    _need(text, key, errors)
    if errors:
        for item in errors:
            print("FAIL " + item, file=sys.stderr)
        return 1
    print("config-doc-check PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
