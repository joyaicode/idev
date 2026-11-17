#!/usr/bin/env python3
"""Run the skill-up suite after the kernel changes.

Not a delivery gate. A missing CLI or engine prints SKIP and exits 0.
A numeric or model judge in evals/ is a FAIL. Reports land in
state/skill-up/latest and do not feed check-feature or promote.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

FORBIDDEN = ("agent_judge", "llm-rubric", "pass_threshold")
SKIP_PREFIXES = (
    ".git/", ".idev/", "state/", "attic/",
    "scripts/docs/notes/", "idev-workspace/",
)
LOOK_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")
LOCK_SECONDS = 1800


def kernel_root() -> Path:
    return Path(__file__).resolve().parents[1]


def surface(name: str) -> bool:
    if not name or name.endswith("/"):
        return False
    return not name.startswith(SKIP_PREFIXES)


def git_text(root: Path, args: list[str]) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True,
    )
    if done.returncode != 0:
        return ""
    return done.stdout


def dirty_names(text: str) -> list[str]:
    names = []
    for line in text.splitlines():
        name = line[3:].strip() if len(line) > 3 and line[2] == " " else line.strip()
        if " -> " in name:
            name = name.split(" -> ", 1)[1]
        if surface(name):
            names.append(name)
    return names


def blob_id(root: Path, name: str) -> str:
    path = root / name
    if not path.is_file():
        return ""
    return git_text(root, ["hash-object", "--", name]).strip()


def fingerprint(root: Path) -> str:
    head = git_text(root, ["rev-parse", "HEAD"]).strip()
    names = dirty_names(git_text(root, ["status", "--porcelain", "-uall"]))
    ids = [f"{name} {blob_id(root, name)}" for name in sorted(set(names))]
    blob = head + "\n" + "\n".join(ids)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def stamp_path(root: Path) -> Path:
    return root / "state" / "skill-up" / "stamp"


def read_stamp(root: Path) -> str:
    path = stamp_path(root)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").splitlines()[0].strip()


def write_stamp(root: Path, digest: str, status: str) -> None:
    path = stamp_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{digest}\n{status}\n", encoding="utf-8")


def changed(root: Path) -> bool:
    return fingerprint(root) != read_stamp(root)


def lock_path(root: Path) -> Path:
    return root / "state" / "skill-up" / "lock"


def lock_held(root: Path) -> bool:
    path = lock_path(root)
    if not path.is_file():
        return False
    return time.time() - path.stat().st_mtime < LOCK_SECONDS


def open_lock(path: Path) -> int:
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return -1


def take_lock(root: Path, digest: str) -> bool:
    path = lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if lock_held(root):
        return False
    if path.exists():
        path.unlink()
    fd = open_lock(path)
    if fd < 0:
        return False
    os.write(fd, digest.encode("utf-8"))
    os.close(fd)
    return True


def release_lock(root: Path) -> None:
    path = lock_path(root)
    if path.is_file():
        path.unlink()


def suite_text(root: Path) -> str:
    base = root / "evals"
    if not base.is_dir():
        return ""
    parts = [p.read_text(encoding="utf-8") for p in sorted(base.rglob("*.yaml"))]
    return "\n".join(parts)


def score_gate(text: str) -> str:
    for word in FORBIDDEN:
        if word in text:
            return word
    return ""


def missing_cases(root: Path, text: str) -> str:
    for name in re.findall(r"(?m)^\s+-\s+(evals/cases/\S+)", text):
        path = root / name
        if not path.is_file():
            return name
        body = path.read_text(encoding="utf-8")
        if "must_contain:" not in body or "agent_judge" in body:
            return name
    return ""


def check_suite(root: Path) -> int:
    text = suite_text(root)
    gate = score_gate(text)
    if gate:
        print(f"skill-up FAIL score gate: {gate}")
        return 1
    missing = missing_cases(root, text)
    if missing:
        print(f"skill-up FAIL missing {missing}")
        return 1
    if "schema_version: v1alpha1" not in text:
        print("skill-up FAIL schema")
        return 1
    print("skill-up PASS suite")
    return 0


def command_ok(name: str) -> bool:
    if shutil.which(name):
        return True
    home = Path.home() / ".local" / "bin" / name
    if home.is_file():
        return True
    return any((Path(root) / name).is_file() for root in LOOK_DIRS)


def skill_up_bin() -> str:
    forced = os.environ.get("SKILL_UP_BIN", "").strip()
    if forced:
        return forced
    found = shutil.which("skill-up")
    if found:
        return found
    home = Path.home() / ".local" / "bin" / "skill-up"
    if home.is_file():
        return str(home)
    return ""


def pick_engine() -> str:
    forced = os.environ.get("SKILL_UP_ENGINE", "").strip()
    if forced:
        return forced
    for cmd, name in (("claude", "claude_code"), ("codex", "codex"), ("qoder", "qodercli"), ("qwen", "qwen_code")):
        if command_ok(cmd):
            return name
    return ""


def plan(root: Path, force: bool) -> str:
    if not force and not changed(root):
        return "skip-unchanged"
    if lock_held(root):
        return "skip-locked"
    if not skill_up_bin():
        return "skip-cli"
    if not pick_engine():
        return "skip-engine"
    return "run"


def child_env() -> dict:
    env = dict(os.environ)
    extra = [*LOOK_DIRS, str(Path.home() / ".local" / "bin")]
    env["PATH"] = os.pathsep.join([*extra, env.get("PATH", "")])
    return env


def run_bin(argv: list[str], root: Path) -> int:
    done = subprocess.run(argv, cwd=str(root), env=child_env())
    return done.returncode


def report_dir(root: Path) -> Path:
    path = root / "state" / "skill-up" / "latest"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_argv(root: Path, binary: str, engine: str) -> list[str]:
    return [
        binary, "run", str(root / "evals" / "eval.yaml"),
        "--engine", engine,
        "--output-dir", str(report_dir(root)),
        "--format", "json",
        "--parallelism", "1",
    ]


def validate_only(root: Path) -> int:
    binary = skill_up_bin()
    code = run_bin([binary, "validate", str(root / "evals" / "eval.yaml")], root)
    print("skill-up PASS validate" if code == 0 else "skill-up FAIL validate")
    return code


def locked_run(root: Path, digest: str) -> int:
    binary = skill_up_bin()
    code = run_bin([binary, "validate", str(root / "evals" / "eval.yaml")], root)
    if code != 0:
        print("skill-up FAIL validate")
        return code
    engine = pick_engine()
    if not engine:
        write_stamp(root, digest, "skip-engine")
        print("skill-up SKIP engine")
        return 0
    code = run_bin(run_argv(root, binary, engine), root)
    status = "pass" if code == 0 else "fail"
    write_stamp(root, digest, status)
    print(f"skill-up {status.upper()} {report_dir(root)}")
    return code


def launch(root: Path, digest: str) -> int:
    if not take_lock(root, digest):
        print("skill-up SKIP locked")
        return 0
    try:
        return locked_run(root, digest)
    finally:
        release_lock(root)


def act(root: Path, args: argparse.Namespace) -> int:
    gate = score_gate(suite_text(root))
    if gate:
        print(f"skill-up FAIL score gate: {gate}")
        return 1
    chosen = plan(root, args.force)
    if args.dry_run:
        print(f"skill-up DRY {chosen}")
        return 0
    if chosen != "run":
        print(f"skill-up SKIP {chosen.split('-', 1)[-1]}")
        return 0
    if args.validate_only:
        return validate_only(root)
    return launch(root, fingerprint(root))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-suite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = kernel_root()
    if args.check_suite:
        return check_suite(root)
    return act(root, args)


if __name__ == "__main__":
    raise SystemExit(main())
