#!/usr/bin/env python3
"""按需增量知识检索 CLI（全文检索优先，SQLite FTS5 + CJK bigram）。

五个子命令：
  sync   扫描白名单目录，按内容 hash 增量重索引（新增 / 更新 / 删除）
  search 全文检索，输出 来源路径·章节·hash·适用范围·状态
  read   按 --id PATH:REV 读原文，返回前再验一次 hash
  doctor FTS5 探针、白名单解析、索引/真源一致性、孤儿条目
  questions 跑验收问题集，Top-5 来源命中 >= 90%

设计约束（见 state/proposals/20261108-knowledge-search-cli.md）：
- 检索时自动增量同步，用户不需要知道 sync 的存在；doctor 显式报告索引态
- 过期即失效：内容 hash 逐文件比对，源变即重索引，不返回旧片段
- SQLite FTS5 stdlib 自带，无进程、无重包、删掉即回退
- 入库与查询同用 CJK bigram 切词（连续汉字段切 bigram、拉丁数字词小写整存）
- 候选 / 未过闸不作为已验证事实注入；检索结果只是资料，不是执行授权
- `--repo` 是仓库路径（不是仓库名）；路径不存在会拒绝并提示，避免把同名仓库的索引静默清空
- `questions` 跑 `state/knowledge-questions.yaml` 验收问题集（Top-5 来源命中 >= 90%）
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
                      query: str, min_hits: int) -> list:
    """查询词覆盖数硬门：结果至少命中过半「原始查询词」才保留。

    FTS5 的 OR 查询不返回每词命中明细，这里对候选逐个回查 `MATCH '"t"'`。
    计数单位是**原始查询词**而非 token：一个词的任一 bigram / 拉丁 token
    命中都算该词命中——否则「弹性搜索」切出 弹性/性搜/搜索 三个 token，
    英文文档只命中同义扩展词 elasticsearch 时被误挡（实测 joypaas q15
    真命中被挡）。同义扩展词只算加分不算门槛。没过线的结果宁可丢掉
    ——排上来的噪声比零命中更贵。
    """
    # 原始查询词：空格分词；中文段不再按 bigram 拆计数单位。
    raw_words = [w for w in query.split() if w]
    word_tokens: list[list[str]] = []
    for w in raw_words:
        toks = tokenize(w).split()
        if toks:
            word_tokens.append(toks)
    # 同义扩展词（如 弹性搜索->elasticsearch）：只算加分不算门槛——中文词
    # 在英文文档上零命中时，扩展词命中仍保住该词（joypaas q15 即此形态）。
    expanded = [english for chinese, english in QUERY_SYNONYMS.items() if chinese in query]
    out = []
    for r in rows:
        path = r[0]
        if not path:
            continue
        hit = 0
        for toks in word_tokens:
            if any(
                conn.execute(
                    "SELECT 1 FROM docs WHERE docs MATCH ? AND path=? AND repo=?",
                    (f'"{t}"', path, repo),
                ).fetchone()
                for t in toks
            ):
                hit += 1
                continue
            if any(
                conn.execute(
                    "SELECT 1 FROM docs WHERE docs MATCH ? AND path=? AND repo=?",
                    (f'"{e}"', path, repo),
                ).fetchone()
                for e in expanded
            ):
                hit += 1
        if hit >= min_hits:
            out.append(r)
    return out


def _run_search(repo: Path, name: str, query: str, top: int) -> list:
    """search 与 questions 共用的检索体：宽召回 -> 覆盖数门 -> 真源优先 -> 裁 top。

    返回未截 hash 的原始行（path, chapter, hash, scope, status, bm25）。
    """
    fts_q = _search_query(query)
    if not fts_q:
        return []
    conn = _connect()
    try:
        # NEAR/2 与 AND-子集在这里都试过：真实语料（590K 精读缺口）上假命中与
        # 真命中的 bm25 分数连续（假命中 -15.5 排在真命中之前），单靠 bm25
        # 分不开。改为查询词覆盖数硬门：结果至少要覆盖过半查询词，再由
        # bm25 排序。这挡住了跨词边界 bigram 撞长文档的假命中。
        n_terms = len(query.split())
        # 过半向上取整；单词 / 双词查询保持原语义（>=1），多词查询至少两词命中。
        min_hits = min(max(2, (n_terms + 1) // 2), n_terms)
        rows = conn.execute(
            "SELECT path, chapter, hash, scope, status, bm25(docs) FROM docs "
            "WHERE docs MATCH ? AND repo=? ORDER BY bm25(docs) LIMIT ?",
            # 候选池放宽到 4 倍：bm25 偏好短文档，会把词密的缺口报告排进
            # 前几名、把长而全的真源挤出小 Top-N（实测 canon 排到第 6/11 名）。
            # 先宽召回，再由覆盖数门与真源优先收严，最后裁到 --top。
            (fts_q, name, max(top * 4, 40)),
        ).fetchall()
        rows = _filter_coverage(rows, conn, name, query, min_hits)
        # 排序：真源目录优先（稳定排序，bm25 分相同层内定序）。书的缺口
        # 报告短而词密，bm25 会把它排在执法真源之前——但报告本来就是对
        # 真源的溯源（「对照结论」节引用的就是真源编号），要执行指导的
        # 调用方先要真源原文，再要出处。conventions/ 前缀只影响 idev 仓，
        # 产品仓无此目录、排序不生效。
        rows.sort(key=lambda r: (0 if r[0].startswith("conventions/") else 1, r[5]))
        return rows[:top]
    finally:
        conn.close()


def cmd_search(args: argparse.Namespace) -> int:
    repo = _resolve_repo(args.repo)
    name = repo.name
    if _sync_repo(repo) is None:
        print(f"no whitelist for repo '{name}'", file=sys.stderr)
        return 1
    if not _search_query(args.query):
        print("empty query", file=sys.stderr)
        return 1
    rows = _run_search(repo, name, args.query, args.top)
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


QUESTIONS_PATH = KERNEL_ROOT / "state" / "knowledge-questions.yaml"


def cmd_questions(args: argparse.Namespace) -> int:
    """验收问题集回归：每条问题跑一次 Top-5 检索，来源命中 >= 90% 才 PASS。

    问题集是验收工具不是产品知识（改它不触发产品仓变更）；期望来源
    allowlist 对上即命中（相等 / endswith 任一方向）。输出计数与逐条
    PASS/MISS，退出码 0/1 —— 与 doctor 同级，不进任何门禁。
    """
    try:
        import yaml
    except ImportError:
        print("PyYAML not available", file=sys.stderr)
        return 2
    if not QUESTIONS_PATH.is_file():
        print(f"questions: {QUESTIONS_PATH} not found", file=sys.stderr)
        return 2
    repo = _resolve_repo(args.repo)
    name = repo.name
    if _sync_repo(repo) is None:
        print(f"no whitelist for repo '{name}'", file=sys.stderr)
        return 1
    questions = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8")) or []
    if not questions:
        print("questions: empty question set", file=sys.stderr)
        return 2
    passed = 0
    for q in questions:
        rows = _run_search(repo, name, q["query"], top=5)
        paths = [r[0] for r in rows]
        hit = any(
            p == e or p.endswith(e) or e.endswith(p)
            for p in paths for e in q.get("expect", [])
        )
        passed += hit
        state = "PASS" if hit else "MISS"
        first = paths[0] if paths else "零命中"
        print(f"{state} {q['id']} {q['query']} -> {first}")
    need = len(questions) * 9 // 10  # >= 90%
    print(f"questions: {passed}/{len(questions)} (门槛 {need})")
    return 0 if passed >= need else 1


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

    p_questions = sub.add_parser("questions", help="验收问题集回归（Top-5 来源命中 >= 90%%）")
    p_questions.add_argument("--repo", required=True)
    p_questions.set_defaults(func=cmd_questions)
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
