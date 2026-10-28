"""Extract and validate an idev.delegation-return/1 JSON block from a report.

The structured form is the primary contract (api/schemas/delegation-return.schema.json).
Regex parsing of STATUS/CHANGED lines stays as a one-version fallback when no
JSON block is present.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "api" / "schemas"
RETURN_SCHEMA = SCHEMA_DIR / "delegation-return.schema.json"

# Fenced block the agents.md contract names.
BLOCK = re.compile(
    r"```(?:json)?\s*idev-return\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)
# Also accept a bare trailing JSON object with the schema const.
BARE = re.compile(
    r"\{[^{}]*\"schema\"\s*:\s*\"idev\.delegation-return/1\".*\}",
    re.DOTALL,
)


def extract(raw: str) -> tuple[dict | None, str]:
    """Return (object, error). error is empty on success or when nothing found."""
    if not raw or not str(raw).strip():
        return None, ""
    text = str(raw)
    match = BLOCK.search(text)
    blob = match.group(1).strip() if match else ""
    if not blob:
        match = BARE.search(text)
        blob = match.group(0).strip() if match else ""
    if not blob:
        return None, ""
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        return None, f"idev-return JSON is not parseable: {exc}"
    if not isinstance(data, dict):
        return None, "idev-return JSON must be an object"
    return data, ""


def _validator():
    try:
        import jsonschema
        from jsonschema import RefResolver
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("jsonschema is required to validate delegation returns") from exc
    schema = json.loads(RETURN_SCHEMA.read_text(encoding="utf-8"))
    store = {}
    for path in SCHEMA_DIR.glob("*.schema.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        store[doc.get("$id", path.name)] = doc
        store[path.name] = doc
    resolver = RefResolver(
        base_uri=schema.get("$id", RETURN_SCHEMA.as_uri()),
        referrer=schema,
        store=store,
    )
    return jsonschema.Draft202012Validator(schema, resolver=resolver)


def validate(data: dict) -> list[str]:
    """Schema error messages; empty means the return is well-formed."""
    validator = _validator()
    return [
        f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
        for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    ]


def check_report(raw: str, *, require: bool = False) -> str:
    """PASS / FAIL / WARN line for run_checks['return-schema']."""
    data, err = extract(raw)
    if err:
        return f"FAIL:{err}"
    if data is None:
        if require:
            return (
                "FAIL:回报末尾缺少 ```json idev-return``` 块 —— "
                "按 api/schemas/delegation-return.schema.json 写结构化回报"
            )
        return "WARN:no idev-return JSON; regex fallback still in use"
    errors = validate(data)
    if errors:
        return "FAIL:idev-return schema: " + "; ".join(errors[:3])
    return "PASS"


def apply_as_main(raw: str, structured: dict) -> str:
    """Rewrite STATUS/CHANGED/EVIDENCE lines from the JSON so regex checks see one truth.

    When an idev-return block is present and valid, JSON is the contract; prose
    lines are overwritten (or inserted) from it. Regex stays only as the
    reader for older agents that never emit JSON.
    """
    text = str(raw or "")
    status = structured.get("status")
    if status:
        line = f"STATUS: {status}"
        if STATUS_LINE.search(text):
            text = STATUS_LINE.sub(line, text, count=1)
        else:
            text = line + "\n" + text
    evidence = structured.get("evidence")
    if evidence:
        if isinstance(evidence, list):
            joined = " ".join(str(p) for p in evidence if str(p).strip())
        else:
            joined = str(evidence).strip()
        if joined:
            line = f"EVIDENCE: {joined}"
            if EVIDENCE_LINE.search(text):
                text = EVIDENCE_LINE.sub(line, text, count=1)
            else:
                text = text.rstrip() + "\n" + line + "\n"
    changed = structured.get("changed")
    if isinstance(changed, list):
        joined = " ".join(str(p) for p in changed) if changed else "-"
        line = f"CHANGED: {joined}"
        if CHANGED_LINE.search(text):
            text = CHANGED_LINE.sub(line, text, count=1)
        else:
            text = text.rstrip() + "\n" + line + "\n"
    conclusion = structured.get("conclusion")
    if conclusion and not CONCLUSION_LINE.search(text):
        text = text.rstrip() + f"\nCONCLUSION: {conclusion}\n"
    assumed = structured.get("assumed")
    if assumed:
        line = f"ASSUMED: {assumed}"
        if ASSUMED_LINE.search(text):
            text = ASSUMED_LINE.sub(line, text, count=1)
        else:
            text = text.rstrip() + "\n" + line + "\n"
    return text


# Local mirrors of the line anchors in delegation.py — keep the JSON→prose
# bridge free of a circular import.
STATUS_LINE = re.compile(r"(?mi)^\s*STATUS:\s*.*$")
EVIDENCE_LINE = re.compile(r"(?mi)^\s*EVIDENCE:\s*.*$")
CHANGED_LINE = re.compile(r"(?mi)^\s*CHANGED:\s*.*$")
CONCLUSION_LINE = re.compile(r"(?mi)^\s*CONCLUSION:\s*.*$")
ASSUMED_LINE = re.compile(r"(?mi)^\s*ASSUMED:\s*.*$")
