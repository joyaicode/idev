#!/usr/bin/env python3
"""Print the Vue skills to open for this repo and stage.

No output means the tree is not Vue. VUE open lines are required reading.
VUE if lines open only when this round touches that subject. VUE MISSING
exits 2.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import vue_skills  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="List vendored Vue skills for a stage")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--stage", default="")
    args = parser.parse_args()
    repo = Path(args.repo).expanduser().resolve()
    rows = vue_skills.lines(repo, args.stage)
    for line in rows:
        print(line)
    if any(line.startswith("VUE MISSING") for line in rows):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
