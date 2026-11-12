#!/usr/bin/env python3
"""A Python REPL whose transcript is evidence.

    repl.py run  --feature F --step S [--code FILE|-] [--note TEXT]
    repl.py list --feature F
    repl.py show --feature F --step S [--run N]

Why this exists: conventions/evidence.md says analysis and inference are
only propositions until something backs them. Prose reasoning about data is
still prose. A computation whose source and output are both on disk is
evidence — someone else can re-run it and get the same answer, which is
exactly what "带辅助证据" asks for.

So this is not "let the agent run code". It is: when an agent needs a fact
that must be computed (how many cases are unproven, which slices have no
baseline item, what changed between two runs), it writes the computation,
the computation runs here, and the saved transcript becomes the EVIDENCE
path in its report.

    <ticket home>/repl/<step>-<n>.py     the source, verbatim
    <ticket home>/repl/<step>-<n>.out    stdout + stderr + exit status

Both live in the ticket directory, so they travel with the ticket and
execution-clean never touches them.

The preamble gives the snippet IDEV / REPO / TICKET as Path objects and puts
the idev libs on sys.path, so a snippet can use doc_home and safeyaml
instead of re-deriving paths.

## What this deliberately is not

- **Not a sandbox by itself.** The signoff guard below is a static scan —
  a tripwire, not an isolation boundary. `--step rootcause` is the
  exception: that one step is executed by `runsc_probe` (gVisor `runsc`).
  Every other step still runs on the host. Pretending the regex is the
  isolation boundary would be worse than saying so.
- **Not a second test framework.** verify owns red/green (its hard rule 10:
  no second assertion engine). A snippet computes facts; whether a case
  passes is still `verify.run`'s answer.
- **Not a gate.** Nothing here blocks a step. It produces evidence.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402

sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
try:
    import doc_home  # noqa: E402
    import runsc_probe  # noqa: E402
except ImportError:
    print(f"BLOCKED cannot import doc_home from {kind_agents.kernel_root()}", file=sys.stderr)
    raise SystemExit(2) from None

TIMEOUT_S = 120

# Fields only a person may cause to be written. An agent reaching for these
# from a REPL is the one thing this layer must never allow to pass quietly:
# workflow_spec.is_human() rejects agent names at signoff time, and a REPL
# must not become the way around that.
SIGNOFF_FIELDS = ("sealed", "accepted", "aligned", "resolved", "reopen_baseline", "semantic_gate")
# Match the field name near a truthy assignment, with whatever subscript or
# quoting sits between them: `d["aligned"] = True`, `item.accepted = True`,
# `{"sealed": True}`, `set_field("resolved", "true")`. The gap allows for a
# closing bracket and quotes but not a newline, so unrelated lines that
# merely mention the word do not trip it.
_FIELDS = "|".join(SIGNOFF_FIELDS)
SIGNOFF_WRITE = re.compile(
    r"(?is)(?:" + _FIELDS + r")"
    r"""["'\]\s)]{0,6}\s*(?:[:=]|,)\s*"""
    r"""["']?(?:True|true|ACCEPTED|1)\b"""
)
# A REPL has no business writing into the ticket. Catch any write call whose
# line mentions a ticket artifact OR the TICKET path the preamble provides —
# the latter is how a snippet would actually reach one.
TICKET_WRITE = re.compile(
    r"(?im)^(?!\s*#).*"
    r"(?:write_text|writelines|safe_dump|yaml\.dump|open\s*\([^)]*['\"][wa])"
    r".*$"
)
TICKET_TARGET = re.compile(
    r"(?i)TICKET\b|baseline\.ya?ml|deliver\.ya?ml|req\.ya?ml|arch\.ya?ml"
    r"|ops\.ya?ml|plan\.ya?ml|review\.md"
)


def ticket_home(feature: str, repo: Path | None) -> Path:
    base = (repo or Path.cwd()).resolve()
    return doc_home.homes(base, feature)["task"]


def repl_dir(feature: str, repo: Path | None) -> Path:
    return ticket_home(feature, repo) / "repl"


def next_index(target: Path, step: str) -> int:
    n = 1
    while (target / f"{step}-{n}.py").exists():
        n += 1
    return n


def guard(code: str) -> list[str]:
    """Static tripwires. A finding here stops the run before it executes."""
    findings: list[str] = []
    if SIGNOFF_WRITE.search(code):
        findings.append(
            "writes a signoff field (sealed / accepted / aligned / resolved / "
            "reopen_baseline / semantic_gate) — only a person may cause that, "
            "and a REPL must not become the way around workflow_spec.is_human()"
        )
    for line in TICKET_WRITE.findall(code):
        if TICKET_TARGET.search(line):
            findings.append(
                "writes into the ticket — use the agent's own Write/Edit for "
                "artifacts, or the ledger tools (hypothesis.py / "
                f"failure_signature.py) for ledgers: {line.strip()[:70]}"
            )
            break
    return findings


PREAMBLE = '''\
# --- idev repl preamble (generated) ---
import sys
from pathlib import Path

IDEV = Path({idev!r})
REPO = Path({repo!r})
TICKET = Path({ticket!r})
sys.path.insert(0, str(IDEV / "scripts" / "lib"))
# Available from the idev libs: doc_home, safeyaml, kind_agents,
# workflow_spec, product_sink. Import what you need.
# --- end preamble ---

'''


