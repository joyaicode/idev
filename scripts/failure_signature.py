#!/usr/bin/env python3
"""Failure signatures and the bounded-fix tripwires.

conventions/evidence.md step 5 defines the stop conditions for a fix loop:
the same failure signature three times running, two changes with no real
code delta, or one root cause still red after ~15 minutes. It also defines
the signature itself as

    [exception type] [failing case] [normalized message]

with line numbers, timestamps and temp paths stripped before comparing.
That was all there, but counting it was left to whoever was watching. This
makes it decidable.

    failure_signature.py sig    --log <path|->
    failure_signature.py append --feature F --log <path> --delta N [--result FAIL|PASS]
    failure_signature.py check  --feature F
    failure_signature.py line   --feature F     # the one-line record evidence.md asks for

The ledger is <ticket home>/fix-attempts.yaml. check exits 2 when a
tripwire fires: that is the signal to stop stacking patches and escalate,
not a score.

Normalization is a heuristic and it is deliberately conservative: it strips
what is known to vary per run and keeps everything else, so two different
bugs stay two signatures. Over-normalizing would merge them and hide a real
regression behind an old signature.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402

sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
try:
    import doc_home  # noqa: E402
except ImportError:
    print(f"BLOCKED cannot import doc_home from {kind_agents.kernel_root()}; set IDEV_ROOT", file=sys.stderr)
    raise SystemExit(2) from None

SAME_SIGNATURE_LIMIT = 3
NO_CHANGE_LIMIT = 2
MINUTES_LIMIT = 15

# Things that differ every run and must not enter the signature.
VOLATILE = [
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<ts>"),
    (re.compile(r"\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b"), "<ts>"),
    (re.compile(r"0x[0-9a-fA-F]{4,}"), "<addr>"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<uuid>"),
    (re.compile(r"/(?:tmp|var/folders|private/var)/\S+"), "<tmp>"),
    (re.compile(r"(?:[A-Za-z]:)?[/\\][\w./\\-]*[/\\](?:target|build|node_modules)[/\\]\S*"), "<buildpath>"),
    (re.compile(r"\(([\w$.]+\.(?:java|py|ts|tsx|js|go|kt)):\d+\)"), r"(\1)"),
    (re.compile(r"\b(line|at line)\s+\d+", re.I), r"\1 <n>"),
    (re.compile(r":(\d+):(\d+)\b"), ":<n>:<n>"),
    (re.compile(r"(?<=[\w)\]]):\d+\b"), ":<n>"),
    (re.compile(r"\bpid[= ]\d+", re.I), "pid=<n>"),
    (re.compile(r"\b\d+\s*ms\b"), "<ms>"),
    # Deliberately no global whitespace collapse here: the message fallback
    # below looks for "the line that names the exception", which needs the
    # line structure intact. Collapsing happens on the message alone, at the
    # end, so a stack trace never gets flattened into the signature.
    (re.compile(r"[ \t]+"), " "),
]

EXC = re.compile(
    r"\b((?:[a-zA-Z_][\w]*\.)+[A-Z]\w*(?:Exception|Error|Throwable)"
    r"|[A-Z]\w*(?:Exception|Error)"
    r"|AssertionError|AssertionFailedError)\b"
)
CASE = [
    re.compile(r"(?:FAILED|FAIL|✗|×)\s+([\w./:\[\]-]+)"),
    re.compile(r"\b((?:test|should|it)[\w$]*)\s*\("),
    re.compile(r"\b(test_[\w]+)\b"),
    re.compile(r"\b([\w$]+Test(?:IT)?(?:\.[\w$]+)?)\b"),
]
MESSAGE = [
    re.compile(r"(?:expected|Expected)[:\s].{0,160}"),
    re.compile(r"(?:AssertionError|assert)\b.{0,160}"),
    re.compile(r"(?:Caused by|caused by)[:\s].{0,160}"),
]


def normalize(text: str) -> str:
    out = text
    for pattern, repl in VOLATILE:
        out = pattern.sub(repl, out)
    return out.strip()


def signature(log: str) -> str:
    """[exception type] [failing case] [normalized message]."""
    flat = normalize(log)

    exc = EXC.search(flat)
    exc_part = exc.group(1).split(".")[-1] if exc else "-"

    case_part = "-"
    for pattern in CASE:
        hit = pattern.search(flat)
        if hit:
            case_part = hit.group(1)
            break

    msg_part = "-"
    for pattern in MESSAGE:
        hit = pattern.search(flat)
        if hit:
            msg_part = hit.group(0)
            break
    if msg_part == "-":
        # Fall back to the first line that names the exception, else the first line.
        lines = [ln.strip() for ln in flat.splitlines() if ln.strip()]
        for line in lines:
            if exc and exc.group(1) in line:
                msg_part = line
                break
        else:
            msg_part = lines[0] if lines else "-"

    msg_part = re.sub(r"\s+", " ", msg_part)[:160].strip()
    return f"[{exc_part}] [{case_part}] [{msg_part}]"


def ticket_home(feature: str, repo: Path | None) -> Path:
    base = repo or Path.cwd()
    return doc_home.homes(base.resolve(), feature)["task"]


def ledger_path(feature: str, repo: Path | None) -> Path:
    return ticket_home(feature, repo) / "fix-attempts.yaml"


def load(path: Path, feature: str) -> dict:
    """The ledger, or a fresh one. A broken file starts over rather than crashing.

    Crashing here would be worst-case timing: the ledger is read in the
    middle of a fix loop, which is exactly when nobody has attention to
    spare for a traceback.
    """
    if path.is_file():
        data = safeyaml.mapping(path)
        if data is None:
            print(f"WARN unreadable ledger, starting a fresh one: {path}", file=sys.stderr)
        else:
            data.setdefault("attempts", [])
            if not isinstance(data["attempts"], list):
                print(f"WARN attempts is not a list, reset: {path}", file=sys.stderr)
                data["attempts"] = []
            return data
    return {"schema_version": 1, "feature": feature, "attempts": []}


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def read_log(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    path = Path(arg).expanduser()
    if not path.is_file():
        print(f"BLOCKED no such log: {path}", file=sys.stderr)
        raise SystemExit(2)
    return path.read_text(encoding="utf-8", errors="replace")


def tripwires(attempts: list[dict]) -> list[str]:
    """Which bounded-fix lines are crossed. Empty = keep going."""
    hits: list[str] = []
    red = [a for a in attempts if str(a.get("result", "FAIL")).upper() != "PASS"]
    if not red:
        return hits

    # The run went green at some point: only count the streak after the last PASS.
    last_pass = max((i for i, a in enumerate(attempts) if str(a.get("result", "")).upper() == "PASS"), default=-1)
    streak = attempts[last_pass + 1 :]

    sigs = [a.get("signature", "") for a in streak]
    if len(sigs) >= SAME_SIGNATURE_LIMIT and len(set(sigs[-SAME_SIGNATURE_LIMIT:])) == 1 and sigs[-1]:
        hits.append(f"same signature {SAME_SIGNATURE_LIMIT} times running")

    if len(streak) >= NO_CHANGE_LIMIT:
        tail = streak[-NO_CHANGE_LIMIT:]
        if all(safeyaml.as_int(a.get("delta")) == 0 or a.get("semantic_change") is False for a in tail):
            hits.append(f"{NO_CHANGE_LIMIT} changes running with no effective code change")

    if streak:
        try:
            started = dt.datetime.fromisoformat(str(streak[0].get("at", "")))
            minutes = (dt.datetime.now(started.tzinfo) - started).total_seconds() / 60
            if minutes > MINUTES_LIMIT:
                hits.append(f"one root cause still red after {int(minutes)} minutes (> {MINUTES_LIMIT})")
        except (ValueError, TypeError):
            pass
    return hits


def cmd_sig(args: argparse.Namespace) -> int:
    print(signature(read_log(args.log)))
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    repo = Path(args.repo) if args.repo else None
    path = ledger_path(args.feature, repo)
    data = load(path, args.feature)
    sig = args.signature or signature(read_log(args.log))

    prior = data["attempts"][-1].get("signature") if data["attempts"] else None
    entry = {
        "at": now(),
        "signature": sig,
        "delta": args.delta,
        "semantic_change": (sig != prior) if prior is not None else True,
        "result": args.result,
    }
    if args.note:
        entry["note"] = args.note
    data["attempts"].append(entry)

    # Decide before writing: the per-round record line in evidence.md ends
    # with 继续/升级, and that verdict has to be stored, not recomputed —
    # `line` prints history, where the tripwire state of a past round is not
    # derivable from the current ledger.
    hits = tripwires(data["attempts"])
    entry["decision"] = "升级" if hits else "继续"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safeyaml.dump(data), encoding="utf-8")

    print(f"OK   attempt {len(data['attempts'])} -> {path}")
    print(f"LINE {record_line(entry)}")
    if hits:
        for hit in hits:
            print(f"STOP {hit}", file=sys.stderr)
        print("STOP escalate to a person; do not stack another patch", file=sys.stderr)
        return 2
    return 0


def record_line(entry: dict) -> str:
    """The one-line record evidence.md asks for each fix round."""
    semantic = "是" if entry.get("semantic_change") else "否"
    decision = entry.get("decision", "继续")
    return f"{entry['signature']} | {entry.get('delta', 0)} | {semantic} | {decision}"


def cmd_check(args: argparse.Namespace) -> int:
    repo = Path(args.repo) if args.repo else None
    path = ledger_path(args.feature, repo)
    if not path.is_file():
        print(f"OK   no fix attempts recorded for {args.feature}")
        return 0
    data = load(path, args.feature)
    attempts = data["attempts"]
    hits = tripwires(attempts)
    if hits:
        for hit in hits:
            print(f"STOP {hit}", file=sys.stderr)
        print(f"STOP {len(attempts)} attempts in {path}", file=sys.stderr)
        print("STOP escalate to a person; do not stack another patch", file=sys.stderr)
        return 2
    print(f"OK   {len(attempts)} attempts, no tripwire crossed")
    return 0


def cmd_line(args: argparse.Namespace) -> int:
    repo = Path(args.repo) if args.repo else None
    data = load(ledger_path(args.feature, repo), args.feature)
    if not data["attempts"]:
        print("-")
        return 0
    for entry in data["attempts"]:
        print(record_line(entry))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="product checkout (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sig", help="print the normalized signature of a log")
    p.add_argument("--log", required=True, help="log file, or - for stdin")
    p.set_defaults(fn=cmd_sig)

    p = sub.add_parser("append", help="record one fix round")
    p.add_argument("--feature", required=True)
    p.add_argument("--log", help="log file, or - for stdin")
    p.add_argument("--signature", help="use this signature instead of deriving one")
    p.add_argument("--delta", type=int, default=0, help="lines of code changed this round")
    p.add_argument("--result", default="FAIL", choices=["FAIL", "PASS"])
    p.add_argument("--note")
    p.set_defaults(fn=cmd_append)

    p = sub.add_parser("check", help="exit 2 if a bounded-fix tripwire is crossed")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("line", help="print the per-round record lines")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_line)

    args = parser.parse_args()
    if args.cmd == "append" and not args.log and not args.signature:
        parser.error("append needs --log or --signature")
    if not args.repo and os.environ.get("IDEV_PRODUCT_REPO"):
        args.repo = os.environ["IDEV_PRODUCT_REPO"]
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
