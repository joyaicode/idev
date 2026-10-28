#!/usr/bin/env python3
"""Ticket claim index: ingest, query, calibrate, guard.

Truth stays in the source file. claims.yaml is a derived list of sentences
that already appear there. Calibrate exits non-zero when a sentence is
missing or two sentences on the same subject do not fit inside each other.
It does not call lessons.py or realign.py, and it does not score anything.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from doc_home import homes  # noqa: E402
from ticket_yaml import TicketYamlError, load_ticket_yaml  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None

CLAIM_LINE = re.compile(
    r"(?m)^(?:-\s*)?主张:\s*(.+?)\s*\|\s*来源:\s*(\S+)(?:\s*\|\s*主题:\s*(\S+))?\s*$"
)
ARTIFACTS = ("design.md", "req.yaml", "verify/plan.yaml")


def norm(text: str) -> str:
    return " ".join(text.split())


def repo_of(explicit: str) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parents[1]


def ticket_of(repo: Path, feature: str) -> Path:
    return homes(repo, feature)["task"]


def rel(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo).as_posix()
    except ValueError:
        return path.as_posix()


def resolve(repo: Path, ticket: Path, source: str) -> Path | None:
    raw = Path(source)
    if raw.is_absolute() and raw.is_file():
        return raw
    for base in (repo, ticket):
        candidate = (base / source).resolve()
        if candidate.is_file():
            return candidate
    return None


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def contains(path: Path, sentence: str) -> bool:
    return norm(sentence) in norm(read(path))


def load_index(ticket: Path) -> list[dict]:
    path = ticket / "claims.yaml"
    if not path.is_file() or yaml is None:
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    records = data.get("records") or []
    return [r for r in records if isinstance(r, dict)]


def dump_index(ticket: Path, feature: str, records: list[dict]) -> None:
    if yaml is None:
        raise SystemExit("claims: PyYAML is required to write claims.yaml")
    path = ticket / "claims.yaml"
    payload = {"feature": feature, "records": records}
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def slice_records(repo: Path, ticket: Path) -> tuple[list[dict], str]:
    req_path = ticket / "req.yaml"
    base_path = ticket / "baseline.yaml"
    if not req_path.is_file() or not base_path.is_file():
        return [], ""
    try:
        req = load_ticket_yaml(req_path)
    except TicketYamlError as exc:
        return [], str(exc)
    source = rel(repo, base_path)
    records = []
    for slice_ in req.get("slices") or []:
        if not isinstance(slice_, dict):
            continue
        text = str(slice_.get("must") or "").strip()
        subject = str(slice_.get("baseline_item_id") or "").strip()
        if not text or text == "无" or not subject:
            continue
        if not contains(base_path, text):
            return [], "%s: sentence not in source" % source
        records.append({"subject": subject, "text": text, "source": source})
    return records, ""


def line_records(repo: Path, ticket: Path) -> tuple[list[dict], str]:
    found = []
    for name in ARTIFACTS:
        path = ticket / name
        if not path.is_file():
            continue
        for match in CLAIM_LINE.finditer(read(path)):
            text, source, subject = match.group(1).strip(), match.group(2).strip(), match.group(3)
            target = resolve(repo, ticket, source)
            if target is None:
                return [], "%s: source missing" % source
            if not contains(target, text):
                return [], "%s: sentence not in source" % rel(repo, target)
            found.append({
                "subject": (subject or source).strip(),
                "text": text,
                "source": rel(repo, target),
            })
    return found, ""


def assign_ids(records: list[dict]) -> list[dict]:
    numbered = []
    for index, record in enumerate(records, start=1):
        numbered.append({
            "id": "c%d" % index,
            "subject": record["subject"],
            "text": record["text"],
            "source": record["source"],
        })
    return numbered


def ingest(repo: Path, feature: str) -> int:
    ticket = ticket_of(repo, feature)
    if not ticket.is_dir():
        print("claims: no ticket for %s" % feature, file=sys.stderr)
        return 2
    slices, err = slice_records(repo, ticket)
    if err:
        print(err)
        return 1
    lines, err = line_records(repo, ticket)
    if err:
        print(err)
        return 1
    dump_index(ticket, feature, assign_ids(slices + lines))
    print(rel(repo, ticket / "claims.yaml"))
    return 0


def query(repo: Path, feature: str, subject: str) -> int:
    ticket = ticket_of(repo, feature)
    matched = [r for r in load_index(ticket) if r.get("subject") == subject]
    if not matched:
        print("claims: no record for %s" % subject, file=sys.stderr)
        return 1
    for record in matched:
        print("%s %s" % (record.get("id"), record.get("subject")))
        print(record.get("text"))
        print(record.get("source"))
    return 0


def missing_sources(repo: Path, ticket: Path, records: list[dict]) -> list[str]:
    lines = []
    for record in records:
        source = str(record.get("source") or "")
        text = str(record.get("text") or "")
        target = resolve(repo, ticket, source)
        if not source or target is None or not text or not contains(target, text):
            lines.append(source or "(empty source)")
    return lines


def contradictions(records: list[dict]) -> list[str]:
    by_subject: dict[str, list[tuple[str, str]]] = {}
    for record in records:
        text = norm(str(record.get("text") or ""))
        source = str(record.get("source") or "")
        by_subject.setdefault(str(record.get("subject") or ""), []).append((text, source))
    lines = []
    for group in by_subject.values():
        for index, (left, left_source) in enumerate(group):
            for right, right_source in group[index + 1:]:
                if left and right and left not in right and right not in left:
                    lines.extend((left_source, right_source))
    return lines


def problems(repo: Path, ticket: Path, records: list[dict]) -> list[str]:
    seen = []
    for line in missing_sources(repo, ticket, records) + contradictions(records):
        if line not in seen:
            seen.append(line)
    return seen


def calibrate(repo: Path, feature: str) -> int:
    ticket = ticket_of(repo, feature)
    records = load_index(ticket)
    if not (ticket / "claims.yaml").is_file():
        print("claims: no claims.yaml for %s" % feature, file=sys.stderr)
        return 2
    found = problems(repo, ticket, records)
    if not found:
        print("ok")
        return 0
    for line in found:
        print(line)
    return 1


def names(want: Path, sources: list[Path]) -> bool:
    return want in sources


def source_files(repo: Path, ticket: Path, records: list[dict]) -> list[Path]:
    found = []
    for record in records:
        got = resolve(repo, ticket, str(record.get("source") or ""))
        if got is not None:
            found.append(got)
    return found


def guard(repo: Path, feature: str, path: str) -> int:
    ticket = ticket_of(repo, feature)
    want = resolve(repo, ticket, path)
    sources = source_files(repo, ticket, load_index(ticket))
    if want is None or not names(want, sources):
        print("unnamed")
        return 0
    return calibrate(repo, feature)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claims.py")
    parser.add_argument("command", choices=("ingest", "query", "calibrate", "guard"))
    parser.add_argument("--feature", required=True)
    parser.add_argument("--repo", default="")
    parser.add_argument("--subject", default="")
    parser.add_argument("--path", default="")
    args = parser.parse_args(argv)
    repo = repo_of(args.repo)
    if args.command == "ingest":
        return ingest(repo, args.feature)
    if args.command == "query":
        if not args.subject:
            print("claims: query needs --subject", file=sys.stderr)
            return 2
        return query(repo, args.feature, args.subject)
    if args.command == "calibrate":
        return calibrate(repo, args.feature)
    if not args.path:
        print("claims: guard needs --path", file=sys.stderr)
        return 2
    return guard(repo, args.feature, args.path)


if __name__ == "__main__":
    raise SystemExit(main())
