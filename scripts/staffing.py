#!/usr/bin/env python3
"""Show, check, or write who holds which role on the current checkout.

  staffing.py show  [--repo R] [--chat NAME]
  staffing.py check --by NAME [--gate TYPE] [--stage STAGE] [--repo R]
  staffing.py write --repo R --solo NAME
  staffing.py write --repo R --role product=alice --role arch=bob ...

`show` prints one STAFFING line. When the role map is still missing it
also prints one NOTE: ask that once, write the file, and do not sign yet.
Exit 0. `check` exits 2 when this person cannot sign. Policy: references/chat-confirm-signoff.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import staffing as lib  # noqa: E402


def _repo(raw: str) -> Path | None:
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def cmd_show(args: argparse.Namespace) -> int:
    staff = lib.resolve(_repo(args.repo), chat=args.chat, git_name=lib.git_user())
    print(lib.format_line(staff))
    note = lib.note_line(staff)
    if note:
        print(note)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    reason = lib.signer_refusal(_repo(args.repo), args.by, args.gate, args.stage)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    print("OK")
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    if repo is None:
        print("write needs --repo", file=sys.stderr)
        return 2
    try:
        if args.solo:
            roles = {role: [args.solo] for role in lib.ROLES}
        else:
            roles = {role: [] for role in lib.ROLES}
            for item in args.role or []:
                if "=" not in item:
                    raise ValueError(f"--role wants role=name, got {item}")
                role, name = item.split("=", 1)
                role = role.strip()
                if role not in roles:
                    raise ValueError(f"unknown role {role}")
                roles[role].append(name.strip())
        path = lib.write_map(repo, roles)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="role-to-person staffing for one checkout")
    sub = parser.add_subparsers(dest="cmd", required=True)

    show = sub.add_parser("show")
    show.add_argument("--repo", default="", help="product checkout; default is the conductor session")
    show.add_argument("--chat", default="", help="who is in this conversation, if already known")
    show.set_defaults(func=cmd_show)

    check = sub.add_parser("check")
    check.add_argument("--repo", default="")
    check.add_argument("--by", required=True)
    check.add_argument("--gate", default="step_confirm")
    check.add_argument("--stage", default="")
    check.set_defaults(func=cmd_check)

    write = sub.add_parser("write")
    write.add_argument("--repo", required=True)
    write.add_argument("--solo", default="", help="one person holds every role")
    write.add_argument("--role", action="append", default=[], help="role=name, repeat for all seven")
    write.set_defaults(func=cmd_write)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
