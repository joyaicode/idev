#!/usr/bin/env python3
"""人在方案文档里写下的标注，和它们的处置。

    annotate.py scan   --feature F              # 还没处置的标注
    annotate.py settle --feature F --at <file:line> --how "<一句话>"
    annotate.py check  --feature F              # 三条判据
    annotate.py schema

需求和设计阶段最贵的一次来回，是人看完方案、心里有十处要改，然后在聊天里
把它们复述一遍。复述会漏，会走样，而且下一轮没有任何东西能对照着查。

所以把文档本身当成人机之间的共享可变状态：人在原地写标注，Agent 处理完
在原地标掉，台账留下原文与处置。这不是新的门禁 —— SKILL.md 硬规则 3 本来
就写着「矛盾、冲突或不清楚没对齐之前禁止写 sealed / arch.accepted」，
人写下的标注就是显式的那一个「不清楚」。这里只是让它判得出来。

## 写法

    Markdown   <!-- @me: 这里不该加缓存 -->
    YAML       # @me: 这里不该加缓存

两种都是各自语言里的注释，不影响解析，也不进入任何正文。
处置完把 `@me:` 改成 `@done:`，原文一个字都不要动。

## 三条判据

1. 文里还有 `@me:`                → 这一条还没处置
2. 文里有 `@done:` 而台账里没有    → 处置没有留痕，等于口头说改了
3. 台账里有、文里两种标记都找不到  → **标注被抹掉了**

第 3 条是这个工具存在的主要理由。前两条只是漏做，第三条是人的意见被
一次重写悄悄吃掉 —— 那比没有这套机制更坏，因为人会以为自己提过了。

## 不等人点头

Agent 处置完（settle + 改成 `@done:`）这一关就能过。人不满意，下一轮再标
一次。答问不是签字，处置也不是：这里留的是可审计的痕迹，不是批准。

Exit: 0 ok, 1 findings, 2 cannot read.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402

sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
try:
    import doc_home  # noqa: E402
except ImportError:
    print(f"BLOCKED cannot import doc_home from {kind_agents.kernel_root()}; set IDEV_ROOT", file=sys.stderr)
    raise SystemExit(2) from None

OPEN = "@me:"
DONE = "@done:"

# <!-- @me: ... --> and # @me: ... , plus the same two for @done.
MARK = re.compile(
    r"(?:<!--\s*|#\s*)@(?P<state>me|done):\s*(?P<text>.*?)\s*(?:-->|$)",
    re.M,
)

SCHEMA = """\
# 标注台账(<票目录>/annotations.yaml)
#
# notes:
#   - id: A1
#     file: .idev/task/demo/arch.yaml   # 相对仓根
#     text: 这里不该加缓存              # 人写下的原文,一个字都不改
#     sha256: <text 的 sha256>
#     at: 2026-11-05T10:00:00+08:00
#     how: 删掉了缓存那一节,改为直读     # 处置,一句话
#
# 人写 `@me:`,Agent 处理完 settle 一条并把文里的 `@me:` 改成 `@done:`。
# 原文不许动 —— sha256 对不上就是另一条标注,台账会说这一条没留痕。
# 本命令不签字,不改正文,也不替人决定标注该不该接受。
"""


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def digest(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def repo_of(args: argparse.Namespace) -> Path:
    if args.repo:
        return Path(args.repo).resolve()
    if os.environ.get("IDEV_PRODUCT_REPO"):
        return Path(os.environ["IDEV_PRODUCT_REPO"]).resolve()
    return Path.cwd().resolve()


def ledger_path(repo: Path, feature: str) -> Path:
    home = doc_home.homes(repo, feature)["task"]
    if not home.is_dir():
        print(f"BLOCKED no ticket home at {home}", file=sys.stderr)
        print("HINT    feature 名打错了?或这张票还没建立", file=sys.stderr)
        raise SystemExit(2)
    return home / "annotations.yaml"


def surfaces(repo: Path, feature: str) -> list[Path]:
    """The documents a person reviews and annotates, in the order they are written."""
    found = doc_home.homes(repo, feature)
    task = found["task"]
    paths = [task / name for name in ("baseline.yaml", "req.yaml", "arch.yaml", "design.md")]
    paths += [found["prd"], found["spec"], found["test-case"]]
    seen: list[Path] = []
    for path in paths:
        if isinstance(path, Path) and path not in seen:
            seen.append(path)
    return seen


def load(path: Path) -> dict | None:
    """The ledger, or None when the file is there but unreadable."""
    if not path.exists():
        return {"schema_version": 1, "notes": []}
    data = safeyaml.mapping(path)
    if data is None:
        return None
    data.setdefault("schema_version", 1)
    data.setdefault("notes", [])
    return data


def notes_of(data: dict) -> list[dict]:
    return [x for x in safeyaml.as_list(data.get("notes")) if isinstance(x, dict)]


def next_id(notes: list[dict]) -> str:
    n = 0
    for item in notes:
        raw = str(item.get("id", "")).lstrip("A")
        if raw.isdigit():
            n = max(n, int(raw))
    return f"A{n + 1}"


def rel(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo).as_posix()
    except ValueError:
        return path.as_posix()


def marks(repo: Path, feature: str) -> list[dict]:
    """Every annotation in every surface: where it is, what it says, open or settled."""
    found: list[dict] = []
    for path in surfaces(repo, feature):
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"WARN 读不了 {path}: {exc}", file=sys.stderr)
            continue
        for n, line in enumerate(body.splitlines(), start=1):
            hit = MARK.search(line)
            if not hit:
                continue
            text = hit.group("text").strip()
            if not text:
                continue
            found.append({
                "file": rel(repo, path),
                "path": path,
                "line": n,
                "state": hit.group("state"),
                "text": text,
                "sha256": digest(text),
            })
    return found


def cmd_scan(args: argparse.Namespace) -> int:
    repo = repo_of(args)
    found = marks(repo, args.feature)
    open_marks = [m for m in found if m["state"] == "me"]
    if not open_marks:
        print(f"OK   没有待处置的标注  ({len(found)} 条标注,全部已处置)")
        return 0
    print(f"# 待处置标注 {len(open_marks)} 条")
    print()
    print("**这些是人写下的要求,不是建议。** 逐条处理,更新文档,")
    print("然后 settle 一条并把文里的 `@me:` 改成 `@done:`。原文不要动。")
    print()
    for m in open_marks:
        print(f"## {m['file']}:{m['line']}")
        print(f"   {m['text']}")
        print(f"   settle: --at {m['file']}:{m['line']} --how \"<一句话>\"")
        print()
    return 1


def cmd_settle(args: argparse.Namespace) -> int:
    repo = repo_of(args)
    path = ledger_path(repo, args.feature)
    data = load(path)
    if data is None:
        print(f"BLOCKED 台账读不了 {path}", file=sys.stderr)
        print("HINT    不覆盖这份文件。先修好或移走,再记新的", file=sys.stderr)
        return 2

    how = " ".join(str(args.how or "").split())
    if not how:
        print("BLOCKED --how 不能为空。没写怎么处置的,等于没有留痕", file=sys.stderr)
        return 2

    where = str(args.at)
    if ":" not in where:
        print("BLOCKED --at 要写成 <file>:<line>", file=sys.stderr)
        return 2
    name, _, lineno = where.rpartition(":")
    found = [m for m in marks(repo, args.feature)
             if m["file"] == name and str(m["line"]) == lineno]
    if not found:
        print(f"BLOCKED {where} 上没有标注", file=sys.stderr)
        print("HINT    先跑 scan 看现在还有哪些", file=sys.stderr)
        return 2
    mark = found[0]

    notes = notes_of(data)
    if any(str(x.get("sha256")) == mark["sha256"] for x in notes):
        print(f"OK   这一条已经记过了: {mark['text'][:40]}")
        return 0
    notes.append({
        "id": next_id(notes),
        "file": mark["file"],
        "text": mark["text"],
        "sha256": mark["sha256"],
        "at": now(),
        "how": how,
    })
    data["notes"] = notes
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safeyaml.dump(data), encoding="utf-8")
    print(f"OK   记下 {notes[-1]['id']} -> {path}")
    print(f"NEXT 把 {mark['file']}:{mark['line']} 的 `{OPEN}` 改成 `{DONE}`,原文不动")
    return 0


def findings(repo: Path, feature: str) -> list[str]:
    """The three checks, in the words check-feature prints."""
    path = doc_home.homes(repo, feature)["task"] / "annotations.yaml"
    data = load(path)
    if data is None:
        return [f"标注台账读不了: {path}"]
    notes = notes_of(data)
    by_sha = {str(x.get("sha256")): x for x in notes}
    found = marks(repo, feature)
    out: list[str] = []

    for m in found:
        if m["state"] == "me":
            out.append(f"标注未处置 {m['file']}:{m['line']} — {m['text'][:60]}")
        elif m["sha256"] not in by_sha:
            out.append(
                f"标注处置无留痕 {m['file']}:{m['line']} — {m['text'][:60]}"
                f" (settle 一条,或把原文改回来)"
            )

    seen = {m["sha256"] for m in found}
    for note in notes:
        sha = str(note.get("sha256"))
        if sha not in seen:
            out.append(
                f"标注被抹掉 {note.get('id')} {note.get('file')} — {str(note.get('text'))[:60]}"
                f" (台账里有,文里两种标记都找不到)"
            )
    return out


def cmd_check(args: argparse.Namespace) -> int:
    repo = repo_of(args)
    out = findings(repo, args.feature)
    if not out:
        print("OK   标注都处置了,处置都有留痕")
        print("PASS 这只说明没撞上已知的硬错,不说明方案对齐了")
        return 0
    for line in out:
        print(f"FAIL {line}")
    print("STOP 人写下的标注还没对齐,不要写 sealed / accepted", file=sys.stderr)
    return 1


def cmd_schema(_: argparse.Namespace) -> int:
    print(SCHEMA)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="product checkout (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="未处置的标注")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("settle", help="记下一条标注的处置")
    p.add_argument("--feature", required=True)
    p.add_argument("--at", required=True, help="<file>:<line>,按 scan 打出来的那个")
    p.add_argument("--how", required=True, help="怎么处置的,一句话")
    p.set_defaults(fn=cmd_settle)

    p = sub.add_parser("check", help="三条判据")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("schema", help="台账字段")
    p.set_defaults(fn=cmd_schema)

    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
