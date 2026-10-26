#!/usr/bin/env python3
"""Bounded ReAct joint for one workflow step.

The step's candidate list is the only set of tools an action may name.
The loop stops at max_hops (default 8, hard cap 16). A failed observation
takes on_fail (human, stop, or skip). Running out of hops takes on_exhaust
(human or stop). skip records the hop, stays open, and writes no inbox note.
It does not call a model and it does not change the recipe. A trace that
names this file with `react:` has the hops copied into calls on append.

  react_loop.py open --feature F --step S --candidate ID [--candidate ID ...]
      [--max-hops N] [--on-exhaust human|stop] [--on-fail human|stop|skip] [--dir DIR]
  react_loop.py act --feature F --step S --thought TEXT --action ID [--dir DIR]
  react_loop.py observe --feature F --step S --text TEXT [--fail] [--dir DIR]
  react_loop.py finish --feature F --step S [--dir DIR]
  react_loop.py show --feature F [--step S] [--dir DIR]

Exit 0 means the loop is still open or finished cleanly.
Exit 2 is a refused call (wrong tool, wrong state); the file is unchanged.
Exit 3 is the predefined exit. stdout starts with `EXIT human` or `EXIT stop`.
That also writes an inbox note tagged react-exhausted or react-tool-fail.
`on_fail: skip` prints `SKIP <action>` and exits 0. `show` prints WHY, RESULT,
and TOOL for each hop. It displays the record; it does not run the command.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import safeyaml  # noqa: E402
from product_sink import sink_dir  # noqa: E402

DEFAULT_HOPS = 8
HOP_CAP = 16
EXITS = {"human", "stop"}


class Refused(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def slug(value: str) -> bool:
    return re.fullmatch(r"[a-z][a-z0-9-]*", value or "") is not None


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def loop_path(folder: Path, feature: str, step: str) -> Path:
    return folder / f"{feature}--{step}.yaml"


def place(args: argparse.Namespace) -> Path:
    if args.dir:
        path = Path(args.dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return sink_dir("react", mkdir=True)


def inbox_place(args: argparse.Namespace) -> Path:
    if args.dir:
        path = Path(args.dir) / "inbox"
    else:
        path = sink_dir("inbox", mkdir=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def require_slugs(feature: str, step: str) -> None:
    if slug(feature) and slug(step):
        return
    raise SystemExit("feature and step must be slugs")


def load_open(data: dict) -> None:
    if data.get("schema_version") != 1:
        raise Refused("REFUSE no open loop")
    if data.get("status") != "open":
        raise Refused("REFUSE status %s" % data.get("status"))
    if data.get("pending"):
        raise Refused("REFUSE observe the pending action first")


def call_of(hop: dict, step: str) -> dict:
    action = str(hop.get("action") or "")
    item = {
        "kind": "tool",
        "name": action,
        "from": "react:%s" % step,
        "to": "tool:%s" % action,
        "why": str(hop.get("thought") or ""),
        "result": str(hop.get("observation") or ""),
    }
    command = tool_commands().get(action, "")
    if command:
        item["args"] = command
    if hop.get("duration_s"):
        item["duration_s"] = str(hop["duration_s"])
    return item


def calls_from_file(path: Path) -> list[dict]:
    data = safeyaml.mapping(path)
    if not data or not isinstance(data.get("hops"), list):
        return []
    step = str(data.get("step") or "")
    return [call_of(hop, step) for hop in data["hops"] if isinstance(hop, dict)]


def elapsed(start: str) -> str:
    try:
        began = dt.datetime.fromisoformat(start)
    except ValueError:
        return ""
    return "%.1f" % (dt.datetime.now().astimezone() - began).total_seconds()


def write_inbox(folder: Path, feature: str, step: str, tag: str, note: str) -> None:
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    path = folder / ("react-%s--%s-%s.yaml" % (feature, step, stamp))
    path.write_text(
        safeyaml.dump(
            {
                "schema_version": 1,
                "feature": feature,
                "status": "pending",
                "tags": [tag],
                "note": note,
            }
        ),
        encoding="utf-8",
    )


def take_exit(data: dict, reason: str, detail: str) -> tuple[str, str]:
    failed = reason != "exhausted"
    exit_to = str(data.get("on_fail") or "human") if failed else str(data.get("on_exhaust") or "human")
    if failed and exit_to == "skip":
        return "skip", ""
    data["status"] = "failed" if failed else "exhausted"
    data.pop("pending", None)
    tag = "react-tool-fail" if failed else "react-exhausted"
    note = "%s step %s %s" % (reason, data.get("step"), detail)
    return exit_to, "%s\n%s" % (tag, " ".join(note.split()))


def tool_commands() -> dict[str, str]:
    path = Path(__file__).resolve().parent.parent / "references" / "tools.yaml"
    data = safeyaml.mapping(path)
    commands: dict[str, str] = {}
    for tool in (data or {}).get("tools") or []:
        if isinstance(tool, dict) and tool.get("id") and tool.get("command"):
            commands[str(tool["id"])] = str(tool["command"])
    return commands


def require_registered(names: list[str]) -> None:
    missing = [name for name in names if name not in tool_commands()]
    if missing:
        raise SystemExit("unknown tool %s; add it to references/tools.yaml" % ", ".join(missing))


def act_line(action: str) -> str:
    command = tool_commands().get(action, "")
    line = "ACT pending %s" % action
    if command:
        return "%s\nTOOL %s" % (line, command)
    return line


def cmd_open(args: argparse.Namespace) -> int:
    require_slugs(args.feature, args.step)
    if not args.candidate or any(not slug(name) for name in args.candidate):
        raise SystemExit("candidates must be slugs")
    require_registered(args.candidate)
    if len(set(args.candidate)) != len(args.candidate):
        raise SystemExit("duplicate candidate")
    if args.max_hops < 1 or args.max_hops > HOP_CAP:
        raise SystemExit("max-hops must be from 1 to %d" % HOP_CAP)
    if args.on_exhaust not in EXITS:
        raise SystemExit("on-exhaust must be human or stop")
    if args.on_fail not in {"human", "stop", "skip"}:
        raise SystemExit("on-fail must be human, stop, or skip")
    path = loop_path(place(args), args.feature, args.step)
    if path.is_file():
        print("REFUSE already recorded: %s" % path, file=sys.stderr)
        return 2
    safeyaml.save_locked(path, lambda _: _fresh(args))
    print("OPEN %s" % path)
    return 0


def _fresh(args: argparse.Namespace) -> dict:
    return {
        "schema_version": 1,
        "feature": args.feature,
        "step": args.step,
        "status": "open",
        "candidates": list(args.candidate),
        "max_hops": args.max_hops,
        "on_exhaust": args.on_exhaust,
        "on_fail": args.on_fail,
        "hops": [],
    }


def cmd_act(args: argparse.Namespace) -> int:
    require_slugs(args.feature, args.step)
    if not args.thought.strip():
        raise SystemExit("thought is required")
    path = loop_path(place(args), args.feature, args.step)
    box: dict = {}

    def mutate(data: dict) -> dict:
        _act(data, args, box)
        return data

    try:
        safeyaml.save_locked(path, mutate)
    except Refused as refused:
        print(refused.message, file=sys.stderr)
        return 2
    if "exit" not in box:
        box["line"] = act_line(args.action)
    return _after(args, box)


def _act(data: dict, args: argparse.Namespace, box: dict) -> None:
    load_open(data)
    if args.action not in (data.get("candidates") or []):
        raise Refused("REJECT not a candidate: %s" % args.action)
    if len(data.get("hops") or []) >= int(data.get("max_hops") or DEFAULT_HOPS):
        box["exit"] = take_exit(data, "exhausted", "hops %d" % len(data.get("hops") or []))
        return
    data["pending"] = {"thought": args.thought, "action": args.action, "at": now()}


def cmd_observe(args: argparse.Namespace) -> int:
    require_slugs(args.feature, args.step)
    if not args.text.strip():
        raise SystemExit("text is required")
    path = loop_path(place(args), args.feature, args.step)
    box: dict = {}

    def mutate(data: dict) -> dict:
        _observe(data, args, box)
        return data

    try:
        safeyaml.save_locked(path, mutate)
    except Refused as refused:
        print(refused.message, file=sys.stderr)
        return 2
    return _after(args, box)


def _observe(data: dict, args: argparse.Namespace, box: dict) -> None:
    pending = data.get("pending")
    if data.get("status") != "open" or not isinstance(pending, dict):
        raise Refused("REFUSE no pending action")
    hop = _hop(data, pending, args)
    data["hops"].append(hop)
    data.pop("pending", None)
    if args.fail:
        seen = " ".join(args.text.split())[:80]
        detail = "action %s observation %s" % (hop["action"], seen)
        exit_to, packed = take_exit(data, "tool-fail", detail)
        if exit_to == "skip":
            print_later(box, "SKIP %s" % hop["action"])
            return
        box["exit"] = (exit_to, packed)
        return
    print_later(box, "HOP %d %s ok" % (hop["n"], hop["action"]))


def _hop(data: dict, pending: dict, args: argparse.Namespace) -> dict:
    hop = {
        "n": len(data.get("hops") or []) + 1,
        "thought": pending.get("thought") or "",
        "action": pending.get("action") or "",
        "observation": args.text,
        "ok": not args.fail,
        "at": now(),
    }
    duration = elapsed(str(pending.get("at") or ""))
    if duration:
        hop["duration_s"] = duration
    return hop


def print_later(box: dict, line: str) -> None:
    box["line"] = line


def _after(args: argparse.Namespace, box: dict) -> int:
    if "exit" in box:
        exit_to, packed = box["exit"]
        tag, note = packed.split("\n", 1)
        write_inbox(inbox_place(args), args.feature, args.step, tag, note)
        print("EXIT %s" % exit_to)
        return 3
    if box.get("line"):
        print(box["line"])
    else:
        print("ACT pending %s" % args.action)
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    require_slugs(args.feature, args.step)
    path = loop_path(place(args), args.feature, args.step)

    def mutate(data: dict) -> dict:
        load_open(data)
        data["status"] = "done"
        return data

    try:
        safeyaml.save_locked(path, mutate)
    except Refused as refused:
        print(refused.message, file=sys.stderr)
        return 2
    print("DONE %s" % path)
    return 0


def _hop_line(hop: dict) -> str:
    mark = "ok" if hop.get("ok") else "fail"
    duration = hop.get("duration_s") or "-"
    return "HOP %s %s %s %ss" % (hop.get("n"), hop.get("action"), mark, duration)


def _show_hop(hop: dict) -> None:
    print(_hop_line(hop))
    if hop.get("thought"):
        print("WHY %s" % hop["thought"])
    if hop.get("observation"):
        print("RESULT %s" % hop["observation"])
    command = tool_commands().get(str(hop.get("action") or ""), "")
    if command:
        print("TOOL %s" % command)


def _show_file(path: Path) -> int:
    data = safeyaml.mapping(path)
    if not data:
        print("REFUSE no loop %s" % path.name, file=sys.stderr)
        return 2
    print("PATH %s" % path)
    print("STATUS %s" % data.get("status"))
    for hop in data.get("hops") or []:
        _show_hop(hop)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    if not slug(args.feature) or (args.step and not slug(args.step)):
        raise SystemExit("feature and step must be slugs")
    if args.step:
        return _show_file(loop_path(place(args), args.feature, args.step))
    found = sorted(path for path in place(args).glob("%s--*.yaml" % args.feature) if path.is_file())
    if not found:
        print("NONE")
        return 0
    return max(_show_file(path) for path in found)


def _where(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--feature", required=True)
    parser.add_argument("--step", required=True)
    parser.add_argument("--dir", help="write the loop here instead of the react sink")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    _open_parser(sub)
    _act_parser(sub)
    _observe_parser(sub)
    _where(sub.add_parser("finish"))
    _show_parser(sub)
    return parser


def _show_parser(sub) -> None:
    shown = sub.add_parser("show")
    shown.add_argument("--feature", required=True)
    shown.add_argument("--step", default="")
    shown.add_argument("--dir", help="read the loop here instead of the react sink")


def _open_parser(sub) -> None:
    opened = sub.add_parser("open")
    _where(opened)
    opened.add_argument("--candidate", action="append", required=True)
    opened.add_argument("--max-hops", type=int, default=DEFAULT_HOPS)
    opened.add_argument("--on-exhaust", default="human")
    opened.add_argument("--on-fail", default="human")


def _act_parser(sub) -> None:
    acted = sub.add_parser("act")
    _where(acted)
    acted.add_argument("--thought", required=True)
    acted.add_argument("--action", required=True)


def _observe_parser(sub) -> None:
    observed = sub.add_parser("observe")
    _where(observed)
    observed.add_argument("--text", required=True)
    observed.add_argument("--fail", action="store_true")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    commands = {
        "open": cmd_open,
        "act": cmd_act,
        "observe": cmd_observe,
        "finish": cmd_finish,
        "show": cmd_show,
    }
    return commands[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
