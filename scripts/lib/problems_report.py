#!/usr/bin/env python3
"""Count convention findings in a Qodana or IntelliJ results directory.

Vulnerable-library hits are counted and do not fail this gate.
Exit 0 when a recognized report has no convention findings.
Exit 1 when convention findings remain.
Exit 2 when the directory is not a recognized report (UNPROVEN).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _clean(uri: str) -> str:
    text = (uri or "").replace("file://", "")
    marker = "$PROJECT_DIR$/"
    if marker in text:
        text = text.split(marker, 1)[1]
    return text or uri or "?"


def _vulnerable(title: str, ident: str) -> bool:
    if "易受攻击" in title or "易受攻击" in ident:
        return True
    return "Vulnerable" in ident or "Vulnerable" in title


def _kind(severity: str) -> str:
    sev = (severity or "").strip().upper()
    if sev in {"WEAK WARNING", "INFO", "INFORMATION", "NOTE", "STYLE", "NONE"}:
        return "weak"
    if sev in {"WARNING", "ERROR", "TYPO", "HIGH", "CRITICAL"}:
        return "fail"
    return "skip"


def collect(directory: Path):
    rows: list[str] = []
    vulnerable = 0
    weak = 0
    recognized = False
    if not directory.is_dir():
        return recognized, rows, vulnerable, weak
    for path in sorted(directory.rglob("*.json")):
        if path.name.startswith("."):
            continue
        data = _load(path)
        if not isinstance(data, dict):
            continue
        problems = data.get("problems")
        if isinstance(problems, list):
            recognized = True
            for problem in problems:
                klass = problem.get("problem_class") or {}
                title = klass.get("name") or ""
                ident = klass.get("id") or ""
                if _vulnerable(title, ident):
                    vulnerable += 1
                    continue
                kind = _kind(klass.get("severity") or "")
                if kind == "weak":
                    weak += 1
                elif kind == "fail":
                    rows.append(
                        "%s:%s %s %s"
                        % (
                            _clean(problem.get("file") or ""),
                            problem.get("line"),
                            klass.get("severity") or "",
                            title,
                        )
                    )
            continue
        runs = data.get("runs")
        if not isinstance(runs, list):
            continue
        recognized = True
        for run in runs:
            if not isinstance(run, dict):
                continue
            for result in run.get("results") or []:
                if not isinstance(result, dict):
                    continue
                ident = result.get("ruleId") or ""
                message = result.get("message") or {}
                title = message.get("text") if isinstance(message, dict) else ident
                title = title or ident
                if _vulnerable(title, ident):
                    vulnerable += 1
                    continue
                kind = _kind(result.get("level") or "")
                locations = result.get("locations") or [{}]
                physical = {}
                if locations and isinstance(locations[0], dict):
                    physical = locations[0].get("physicalLocation") or {}
                artifact = physical.get("artifactLocation") or {}
                region = physical.get("region") or {}
                if kind == "weak":
                    weak += 1
                elif kind == "fail":
                    rows.append(
                        "%s:%s %s %s"
                        % (
                            _clean(artifact.get("uri") or ""),
                            region.get("startLine"),
                            result.get("level") or "",
                            title,
                        )
                    )
    return recognized, rows, vulnerable, weak


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--empty-ok",
        action="store_true",
        help="a directory with no report is clean when the scanner itself exited 0",
    )
    parser.add_argument("--label", default="qodana")
    args = parser.parse_args(argv)
    recognized, rows, vulnerable, weak = collect(args.directory)
    if not recognized and not args.empty_ok:
        print("%s: UNPROVEN" % args.label)
        return 2
    print("%s convention: %d" % (args.label, len(rows)))
    print(
        "%s vulnerable-libraries: %d (other tab, not this gate)"
        % (args.label, vulnerable)
    )
    if weak:
        print("%s weak: %d (not this gate)" % (args.label, weak))
    for line in rows[:40]:
        print("  " + line)
    if len(rows) > 40:
        print("  ... %d more" % (len(rows) - 40))
    return 1 if rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