def cmd_run(args: argparse.Namespace) -> int:
    if args.code in (None, "-"):
        code = sys.stdin.read()
    else:
        src = Path(args.code)
        if not src.is_file():
            print(f"BLOCKED no such file: {src}", file=sys.stderr)
            return 2
        code = src.read_text(encoding="utf-8", errors="replace")

    if not code.strip():
        print("BLOCKED empty snippet", file=sys.stderr)
        return 2

    findings = guard(code)
    if findings:
        for f in findings:
            print(f"BLOCKED {f}", file=sys.stderr)
        print("BLOCKED nothing was executed", file=sys.stderr)
        return 2

    repo = args.repo
    home = ticket_home(args.feature, repo)
    if not home.is_dir():
        print(f"BLOCKED no ticket home at {home}", file=sys.stderr)
        return 2

    target = repl_dir(args.feature, repo)
    target.mkdir(parents=True, exist_ok=True)
    n = next_index(target, args.step)
    src_path = target / f"{args.step}-{n}.py"
    out_path = target / f"{args.step}-{n}.out"

    repo_root = (repo or Path.cwd()).resolve()
    kernel = kind_agents.kernel_root()
    sandboxed = args.step == "rootcause"
    if sandboxed:
        idev_p, repo_p, ticket_p = runsc_probe.container_layout(repo_root, home, kernel)
    else:
        idev_p, repo_p, ticket_p = str(kernel), str(repo_root), str(home)
    full = PREAMBLE.format(idev=idev_p, repo=repo_p, ticket=ticket_p) + code
    src_path.write_text(full, encoding="utf-8")

    started = dt.datetime.now().astimezone()
    launched = False
    mounts: tuple[str, ...] = ()
    if sandboxed:
        result = runsc_probe.execute(src_path, repo_root, kernel)
        out, err, rc = result.stdout, result.stderr, result.exit_code
        launched = result.launched
        mounts = result.mounts
    else:
        try:
            proc = subprocess.run(  # noqa: S603 - host repl is the non-rootcause path
                [sys.executable, str(src_path)],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
                cwd=str(repo_root),
            )
            out, err, rc = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            out, err, rc = "", f"timed out after {TIMEOUT_S}s", 124
    elapsed = (dt.datetime.now().astimezone() - started).total_seconds()

    if launched:
        receipt = target / f"{args.step}-{n}.receipt"
        receipt.write_text(runsc_probe.receipt_body(rc, mounts), encoding="utf-8")

    transcript = [
        f"# repl {args.step}-{n}",
        f"# at: {started.isoformat(timespec='seconds')}",
        f"# source: {src_path}",
        f"# exit: {rc}   elapsed: {elapsed:.1f}s",
    ]
    if launched:
        transcript.append("# " + runsc_probe.RUNTIME_MARK)
    if args.note:
        transcript.append(f"# note: {args.note}")
    transcript += ["", "## stdout", out.rstrip() or "(empty)"]
    if err.strip():
        transcript += ["", "## stderr", err.rstrip()]
    out_path.write_text("\n".join(transcript) + "\n", encoding="utf-8")

    print(out.rstrip() or "(no stdout)")
    if err.strip():
        print("--- stderr ---", file=sys.stderr)
        print(err.rstrip(), file=sys.stderr)
    print(f"\nEVIDENCE {out_path}")
    print(f"SOURCE   {src_path}")
    if rc != 0:
        print(f"EXIT     {rc}", file=sys.stderr)
    return 0 if rc == 0 else 1


def cmd_list(args: argparse.Namespace) -> int:
    target = repl_dir(args.feature, args.repo)
    if not target.is_dir():
        print("(no repl runs)")
        return 0
    runs = sorted(target.glob("*.out"))
    if not runs:
        print("(no repl runs)")
        return 0
    for path in runs:
        head = path.read_text(encoding="utf-8", errors="replace").splitlines()
        exit_line = next((l for l in head if l.startswith("# exit:")), "# exit: ?")
        print(f"{path.stem:<24} {exit_line[2:]}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    target = repl_dir(args.feature, args.repo)
    pattern = f"{args.step}-{args.run}.out" if args.run else f"{args.step}-*.out"
    hits = sorted(target.glob(pattern)) if target.is_dir() else []
    if not hits:
        print(f"BLOCKED no transcript for step {args.step}", file=sys.stderr)
        return 2
    path = hits[-1]
    print(path.read_text(encoding="utf-8", errors="replace"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="run a snippet and save the transcript as evidence")
    p.add_argument("--feature", required=True)
    p.add_argument("--step", required=True, help="the workflow step this computation belongs to")
    p.add_argument("--code", help="snippet file, or - for stdin (default)")
    p.add_argument("--note", help="one line on what this computes")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("list", help="list saved runs for a feature")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("show", help="print a saved transcript")
    p.add_argument("--feature", required=True)
    p.add_argument("--step", required=True)
    p.add_argument("--run", type=int)
    p.set_defaults(fn=cmd_show)

    args = parser.parse_args()
    if args.repo is None and os.environ.get("IDEV_PRODUCT_REPO"):
        args.repo = Path(os.environ["IDEV_PRODUCT_REPO"])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
