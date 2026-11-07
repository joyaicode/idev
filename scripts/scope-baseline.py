#!/usr/bin/env python3
"""Stop a lite change when the sealed baseline moved.

Exit 0 when baseline.yaml in HEAD is sealed and the worktree copy matches.
Exit 2 when it is missing, unsealed, or different. Prints SCOPE PASS or SCOPE BLOCKED.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import doc_home  # noqa: E402
import safeyaml  # noqa: E402


def baseline_file(repo: Path, feature: str) -> Path:
    return doc_home.homes(repo, feature)["task"] / "baseline.yaml"


def head_bytes(repo: Path, rel: str) -> bytes | None:
    proc = subprocess.run(
        ["git", "show", f"HEAD:{rel}"], cwd=repo, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def sealed(raw: bytes) -> bool:
    data = safeyaml.mapping_from_text(raw.decode("utf-8", "replace")) or {}
    return data.get("sealed") is True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--feature", required=True)
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    path = baseline_file(repo, args.feature)
    try:
        rel = path.relative_to(repo).as_posix()
    except ValueError:
        print("SCOPE BLOCKED baseline.yaml is outside the repo", file=sys.stderr)
        return 2
    committed = head_bytes(repo, rel)
    if committed is None:
        print(f"SCOPE BLOCKED {rel} is not in HEAD", file=sys.stderr)
        return 2
    if not path.is_file():
        print(f"SCOPE BLOCKED missing {rel}", file=sys.stderr)
        return 2
    if path.read_bytes() != committed:
        print(f"SCOPE BLOCKED {rel} differs from HEAD", file=sys.stderr)
        return 2
    if not sealed(committed):
        print(f"SCOPE BLOCKED {rel} is not sealed", file=sys.stderr)
        return 2
    print(f"SCOPE PASS {rel} sealed goal unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
