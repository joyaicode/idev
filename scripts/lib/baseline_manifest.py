#!/usr/bin/env python3
"""Compute a baseline ManifestRoot matching Go workspace.FromTicket.

Used for E5.5 parity: the same ticket directory must yield the same digest
from Python and from `idev workspace manifest`. Algorithm mirrors
internal/domain/baseline + pkg/canonical (JCS sealed fields + sha256sum root).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

SEALED_FIELDS = ("goal", "non_goal", "items", "boundaries", "details")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _hex(digest: str) -> str:
    return digest[len("sha256:") :] if digest.startswith("sha256:") else digest


def _normalize_text(raw: bytes) -> bytes:
    s = raw.decode("utf-8", errors="replace")
    # NFC
    import unicodedata

    s = unicodedata.normalize("NFC", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in s.split("\n")]
    s = "\n".join(lines).rstrip("\n")
    if not s:
        return b""
    return (s + "\n").encode("utf-8")


def _jcs(obj: object) -> bytes:
    # RFC 8785-ish: json with sorted keys, no whitespace, UTF-8.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _semantic_yaml(doc: dict, fields=SEALED_FIELDS) -> str:
    subset = {f: doc[f] for f in fields if f in doc}
    return _sha256(_jcs(subset))


def _root(lines: list[tuple[str, str]]) -> str:
    rows = sorted(lines, key=lambda x: x[0])
    blob = "".join("%s  %s\n" % (_hex(d), p) for p, d in rows)
    return _sha256(blob.encode("utf-8"))


def _detail_paths(details) -> list[str]:
    out: list[str] = []
    if isinstance(details, list):
        for item in details:
            if isinstance(item, str) and item.strip():
                out.append(item.strip().replace("\\", "/"))
    elif isinstance(details, dict):
        for item in details.values():
            if isinstance(item, str) and item.strip():
                out.append(item.strip().replace("\\", "/"))
    return out


def _resolve(ticket: Path, repo: Path | None, rel: str) -> Path | None:
    p = Path(rel)
    if p.is_absolute() and p.is_file():
        return p
    under_ticket = ticket / rel
    if under_ticket.is_file():
        return under_ticket
    if repo is not None:
        under_repo = repo / rel
        if under_repo.is_file():
            return under_repo
    return None


def manifest_root(ticket: Path, repo: Path | None = None) -> str:
    path = ticket / "baseline.yaml"
    raw = path.read_bytes()
    doc = yaml.safe_load(raw) or {}
    files: list[tuple[str, str]] = [("baseline.yaml", _semantic_yaml(doc))]
    for rel in _detail_paths(doc.get("details")):
        found = _resolve(ticket, repo, rel)
        if found is None:
            continue
        body = found.read_bytes()
        if found.suffix.lower() in (".yaml", ".yml"):
            nested = yaml.safe_load(body) or {}
            if isinstance(nested, dict):
                dig = _semantic_yaml(nested)
            else:
                dig = _sha256(_normalize_text(body))
        else:
            dig = _sha256(_normalize_text(body))
        files.append((rel.replace("\\", "/"), dig))
    return _root(files)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticket", required=True)
    p.add_argument("--repo", default="")
    args = p.parse_args(argv)
    ticket = Path(args.ticket).expanduser().resolve()
    repo = Path(args.repo).expanduser().resolve() if args.repo else None
    print(manifest_root(ticket, repo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
