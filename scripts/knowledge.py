#!/usr/bin/env python3
"""按需增量知识检索 CLI（全文检索优先，SQLite FTS5 + CJK bigram）。

四个子命令：
  sync   扫描白名单目录，按内容 hash 增量重索引（新增 / 更新 / 删除）
  search 全文检索，输出 来源路径·章节·hash·适用范围·状态
  read   按 --id PATH:REV 读原文，返回前再验一次 hash
  doctor FTS5 探针、白名单解析、索引/真源一致性、孤儿条目

设计约束（见 state/proposals/20261108-knowledge-search-cli.md）：
- 检索时自动增量同步，用户不需要知道 sync 的存在；doctor 显式报告索引态
- 过期即失效：内容 hash 逐文件比对，源变即重索引，不返回旧片段
- SQLite FTS5 stdlib 自带，无进程、无重包、删掉即回退
- 入库与查询同用 CJK bigram 切词（连续汉字段切 bigram、拉丁数字词小写整存）
- 候选 / 未过闸不作为已验证事实注入；检索结果只是资料，不是执行授权
- `--repo` 是仓库路径（不是仓库名）；路径不存在会拒绝并提示，避免把同名仓库的索引静默清空
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parent
KERNEL_ROOT = SCRIPTS_ROOT.parent
INDEX_DIR = KERNEL_ROOT / "state" / "knowledge-index"
DB_PATH = INDEX_DIR / "knowledge.db"
LOCK_PATH = INDEX_DIR / "knowledge.lock"

# 白名单：仓库名 -> 要索引的相对目录。P0 只做 joypaas 单产品，证明收益后再扩。
# idev 自身 2026-11-07 入列：精读书籍的炼化产物（conventions 真源两页、notes 精读缺口）
# 是「指导与决策」检索面的一部分——编码规约的执行召回走 canon §2/§4 触发行，
# 但按主题找条目、找哪本书覆盖了什么，仍需要一条检索路。
WHITELIST: dict[str, list[str]] = {
    "joypaas": ["docs/design", ".idev/pack", ".cursor", "docs/adr"],
    "idev": ["conventions", "scripts/docs/notes", "deliver", "references", "docs"],
}

# 越界排除：白名单外的路径、密钥 / .env / 依赖目录 / 构建产物一律不索引。
EXCLUDE_PARTS = {".git", ".env", "node_modules", "__pycache__", "build", "dist",
                 "target", "vendor", ".idea", ".vscode"}
EXCLUDE_SUFFIXES = {".lock", ".pyc", ".class", ".jar", ".war", ".png", ".jpg",
                    ".jpeg", ".gif", ".svg", ".pdf", ".zip", ".tar", ".gz",
                    ".tgz", ".db", ".sqlite", ".sqlite3"}
# 精读层的原始材料（README 三层约定：不入库、可再生）不索引——OCR 全文噪声大，
# 会把精读缺口的命中挤出 Top-N；要查原文走书。
EXCLUDE_STEMS = {"-OCR", "-全文"}

CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
WORD_RE = re.compile(r"[a-z0-9]+")
QUERY_FILLERS = ("如何",)
QUERY_SYNONYMS = {
    "处理器": "handler",
    "弹性搜索": "elasticsearch",
}


def tokenize(text: str) -> str:
    """CJK bigram 切词：连续汉字段切重叠 bigram，拉丁/数字词小写整存。

    入库与查询同用本函数，保证同一文本得到同一 token 序列。FTS5 的 unicode61
    把一段连续汉字当作一个整 token，因此先把汉字段切成空格分隔的 bigram，
    再交给 unicode61，双字词查询即可精确命中（实测「账本」「采信」均 1 命中）。
    """
    out: list[str] = []
    pos = 0
    for m in CJK_RE.finditer(text):
        for w in WORD_RE.findall(text[pos:m.start()].lower()):
            out.append(w)
        run = m.group()
        if len(run) == 1:
            out.append(run)
        else:
            out.extend(run[i:i + 2] for i in range(len(run) - 1))
        pos = m.end()
    for w in WORD_RE.findall(text[pos:].lower()):
        out.append(w)
    return " ".join(out)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _excluded(rel: str) -> bool:
    """越界判定：依赖目录、密钥、构建产物、二进制后缀、OCR 原始材料不索引。"""
    parts = set(Path(rel).parts)
    if parts & EXCLUDE_PARTS:
        return True
    stem = Path(rel).stem
    if Path(rel).suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    if any(stem.endswith(s) for s in EXCLUDE_STEMS):
        return True
    return False


def _chapter(content: str, rel: str) -> str:
    """章节：取第一个 markdown 标题；没有标题用文件名。"""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:80]
    return Path(rel).stem


def _scope(rel: str) -> str:
    """适用范围：路径顶层目录 + 第一级子目录，便于按模块过滤。"""
    parts = Path(rel).parts
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0] if parts else ""


def _connect() -> sqlite3.Connection:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5("
        "content, path UNINDEXED, chapter UNINDEXED, hash UNINDEXED, "
        "status UNINDEXED, scope UNINDEXED, repo UNINDEXED, "
        "mtime UNINDEXED, size UNINDEXED"
        ")"
    )
    return conn


@contextlib.contextmanager
def _lock(timeout: float = 5.0):
    """单写锁：flock 有限等待，避免并发写坏索引。"""
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        deadline = time.time() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() >= deadline:
                    raise TimeoutError(f"knowledge lock timeout after {timeout}s")
                time.sleep(0.05)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _upsert(conn: sqlite3.Connection, repo: str, rel: str, content: str,
            h: str, st_mtime: float, st_size: int) -> None:
    tokenized = tokenize(content)
    chapter = _chapter(content, rel)
    scope = _scope(rel)
    conn.execute(
        "DELETE FROM docs WHERE path=? AND repo=?", (rel, repo)
    )
    conn.execute(
        "INSERT INTO docs (content, path, chapter, hash, status, scope, repo, mtime, size) "
        "VALUES (?, ?, ?, ?, 'doc', ?, ?, ?, ?)",
        (tokenized, rel, chapter, h, scope, repo, st_mtime, st_size),
    )


def _resolve_repo(repo_arg: str) -> Path:
    p = Path(repo_arg).resolve()
    if not p.is_dir():
        raise FileNotFoundError(
            f"repo 路径不存在: {p}（--repo 要传仓库路径，不是仓库名；在仓库内用 --repo .）"
        )
    return p


def _sync_repo(repo: Path) -> tuple[str, tuple[int, int, int, int]] | None:
    """Sync one repo; None means the repo is not whitelisted."""
    name = repo.name
    dirs = WHITELIST.get(name)
    if not dirs:
        return None
    with _lock():
        conn = _connect()
        try:
            added = updated = deleted = skipped = 0
            seen: set[str] = set()
            for d in dirs:
                base = repo / d
                if not base.is_dir():
                    continue
                for f in base.rglob("*"):
                    if not f.is_file() or f.is_symlink():
                        continue
                    try:
                        rel = str(f.relative_to(repo))
                    except ValueError:
                        continue
                    if _excluded(rel):
                        continue
                    st = f.stat()
                    row = conn.execute(
                        "SELECT hash, mtime, size FROM docs WHERE path=? AND repo=?",
                        (rel, name),
                    ).fetchone()
                    if row is not None and row[1] == st.st_mtime and row[2] == st.st_size:
                        seen.add(rel)
                        continue
                    try:
                        content = _read_text(f)
                    except OSError as exc:
                        # 读失败不崩整轮：跳过该条，doctor 会报「源不可读」。
                        print(f"skip unreadable {rel}: {exc}", file=sys.stderr)
                        skipped += 1
                        continue
                    h = sha256(content)
                    if row is None:
                        _upsert(conn, name, rel, content, h, st.st_mtime, st.st_size)
                        added += 1
                    elif row[0] != h:
                        _upsert(conn, name, rel, content, h, st.st_mtime, st.st_size)
                        updated += 1
                    seen.add(rel)
            for (rel,) in conn.execute("SELECT path FROM docs WHERE repo=?", (name,)).fetchall():
                if rel not in seen:
                    conn.execute("DELETE FROM docs WHERE path=? AND repo=?", (rel, name))
                    deleted += 1
            conn.commit()
        finally:
            conn.close()
    return name, (added, updated, deleted, skipped)


def cmd_sync(args: argparse.Namespace) -> int:
    repo = _resolve_repo(args.repo)
    result = _sync_repo(repo)
    if result is None:
        print(f"no whitelist for repo '{repo.name}'", file=sys.stderr)
        return 1
    name, (added, updated, deleted, skipped) = result
    print(f"sync {name}: +{added} ~{updated} -{deleted} !{skipped}")
    return 0


def _search_query(q: str) -> str:
    for filler in QUERY_FILLERS:
        q = q.replace(filler, "")
    expanded = [english for chinese, english in QUERY_SYNONYMS.items() if chinese in q]
    terms = list(dict.fromkeys(tokenize(q).split() + expanded))
    if not terms:
        return ""
    # OR 语义 + bm25 排序：长查询切出的 bigram 里含跨词边界的噪声 token，
    # 用 AND 会要求整句连续命中（过严）；OR 让任一 bigram 命中即进入候选，
    # 由 _filter_coverage 按查询词覆盖数过滤、bm25 排序。
    return " OR ".join(f'"{t}"' for t in terms)


def _filter_coverage(rows: list, conn: sqlite3.Connection, repo: str,
                      fts_q: str, min_hits: int) -> list:
    """查询词覆盖数硬门：结果至少命中过半查询词才保留。

    FTS5 的 OR 查询不返回每词命中明细，这里对 Top-N 候选逐个回查
    `MATCH '"t"'`（LIMIT top 之后才过滤，候选集不放大，回查是点查）。
    拉丁词不折半：中文主题词切 bigram 后一词多 token，英文同义扩展词
    （handler / elasticsearch）只算加分不算门槛。没过线的结果宁可丢掉
    ——排上来的噪声比零命中更贵。
    """
    terms = [t.strip('"') for t in fts_q.split(" OR ")]
    out = []
    for r in rows:
        path = r[0]
        if not path:
            continue
        # MATCH 只收一个查询串：OR 整串命中只证明 >=1，因此要数「该文档
        # 对几个查询词有命中」须逐词点查（候选 × 词数次，Top-N 内点查）。
        hit = sum(
            1 for t in terms
            if conn.execute(
                "SELECT 1 FROM docs WHERE docs MATCH ? AND path=? AND repo=?",
                (f'"{t}"', path, repo),
            ).fetchone()
        )
        if hit >= min_hits:
            out.append(r)
    return out


def cmd_search(args: argparse.Namespace) -> int:
    repo = _resolve_repo(args.repo)
    name = repo.name
    if _sync_repo(repo) is None:
        print(f"no whitelist for repo '{name}'", file=sys.stderr)
        return 1
    fts_q = _search_query(args.query)
    if not fts_q:
        print("empty query", file=sys.stderr)
        return 1
    conn = _connect()
    try:
        # NEAR/2 与 AND-子集在这里都试过：真实语料（590K 精读缺口）上假命中与
        # 真命中的 bm25 分数连续（假命中 -15.5 排在真命中之前），单靠 bm25
        # 分不开。改为查询词覆盖数硬门：结果至少要覆盖过半查询词（拉丁词
        # 不折半），再由 bm25 排序。这挡住了跨词边界 bigram 撞长文档的假命中。
        n_terms = len(fts_q.split(" OR "))
        # 过半向上取整；单词 / 双词查询保持原语义（>=1），多词查询至少两词命中。
        min_hits = min(max(2, (n_terms + 1) // 2), n_terms)
        rows = conn.execute(
            "SELECT path, chapter, hash, scope, status, bm25(docs) FROM docs "
            "WHERE docs MATCH ? AND repo=? ORDER BY bm25(docs) LIMIT ?",
            (fts_q, name, args.top),
        ).fetchall()
        rows = _filter_coverage(rows, conn, name, fts_q, min_hits)
    finally:
        conn.close()
    rows = [r[:5] for r in rows]
    if args.json:
        print(json.dumps([
            {"path": r[0], "chapter": r[1], "hash": r[2], "scope": r[3], "status": r[4]}
            for r in rows
        ], ensure_ascii=False, indent=2))
    elif not rows:
        print("零命中")
    else:
        for r in rows:
            print(f"{r[0]} · {r[1]} · {r[2][:12]} · {r[3]} · {r[4]}")
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    repo = _resolve_repo(args.repo)
    path_str, sep, rev = args.id.partition(":")
    if not sep or not rev:
        print("usage: read --id PATH:REV", file=sys.stderr)
        return 1
    target = (repo / path_str).resolve()
    try:
        target.relative_to(repo)
    except ValueError:
        print(f"refuse: {path_str} escapes repo root", file=sys.stderr)
        return 1
    if not target.is_file():
        print(f"refuse: {path_str} not found", file=sys.stderr)
        return 1
    content = _read_text(target)
    if sha256(content) != rev:
        print(f"refuse: {path_str} hash mismatch (source changed)", file=sys.stderr)
        return 1
    sys.stdout.write(content)
    if not content.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    problems: list[str] = []
    # 索引完整性
    if DB_PATH.is_file():
        try:
            conn = sqlite3.connect(DB_PATH)
            try:
                ok = conn.execute("PRAGMA integrity_check").fetchone()
                if ok != ("ok",):
                    problems.append(f"索引损坏: {ok}")
            finally:
                conn.close()
        except sqlite3.DatabaseError as exc:
            problems.append(f"索引打不开: {exc}")
    # FTS5 探针
    try:
        probe = sqlite3.connect(":memory:")
        probe.execute("CREATE VIRTUAL TABLE probe USING fts5(x)")
        probe.execute("INSERT INTO probe(x) VALUES ('探针')")
        probe.execute("SELECT count(*) FROM probe WHERE probe MATCH '探针'")
        probe.close()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"FTS5 探针失败: {exc}")
    # 白名单解析
    if args.repo:
        repo = _resolve_repo(args.repo)
        name = repo.name
        dirs = WHITELIST.get(name)
        if not dirs:
            problems.append(f"仓库 '{name}' 无白名单")
        else:
            for d in dirs:
                if not (repo / d).is_dir():
                    problems.append(f"白名单目录缺失: {name}/{d}")
        # 索引/真源一致性 + 孤儿
        if DB_PATH.is_file():
            conn = _connect()
            try:
                for (rel, h) in conn.execute(
                    "SELECT path, hash FROM docs WHERE repo=?", (name,)
                ).fetchall():
                    src = repo / rel
                    if not src.is_file():
                        problems.append(f"孤儿条目（源已删）: {rel}")
                    elif sha256(_read_text(src)) != h:
                        problems.append(f"过期条目（源已变）: {rel}")
            finally:
                conn.close()
    if problems:
        for p in problems:
            print(f"doctor: {p}")
        return 1
    print("doctor: ok")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="knowledge.py", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sync = sub.add_parser("sync", help="扫描白名单并增量重索引")
    p_sync.add_argument("--repo", required=True)
    p_sync.add_argument("--feature", default="")
    p_sync.set_defaults(func=cmd_sync)

    p_search = sub.add_parser("search", help="全文检索")
    p_search.add_argument("--repo", required=True)
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--feature", default="")
    p_search.add_argument("--top", type=int, default=10)
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_read = sub.add_parser("read", help="按 --id PATH:REV 读原文并验 hash")
    p_read.add_argument("--id", required=True)
    p_read.add_argument("--repo", required=True)
    p_read.set_defaults(func=cmd_read)

    p_doctor = sub.add_parser("doctor", help="探针 + 一致性 + 孤儿")
    p_doctor.add_argument("--repo", default="")
    p_doctor.set_defaults(func=cmd_doctor)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"knowledge: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
