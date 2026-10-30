#!/usr/bin/env python3
"""Clean old idev execution artifacts, after folding them into memory.md.

Product sessions: <repo>/.idev/{traces,reviews,inbox}.
Conductor sessions with no current product: the kernel state dirs.
docs/task, .idev/task, .idev/docs, and the product line (marker, pack, workflows, handoff,
extensions, checks, strip-tokens, memory.md) are never deleted.

Default age clean is a dry run. Pass --apply to unlink.
Traces: always keep the newest --keep files. Among the rest, unlink
those older than --days.
Reviews: keep names containing "latest" or ending in status.env.
Inbox: unlink only status consumed/archived, and only when older than --days.
Each deleted file is appended to memory.md first.

--compact is the product .idev budget. It folds raw files into
.idev/memory.md (tracked; survives git clean of ignored residue), then
unlinks them when either trigger holds:
- a file outside the hot set is named at least --cites times in other
  reviews or proposals, or
- at least --generations have passed since the last compact.
The hot set always stays: newest --hot traces, latest reviews,
status.env, inbox that is not consumed/archived, and proposals that are
still open. --bump advances the generation counter (evolve-review does
this once per real run).

Phase 2 §2: before a trace is unlinked, the user citation (invoke),
decisions, rejected paths, delegations, recorded step status and evidence
paths, and call results are appended to .idev/timeline/<feature>.yaml.
memory.md keeps only a one-line prose pointer. Those fields are not folded
away.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from product_sink import kernel_root, product_repo, sink_dir  # noqa: E402
import structured_retain  # noqa: E402

INBOX_DONE = {"consumed", "archived"}
PROPOSAL_CLOSED = {"archived", "landed", "rejected", "ga", "done", "consumed"}
INTRO = (
    "# idev memory\n"
    "\n"
    "idev 在产线 `.idev/` 留下的可延续摘要。原始 trace、复盘、已消费 inbox、"
    "已关闭提案在写入这里之后删除。本文件纳入版本库，避免只留在被忽略的残留里。\n"
)


def execution_dirs(repo: Path | None) -> dict[str, Path]:
    if repo is None:
        root = kernel_root() / "state"
        return {
            "traces": sink_dir("traces"),
            "reviews": sink_dir("reviews"),
            "inbox": sink_dir("inbox"),
            "proposals": sink_dir("proposals"),
            "memory": root / "memory.md",
            "timeline": root / "timeline",
        }
    base = repo / ".idev"
    return {
        "traces": base / "traces",
        "reviews": base / "reviews",
        "inbox": base / "inbox",
        "proposals": base / "proposals",
        "memory": base / "memory.md",
        "timeline": base / "timeline",
    }


def status_of(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("status:"):
            return stripped.split(":", 1)[1].strip().strip("'\"")
    return ""


def inbox_done(path: Path) -> bool:
    return status_of(path) in INBOX_DONE


def proposal_closed(path: Path) -> bool:
    return status_of(path) in PROPOSAL_CLOSED


def review_protected(path: Path) -> bool:
    name = path.name
    return "latest" in name or name.endswith("status.env")


def one_line(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return path.name
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                lines = lines[index + 1 :]
                break
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("summary:"):
            value = stripped.split(":", 1)[1].strip().strip("'\"")
            if value:
                return value[:160]
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(("status:", "schema_version:", "marker:")):
            continue
        return stripped[:160]
    return path.name


def victims(directory: Path, kind: str, *, days: int, keep: int, now: float) -> list[Path]:
    if not directory.is_dir():
        return []
    files = [p for p in directory.iterdir() if p.is_file()]
    files.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    cutoff = now - days * 86400
    chosen: list[Path] = []
    for index, path in enumerate(files):
        if kind == "traces" and index < keep:
            continue
        if kind == "reviews" and review_protected(path):
            continue
        if kind == "inbox" and not inbox_done(path):
            continue
        if path.stat().st_mtime >= cutoff:
            continue
        chosen.append(path)
    return chosen


def read_memory(path: Path) -> tuple[int, int, str]:
    if not path.is_file():
        return 0, 0, ""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    if not match:
        return 0, 0, text.lstrip("\n")
    front = match.group(1)
    body = text[match.end() :].lstrip("\n")

    def num(key: str) -> int:
        found = re.search(r"^%s:\s*(\d+)\s*$" % key, front, re.M)
        return int(found.group(1)) if found else 0

    return num("generation"), num("last_compact_generation"), body


def write_memory(path: Path, generation: int, last: int, body: str, section: str) -> None:
    if not body.strip():
        body = INTRO
    if section:
        body = body.rstrip() + "\n\n" + section.strip() + "\n"
    elif not body.endswith("\n"):
        body += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = (
        "---\n"
        "marker: idev-memory\n"
        "generation: %d\n"
        "last_compact_generation: %d\n"
        "---\n\n%s" % (generation, last, body if body.endswith("\n") else body + "\n")
    )
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(path)


def section_for(title: str, items: list[tuple[str, Path]]) -> str:
    lines = ["## %s" % title, ""]
    for kind, path in items:
        lines.append("- `%s/%s`: %s" % (kind, path.name, one_line(path)))
    return "\n".join(lines)


def list_files(dirs: dict[str, Path]) -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    for kind in ("traces", "reviews", "inbox", "proposals"):
        directory = dirs[kind]
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.is_file():
                rows.append((kind, path))
    return rows


def cite_counts(rows: list[tuple[str, Path]]) -> dict[str, int]:
    texts: list[tuple[Path, str]] = []
    for _, path in rows:
        if path.suffix.lower() not in {".md", ".yaml", ".yml", ".txt", ".env"}:
            continue
        try:
            texts.append((path, path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    counts: dict[str, int] = {}
    for kind, path in rows:
        token = "%s/%s" % (kind, path.name)
        total = 0
        for source, text in texts:
            if source == path:
                continue
            total += text.count(token)
        counts[token] = total
    return counts


def hot_trace_names(directory: Path, hot: int) -> set[str]:
    if hot <= 0 or not directory.is_dir():
        return set()
    files = [p for p in directory.iterdir() if p.is_file()]
    files.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    return {path.name for path in files[:hot]}


def receipt_count(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.iterdir() if path.is_file() and "evolve-review-receipt" in path.name)


def eligible(kind: str, path: Path, hot_names: set[str]) -> bool:
    if kind == "traces":
        return path.name not in hot_names
    if kind == "reviews":
        return not review_protected(path)
    if kind == "inbox":
        return inbox_done(path)
    if kind == "proposals":
        return proposal_closed(path)
    return False


def resolve_repo(raw: str) -> Path | None:
    if raw:
        repo: Path | None = Path(raw).expanduser().resolve()
        if repo == kernel_root() or str(repo).startswith(str(kernel_root()) + "/"):
            return None
        return repo
    return product_repo()


def apply_items(
    items: list[tuple[str, Path]],
    *,
    do_apply: bool,
    apply_label: str,
    dry_label: str,
    dirs: dict[str, Path] | None = None,
) -> int:
    removed = 0
    for kind, path in items:
        if kind == "traces" and dirs is not None:
            kept = structured_retain.append_facts(dirs, path) if do_apply else None
            if kept is not None:
                print("KEEP-STRUCT %s -> %s" % (path.name, kept.name))
            elif not do_apply and structured_retain.extract_trace_facts(path) is not None:
                print("KEEP-STRUCT %s (dry-run)" % path.name)
        if do_apply:
            path.unlink()
            print("%s %s/%s" % (apply_label, kind, path.name))
        else:
            print("%s %s/%s" % (dry_label, kind, path.name))
        removed += 1
    return removed


def run_age(dirs: dict[str, Path], *, days: int, keep: int, do_apply: bool) -> int:
    now = time.time()
    chosen: list[tuple[str, Path]] = []
    for kind in ("traces", "reviews", "inbox"):
        for path in victims(dirs[kind], kind, days=days, keep=keep, now=now):
            chosen.append((kind, path))
    if do_apply and chosen:
        generation, last, body = read_memory(dirs["memory"])
        write_memory(dirs["memory"], generation, last, body, section_for("age", chosen))
    return apply_items(
        chosen, do_apply=do_apply, apply_label="RM ", dry_label="DRY", dirs=dirs
    )


def run_compact(
    dirs: dict[str, Path],
    *,
    hot: int,
    cites: int,
    generations: int,
    do_apply: bool,
    bump: bool,
) -> int:
    stored, last, body = read_memory(dirs["memory"])
    if bump:
        generation_now = stored + 1
    else:
        generation_now = max(stored, receipt_count(dirs["reviews"]))
    delta = generation_now - last
    rows = list_files(dirs)
    counts = cite_counts(rows)
    hot_names = hot_trace_names(dirs["traces"], hot)
    gen_hit = generations > 0 and delta >= generations
    cited = {token for token, count in counts.items() if count >= cites}
    chosen: list[tuple[str, Path]] = []
    for kind, path in rows:
        token = "%s/%s" % (kind, path.name)
        if not eligible(kind, path, hot_names):
            continue
        if gen_hit or token in cited:
            chosen.append((kind, path))
    chosen.sort(key=lambda item: (item[0], item[1].name))
    print(
        "generation=%s since_last=%s hot_traces=%s"
        % (generation_now, delta, len(hot_names))
    )
    if not chosen:
        print("compact SKIP")
    if do_apply and (chosen or bump):
        last_out = generation_now if chosen else last
        section = section_for("generation %s" % generation_now, chosen) if chosen else ""
        write_memory(dirs["memory"], generation_now, last_out, body, section)
    if bump:
        print("BUMP generation=%s" % generation_now)
    return apply_items(
        chosen, do_apply=do_apply, apply_label="RM ", dry_label="FOLD", dirs=dirs
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="", help="product checkout; default is the current session")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--keep", type=int, default=50, help="newest traces always kept by the age clean")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--compact", action="store_true", help="summarize, then drop files outside the hot set")
    parser.add_argument("--bump", action="store_true", help="with --compact, advance the generation counter")
    parser.add_argument("--hot", type=int, default=20, help="newest traces kept by --compact")
    parser.add_argument("--cites", type=int, default=2, help="citations outside the hot set that trigger a fold")
    parser.add_argument("--generations", type=int, default=3, help="generations since the last compact that trigger a fold")
    args = parser.parse_args(argv)
    if args.days < 0 or args.keep < 0 or args.hot < 0 or args.cites < 1 or args.generations < 1:
        print("FAIL days, keep, hot must be >= 0; cites and generations must be >= 1", file=sys.stderr)
        return 2
    repo = resolve_repo(args.repo)
    dirs = execution_dirs(repo)
    mode = "apply" if args.apply else "dry-run"
    print("# idev execution-clean")
    print("repo=%s" % (repo if repo else "conductor"))
    if args.compact:
        print(
            "mode=%s compact=1 cites=%s generations=%s"
            % (mode, args.cites, args.generations)
        )
        removed = run_compact(
            dirs,
            hot=args.hot,
            cites=args.cites,
            generations=args.generations,
            do_apply=args.apply,
            bump=args.bump,
        )
    else:
        print("mode=%s days=%s keep_traces=%s" % (mode, args.days, args.keep))
        removed = run_age(dirs, days=args.days, keep=args.keep, do_apply=args.apply)
    print("execution-clean PASS removed=%s" % removed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
