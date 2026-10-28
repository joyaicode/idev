#!/usr/bin/env python3
"""Vendored Vue skills resolve inside the kernel, and only for Vue trees."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import vue_skills  # noqa: E402


def main() -> int:
    failed = 0
    for name in sorted({n for rows in vue_skills.STAGE_SKILLS.values() for _, n in rows}):
        path = vue_skills.skill_file(name)
        if path is None or ROOT / "skills" / "vue" not in path.parents:
            print("FAIL skill not vendored: %s -> %s" % (name, path))
            failed += 1
        else:
            print("ok   vendored %s" % name)
    if vue_skills.is_vue_repo(ROOT):
        print("FAIL kernel tree detected as Vue")
        failed += 1
    else:
        print("ok   kernel is not a Vue repo")
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        (repo / "package.json").write_text('{"dependencies":{"vue":"3.5.0"}}\n', encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "vue-skills.py"), "--repo", str(repo), "--stage", "code"],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print("FAIL vue-skills.py %s %s" % (proc.returncode, proc.stderr))
            failed += 1
        elif "VUE open vue-best-practices " not in proc.stdout:
            print("FAIL code stage missing vue-best-practices")
            failed += 1
        elif str(ROOT / "skills" / "vue" / "vue-best-practices" / "SKILL.md") not in proc.stdout:
            print("FAIL path is not the kernel copy")
            failed += 1
        else:
            print("ok   code stage opens vendored vue-best-practices")
        empty = repo / "empty"
        empty.mkdir()
        quiet = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "vue-skills.py"), "--repo", str(empty), "--stage", "code"],
            check=False,
            capture_output=True,
            text=True,
        )
        if quiet.returncode != 0 or quiet.stdout.strip():
            print("FAIL non-vue repo produced output: %r" % quiet.stdout)
            failed += 1
        else:
            print("ok   non-vue repo is silent")
    if failed:
        print("vue-skills FAIL %s" % failed)
        return 1
    print("vue-skills PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
