"""Run fanout PREP lines that are kernel scripts. Any other line stays with the conductor."""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import kind_agents


def kernel_argv(line: str) -> list[str] | None:
    """The argv when the line is bash of a script inside this kernel, else None."""
    try:
        parts = shlex.split(line)
    except ValueError:
        return None
    if len(parts) < 2 or parts[0] != "bash":
        return None
    script = Path(parts[1]).resolve()
    root = (kind_agents.kernel_root() / "scripts").resolve()
    try:
        script.relative_to(root)
    except ValueError:
        return None
    if not script.is_file():
        return None
    return parts


def run_all(lines: list[str], dest: Path) -> tuple[int, str]:
    """Run every line. Exit 1 still counts as finished: the findings are the scan."""
    chunks: list[str] = []
    code = 0
    for line in lines:
        argv = kernel_argv(line)
        if argv is None:
            return 3, ""
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=180)
        chunks.append(proc.stdout + proc.stderr)
        if proc.returncode not in (0, 1):
            code = proc.returncode or 1
            break
        code = max(code, proc.returncode)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(chunks), encoding="utf-8")
    return code, str(dest)
