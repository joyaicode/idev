#!/usr/bin/env python3
"""Every test in scripts/ is reached by selfcheck, and actually runs when it is.

Three ways a test file passes without testing anything, all three found in
this repo on 2026-11-03:

  * nobody runs it here. selfcheck names its tests one by one so each
    failure can say what broke; a file added without that line waits for
    someone to think of `pytest scripts/`. 23 of 47 were in that state, and
    CI's own hand-listed set covered only 3 of those 23 — so 20 had no gate
    on either side.
  * it runs and asserts nothing. `test_lessons_conflict.py` held two real
    TestCase methods and no `unittest.main()`, so `python3 <it>` printed
    nothing and exited 0 — green for as long as anyone cared to look.
  * it runs and skips itself. With no idev binary to build against,
    `test_record_findings` skips 6 of 6 and `test_step_land` 8 of 8 —
    measured, not guessed — while `test_auto_gate`, `test_hooks` and
    `test_idev_bin` lose 1-2 cases each. All five exit 0, and selfcheck ran
    them under `>/dev/null 2>&1`, so a machine without Go reported a pass
    having tested some of it, or none of it, with no way to tell which.

So this checks the roster rather than the code: a file with TestCase
methods must have an entry point, every file is either named by selfcheck
or run right here, and a file that can skip may not have its output muted.
Nothing to remember, which is the point.

    python3 scripts/test-roster.py
    python3 scripts/test-roster.py --list     # the roster, no runs
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import roots  # noqa: E402
import testenv  # noqa: E402

# Entry points that make `python3 <file>` run the cases it holds.
ENTRY_NAMES = ("main", "run_tests")

# Anything that can leave a case unexecuted at runtime.
SKIP_NAMES = ("skip", "skipIf", "skipUnless", "skipTest")

# A test may take a while to build or to walk a tree; it may not hang.
PER_TEST_TIMEOUT = 300

# Where not to look: retired code, recorded state, bytecode.
SKIP_DIRS = frozenset({".git", "__pycache__", "attic", "state", "node_modules"})

# unittest's own summary, which is the only honest source for how many of a
# file's cases actually ran.
RAN_RE = re.compile(r"^Ran (\d+) tests?", re.M)
SKIPPED_RE = re.compile(r"skipped=(\d+)")


def holds_cases(tree: ast.Module) -> bool:
    """True when the file defines TestCase methods, as opposed to being a
    print-and-exit script that reports its own PASS."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
            if name == "TestCase":
                return True
    return False


def has_entry(tree: ast.Module) -> bool:
    """True when running the file runs its cases.

    Both spellings count — `unittest.main()` and a bare `main()` imported
    from it — because what matters is that the cases execute, not how the
    call is written.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in ENTRY_NAMES:
            return True
    return False


def can_skip(tree: ast.Module) -> bool:
    """True when the file can leave cases unexecuted: a skip decorator or a
    skipTest call."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in SKIP_NAMES:
            return True
        if isinstance(node, ast.Name) and node.id in SKIP_NAMES:
            return True
    return False


def muted_by(selfcheck: str, name: str) -> bool:
    """True when selfcheck runs this test with its output thrown away."""
    for line in selfcheck.splitlines():
        if name in line and ">/dev/null" in line:
            return True
    return False


def ran_and_skipped(output: str) -> tuple:
    """(cases that ran, cases skipped) from unittest's summary."""
    ran = RAN_RE.search(output)
    skipped = SKIPPED_RE.search(output)
    return (int(ran.group(1)) if ran else None,
            int(skipped.group(1)) if skipped else 0)



def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", default=None, help="the checkout to inspect")
    parser.add_argument("--list", action="store_true", help="print the roster, run nothing")
    args = parser.parse_args(argv)

    kernel = Path(args.kernel).expanduser().resolve() if args.kernel else roots.kernel_root()
    scripts = kernel / "scripts"
    # The whole tree and both languages, not just scripts/*.py:
    # `scripts/lib/test_doc_home.py` was reached by nothing at all, and the
    # four `test_*.sh` were named in neither selfcheck nor CI. A roster that
    # picks one directory — or one file extension — has the same hole as a
    # roster someone types by hand.
    files = sorted(
        (p for pat in ("test_*.py", "test_*.sh") for p in kernel.rglob(pat)
         if not SKIP_DIRS.intersection(p.parts)),
        key=lambda p: str(p),
    )
    if not files:
        print(f"FAIL no test_*.py or test_*.sh under {kernel}")
        return 1
    try:
        selfcheck = (scripts / "selfcheck.sh").read_text(encoding="utf-8")
    except OSError as exc:
        print(f"FAIL cannot read selfcheck.sh ({exc})")
        return 1

    # selfcheck exports its own IDEV_DATA / IDEV_BIN; pin() leaves that alone
    # and only steps in when a person runs this directly.
    testenv.pin()

    static, mine = [], []
    for path in files:
        named = path.name in selfcheck
        if path.suffix == ".py":
            source = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source)
            except SyntaxError as exc:
                static.append(f"{path.name}: does not parse ({exc.msg})")
                continue
            if holds_cases(tree) and not has_entry(tree):
                static.append(f"{path.name}: has TestCase methods but no unittest.main() entry")
            if named and can_skip(tree) and muted_by(selfcheck, path.name):
                static.append(
                    f"{path.name}: can skip cases, but selfcheck sends its output to /dev/null "
                    f"— use run_test so the skip line stays readable"
                )
        # A shell test gets the reachability half only: there is no unittest
        # summary to read and no TestCase to look for an entry point on.
        if not named:
            mine.append(path)

    print(f"roster: {len(files)} test files, {len(files) - len(mine)} named by selfcheck, "
          f"{len(mine)} run here")
    if args.list:
        for path in mine:
            print(f"  unnamed: {path.name}")
        for problem in static:
            print(f"  FAIL {problem}")
        return 1 if static else 0

    failed = list(static)
    for path in mine:
        argv_run = [sys.executable, str(path)] if path.suffix == ".py" else ["bash", str(path)]
        try:
            proc = subprocess.run(
                argv_run,
                capture_output=True,
                text=True,
                timeout=PER_TEST_TIMEOUT,
                env=os.environ,
                cwd=str(kernel),
            )
        except subprocess.TimeoutExpired:
            failed.append(f"{path.name}: still running after {PER_TEST_TIMEOUT}s")
            continue
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            tail = output.strip().splitlines()
            failed.append(f"{path.name}: exit {proc.returncode} — {tail[-1] if tail else 'no output'}")
            continue
        ran, skipped = ran_and_skipped(output)
        if skipped:
            # Partly skipped is legitimate — an optional dependency is
            # missing — but it has to be readable. Entirely skipped is not a
            # pass; nothing was tested.
            if ran is not None and skipped >= ran:
                failed.append(f"{path.name}: all {ran} cases skipped, so nothing was tested")
            else:
                print(f"     {path.name}: {skipped} of {ran} cases skipped")

    for problem in failed:
        print(f"FAIL {problem}")
    if failed:
        print(f"test roster FAIL ({len(failed)})")
        return 1
    print("test roster PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
