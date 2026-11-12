#!/usr/bin/env python3
"""Show, set, clear, or settle idev drive_mode (assisted | auto).

    python3 scripts/drive-mode.py show [--repo <仓>]
    python3 scripts/drive-mode.py set auto [--repo <仓>] [--by <人>]
    python3 scripts/drive-mode.py set assisted [--repo <仓>]
    python3 scripts/drive-mode.py clear [--repo <仓>]
    python3 scripts/drive-mode.py settle [--repo <仓>] [--feature <票>]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import drive_mode  # noqa: E402
import staffing  # noqa: E402
from product_sink import product_repo  # noqa: E402
from roots import kernel_root  # noqa: E402


def repo_of(raw: str) -> Path | None:
    if raw.strip():
        return Path(raw).expanduser().resolve()
    return product_repo()


def cmd_show(args: argparse.Namespace) -> int:
    repo = repo_of(args.repo)
    mode, source = drive_mode.resolve(repo, kernel_root() / "state")
    print(drive_mode.format_line(mode, source))
    if source == "session":
        print("SESSION %s" % drive_mode.session_path(repo, kernel_root() / "state"))
    defaults = drive_mode.defaults_path(repo)
    if defaults is not None:
        print("DEFAULTS %s" % defaults)
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    repo = repo_of(args.repo)
    try:
        path = drive_mode.set_mode(repo, args.mode, by=args.by, kernel_state=kernel_root() / "state")
    except ValueError as exc:
        print("FAIL %s" % exc, file=sys.stderr)
        return 2
    mode, source = drive_mode.resolve(repo, kernel_root() / "state")
    print(drive_mode.format_line(mode, source))
    print("WROTE %s" % path)
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    repo = repo_of(args.repo)
    path = drive_mode.clear(repo, kernel_root() / "state")
    mode, source = drive_mode.resolve(repo, kernel_root() / "state")
    print(drive_mode.format_line(mode, source))
    print("CLEARED %s" % (path if path else "none"))
    return 0


def cmd_settle(args: argparse.Namespace) -> int:
    """Apply auto-mode settlements: staffing solo map, optional verify feedback."""
    repo = repo_of(args.repo)
    mode, source = drive_mode.resolve(repo, kernel_root() / "state")
    print(drive_mode.format_line(mode, source))
    if mode != "auto":
        print("SETTLE skip (drive_mode is not auto)")
        return 0
    if repo is not None:
        staff, written = staffing.auto_solo_under_drive(repo, git_name=staffing.git_user())
        print(staffing.format_line(staff))
        if written is not None:
            print("DRIVE_AUTO staffing=solo %s" % written)
    feature = str(args.feature or "").strip()
    if feature and repo is not None:
        path = drive_mode.settle_verify_feedback(repo, feature)
        if path is not None:
            print("DRIVE_AUTO verify-feedback=none %s" % path)
        debt = drive_mode.settle_scope_debt(repo, feature)
        if debt is not None:
            print("DRIVE_AUTO scope-debt=%s %s" % (
                (_load_scope_decision(debt) or "adopted"), debt,
            ))
    return 0


def _load_scope_decision(path: Path) -> str:
    data = drive_mode._load_yaml(path)  # noqa: SLF001
    debt = data.get("scope_debt") if isinstance(data, dict) else None
    if isinstance(debt, dict):
        return str(debt.get("decision") or "").strip()
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="")
    sub = parser.add_subparsers(dest="cmd", required=True)

    show = sub.add_parser("show", help="print current drive mode")
    show.set_defaults(func=cmd_show)

    sett = sub.add_parser("set", help="set session override")
    sett.add_argument("mode", help="assisted|auto")
    sett.add_argument("--by", default="")
    sett.set_defaults(func=cmd_set)

    clear = sub.add_parser("clear", help="drop session override")
    clear.set_defaults(func=cmd_clear)

    settle = sub.add_parser(
        "settle",
        help="auto-write staffing / verify feedback / scope_debt when drive=auto",
    )
    settle.add_argument(
        "--feature", default="",
        help="also settle verify/feedback.yaml and scope_debt.pending for this ticket",
    )
    settle.set_defaults(func=cmd_settle)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
