#!/usr/bin/env python3
"""Change-window attribution: name the suspects before the first hypothesis.

evidence.md 闭环-1 says 先查变更记录 — 有变更先解释变更. But the window was
hand-filled (`--window`, `--window-source` on hypothesis.py) and the change
list was left to the agent to dig up, which is exactly the step that gets
skipped when a plausible story is already in hand. The only automated diff
attribution was artifact-match's AHEAD branch, which covers one direction of
one relation (source ahead of a named artifact).

This closes that gap by joining the two axes the agent had to join by hand:

    phenomenon window  ×  change record  (×  artifact identity, optional)

    suspect-changes.py --repo DIR --window "2026-11-01T09:00..2026-11-01T11:00" \
        --window-source "告警时间" [--artifact PATH]

Output is a 嫌疑变更清单 — shipped files touched inside the window, each
with its commit and subject, ordered so that files also implicated by the
artifact comparison come first — plus a ready-to-paste `hypothesis.py add`
line per file. The suggestion's evidence string is `commit <7-hex>`, which
lands in hypothesis.py's `change` evidence tier on purpose: a change record
proves something moved, it does not prove why the symptom happened.

**嫌疑不是证据.** This tool nominates, it does not conclude. Every
nominated file still needs a hypothesis, a case, and the red/green loop
before it counts as a root cause (rootcause-guards.md).

Exit: 0 list produced (possibly empty), 2 cannot answer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Reuse, do not copy: NOT_SHIPPED is the single definition of "cannot be in
# a build". artifact-match.py has a hyphen in its name, so it is loaded by
# path in _load_artifact_match() below; the shim is the fallback nobody
# should need.


def _load_artifact_match():
    """Import artifact-match.py by path (hyphen in the name, not a package)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("artifact_match", HERE / "artifact-match.py")
    if spec is None or spec.loader is None:
        raise ImportError("cannot load artifact-match.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The window may only come from one of these. Same rule as hypothesis.py's
# window-without-source: an unsourced window is how unrelated evidence gets
# swept in — widen it a little and anything can be made to fit.
WINDOW_SOURCES = ("问题发生时间", "告警时间", "数据更新时间")


def parse_window(raw: str) -> tuple[str, str]:
    lo, sep, hi = str(raw).partition("..")
    if not sep or not lo.strip() or not hi.strip():
        print("BLOCKED --window must be <from>..<to>", file=sys.stderr)
        raise SystemExit(2)
    return lo.strip(), hi.strip()


def window_commits(repo: Path, lo: str, hi: str) -> list[dict]:
    """Commits inside the window, newest first: sha / date / subject / files."""
    artifact_match = _load_artifact_match()
    rc, out = artifact_match.run(
        ["git", "log", "--since", lo, "--until", hi,
         "--pretty=format:%H%x1f%ad%x1f%s", "--date=iso-strict", "--name-only"],
        repo,
    )
    if rc != 0:
        print(f"BLOCKED git log failed: {out}", file=sys.stderr)
        raise SystemExit(2)
    commits: list[dict] = []
    current: dict | None = None
    for line in out.splitlines():
        if not line.strip():
            continue
        if "\x1f" in line:
            sha, date, subject = line.split("\x1f", 2)
            current = {"sha": sha, "date": date, "subject": subject, "files": []}
            commits.append(current)
        elif current is not None:
            # Only what could actually be inside a build — same filter the
            # AHEAD branch uses, imported not copied.
            if not artifact_match.NOT_SHIPPED.search(line):
                current["files"].append(line)
    return commits


def artifact_files(repo: Path, artifact: Path) -> tuple[str, set[str]]:
    """Files the artifact comparison implicates: (verdict, shipped files)."""
    artifact_match = _load_artifact_match()
    ident = artifact_match.identify(artifact)
    if not (ident.commit or ident.newest_entry):
        return "UNKNOWN", set()
    rc_h, head = artifact_match.run(["git", "rev-parse", "HEAD"], repo)
    if rc_h != 0 or not head:
        return "UNKNOWN", set()
    if ident.commit and head:
        verdict, _detail = artifact_match._commit_verdict(ident, head, repo)
        base = ident.commit
    else:
        verdict, _detail = artifact_match._timestamp_verdict(ident, head, repo)
        base = ""
    if verdict != "AHEAD" or not base:
        return verdict, set()
    rc_f, files = artifact_match.run(
        ["git", "diff", "--name-only", f"{base}..{head}"], repo)
    if rc_f != 0:
        return verdict, set()
    return verdict, {f for f in files.splitlines()
                     if not artifact_match.NOT_SHIPPED.search(f)}


def cmd_main(args: argparse.Namespace) -> int:
    lo, hi = parse_window(args.window)
    if args.window_source not in WINDOW_SOURCES:
        print(f"BLOCKED --window-source 只能是 {' / '.join(WINDOW_SOURCES)} —— "
              "时间窗必须可追溯(rootcause-guards: window-without-source)",
              file=sys.stderr)
        return 2
    repo = args.repo.resolve() if args.repo else Path.cwd()
    if not (repo / ".git").exists():
        print(f"BLOCKED not a git repo: {repo}", file=sys.stderr)
        return 2

    commits = window_commits(repo, lo, hi)
    # file -> [(commit, subject)] — the suspect list is per file, the unit
    # the next step (hypothesis, instrument, read) actually works on.
    by_file: dict[str, list[dict]] = {}
    for c in commits:
        for f in c["files"]:
            by_file.setdefault(f, []).append(c)

    implicated: set[str] = set()
    verdict = ""
    if args.artifact:
        verdict, implicated = artifact_files(repo, args.artifact)

    print(f"# 嫌疑变更清单  窗口 {lo} .. {hi}  (来源: {args.window_source})")
    if verdict:
        print(f"# 产物比对: {verdict}"
              + ("  —— 与产物差异重叠的文件排在最前" if implicated else ""))
    print()
    if not by_file:
        print("窗口内没有会进产物的变更。")
        print("evidence.md 闭环-1:无变更再查云资源状态/事件与容器异常日志。")
        return 0

    ordered = sorted(by_file, key=lambda f: (f not in implicated, f))
    for f in ordered:
        hits = by_file[f]
        shas = ", ".join(c["sha"][:7] for c in hits)
        mark = "  *产物差异重叠*" if f in implicated else ""
        print(f"  {f}  [{shas}]{mark}")
        for c in hits:
            print(f"      {c['date'][:16]}  {c['sha'][:7]}  {c['subject'][:60]}")
        print(f"      hypothesis.py add --feature <f> "
              f"--claim \"<关于 {f} 的猜想>\" "
              f"--evidence \"commit {hits[0]['sha'][:7]}\"")
        print()

    print("**嫌疑不是证据。** 每个提名文件仍要走假设台账与红绿闭环,")
    print("变更记录证明「动过」,不证明「为什么」(rootcause-guards)。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout (default: cwd)")
    parser.add_argument("--window", required=True, help="<from>..<to>, ISO-8601")
    parser.add_argument("--window-source", required=True,
                        help="问题发生时间 / 告警时间 / 数据更新时间")
    parser.add_argument("--artifact", type=Path,
                        help="线上跑的那份产物;给了就做产物差异交集排序")
    args = parser.parse_args()
    return cmd_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
