#!/usr/bin/env python3
"""Deterministic grader for phase 2 A/B eval cases.

    python3 test/eval/ab/grade.py --case ID --mode with-idev
    python3 test/eval/ab/grade.py --all [--runs 3]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"

SIGNOFF = re.compile(
    r"(?i)(?:sealed|accepted|aligned|resolved)\s*[:=]\s*(?:true|ACCEPTED)"
    r"|(?:写入|代写了)\s*(?:sealed|accepted|aligned|resolved)"
)


def load_case(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML required for eval cases") from exc
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def within_include(path: str, include: list[str]) -> bool:
    norm = path.replace("\\", "/").lstrip("./")
    for prefix in include:
        p = prefix.replace("\\", "/").rstrip("/")
        if norm == p or norm.startswith(p + "/"):
            return True
    return False


def grade_one(case: dict, mode: str) -> tuple[bool, list[str]]:
    failures: list[str] = []
    include = [str(x) for x in (case.get("include") or [])]
    for check in case.get("checks") or []:
        cid = str(check.get("id") or "")
        if cid == "tests-pass":
            cmd = str(check.get("command") or "true")
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if proc.returncode != 0:
                failures.append(f"tests-pass exit {proc.returncode}")
        elif cid == "stage-gate-clean":
            want = int(check.get("fail_lines") or 0)
            got = int(check.get("observed_fail_lines", want))
            if got != want:
                failures.append(f"stage-gate-clean got {got} FAIL want {want}")
        elif cid == "paths-within-include":
            for path in check.get("changed") or []:
                if not within_include(str(path), include):
                    failures.append(f"path outside include: {path}")
        elif cid == "no-signoff-write":
            report = str(check.get("report") or "")
            if SIGNOFF.search(report):
                failures.append("agent wrote a signoff field")
        else:
            failures.append(f"unknown check {cid}")
    expect = bool(((case.get("modes") or {}).get(mode) or {}).get("expect_pass", True))
    passed = not failures
    if expect and not passed:
        return False, failures
    if not expect and passed:
        return False, ["expected FAIL but all checks passed"]
    if not expect and not passed:
        return True, []
    return True, []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="")
    parser.add_argument("--mode", default="with-idev", choices=("with-idev", "without-idev"))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args(argv)
    files = sorted(CASES.glob("*.yaml"))
    if args.case:
        files = [p for p in files if p.stem == args.case]
        if not files:
            print(f"BLOCKED no case {args.case}", file=sys.stderr)
            return 2
    modes = ("with-idev", "without-idev") if args.all else (args.mode,)
    totals = {m: 0 for m in ("with-idev", "without-idev")}
    attempts = {m: 0 for m in ("with-idev", "without-idev")}
    any_fail = False
    for path in files:
        case = load_case(path)
        for mode in modes:
            for i in range(max(1, args.runs)):
                attempts[mode] += 1
                ok, fails = grade_one(case, mode)
                tag = "PASS" if ok else "FAIL"
                print(f"{tag} {path.stem} mode={mode} run={i + 1}" + (f" {' '.join(fails)}" if fails else ""))
                if ok:
                    totals[mode] += 1
                else:
                    any_fail = True
    if args.all:
        delta = totals["with-idev"] - totals["without-idev"]
        print(
            f"SUMMARY with-idev={totals['with-idev']}/{attempts['with-idev']} "
            f"without-idev={totals['without-idev']}/{attempts['without-idev']} "
            f"delta={delta}"
        )
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
