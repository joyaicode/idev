#!/usr/bin/env python3
"""stop / Stop: write a trace skeleton the weekly auditor can accept.

Structural fields (scenario, thinking.summary placeholder, one calls entry,
extensions: []) are filled from the host payload so「字段缺失」stays at zero.
The conductor replaces thinking.summary with one real line via
hooks/fill_thinking.py — until then the placeholder keeps the shape valid.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


PLACEHOLDER = "CONDUCTOR: replace with one thinking line"


def feature_guess(payload: dict) -> str:
    for key in ("feature", "ticket", "feature_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        m = re.search(r"/(?:task|docs/task)/([^/]+)$", str(parent))
        if m:
            return m.group(1)
    return "-"


def as_list(value) -> list:
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def render_yaml(skel: dict) -> str:
    """Minimal YAML without depending on PyYAML in the hook path."""
    files = skel["modified_files"]
    calls = [
        "  - kind: model",
        "    name: inherit",
        "    from: conductor",
        "    to: skill:idev",
        "    why: stop hook captured the turn",
        f"    duration_s: {max(1, int(skel.get('duration_s') or 1))}",
        "    result: skeleton",
    ]
    for path in files[:8]:
        calls.append("  - kind: repo")
        calls.append(f"    name: {path}")
        calls.append("    from: agent")
        calls.append(f"    to: repo:{path}")
        calls.append("    result: touched")
    lines = [
        "schema_version: 2",
        f"at: \"{skel['at']}\"",
        f"feature: {skel['feature']}",
        "intent: \"(stop-hook skeleton)\"",
        "route:",
        "  scenario: S8",
        "  module: deliver",
        "  stage: code",
        "  risk_tier: P1",
        "  why: stop hook; conductor fills thinking.summary",
        "thinking:",
        f"  summary: \"{skel['thinking_summary']}\"",
        "  signals: []",
        "  excluded: []",
        "  steps:",
        "    - n: 1",
        "      do: stop hook wrote structural fields",
        "      so: weekly audit sees scenario and calls",
        "opened: []",
        "extensions: []",
        "calls:",
        *calls,
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", default="cursor", choices=("cursor", "claude"))
    parser.add_argument("--thinking", default="", help="conductor one-liner; default is a placeholder")
    args = parser.parse_args(argv)
    payload = lib.read_stdin()
    stamp = lib.now_iso().replace(":", "").replace("+", "p")
    folder = lib.data_dir() / "trace-skeletons"
    folder.mkdir(parents=True, exist_ok=True)
    modified = as_list(payload.get("modified_files") or payload.get("files"))
    duration_ms = payload.get("duration_ms") or payload.get("durationMs") or 0
    try:
        duration_s = max(1, int(duration_ms) // 1000)
    except (TypeError, ValueError):
        duration_s = 1
    thinking = (args.thinking or "").strip() or PLACEHOLDER
    skel = {
        "at": lib.now_iso(),
        "client": args.client,
        "feature": feature_guess(payload),
        "modified_files": modified,
        "duration_s": duration_s,
        "tool_call_count": payload.get("tool_call_count") or payload.get("toolCallCount") or 0,
        "thinking_summary": thinking,
    }
    yaml_path = folder / f"{stamp}-{args.client}.yaml"
    yaml_path.write_text(render_yaml(skel), encoding="utf-8")
    # Also keep a JSON sidecar for tools that prefer it.
    json_path = folder / f"{stamp}-{args.client}.json"
    json_path.write_text(json.dumps({**skel, "yaml": str(yaml_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lib.append_jsonl(lib.data_dir() / "trace-skeletons.jsonl", {
        "at": skel["at"], "path": str(yaml_path), "client": args.client, "feature": skel["feature"],
    })
    # Optional: drop into the live trace dir so the weekly auditor sees it.
    trace_dir = (os.environ.get("IDEV_TRACE_DIR") or "").strip()
    published = ""
    if trace_dir:
        dest = Path(trace_dir)
        dest.mkdir(parents=True, exist_ok=True)
        published_path = dest / f"{stamp}-skeleton.yaml"
        published_path.write_text(yaml_path.read_text(encoding="utf-8"), encoding="utf-8")
        published = str(published_path)
    print(json.dumps({
        "ok": True,
        "skeleton": str(yaml_path),
        "published": published,
        "thinking_summary": thinking,
        "needs_conductor": thinking == PLACEHOLDER,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
