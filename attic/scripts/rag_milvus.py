#!/usr/bin/env python3
"""Local Milvus file that nominates line spans. It does not store bodies.

    The client is Milvus Lite: one .db file, same API as a single-node server,
    no Docker, etcd, or MinIO. One sparse field is whole words, the other is
    CJK bigrams. Milvus fuses the two lists with reciprocal rank (k=60), then
    a local pass reranks by the span text. A changed source file makes the
    stamp mismatch, and search then refuses to return the old spans.
"""
from __future__ import annotations

import hashlib
import os
import re
import warnings
from pathlib import Path

SPACE = 1 << 20
PAD = SPACE - 1
CANDIDATES = 40
RRF_K = 60
ALGO = "hybrid-v5"
FIELDS = ["path", "start", "end", "summary"]
CHUNK = 40
MAX_CHUNKS = 8000
MAX_FILE = 100_000
COLLECTION = "spans"
SKIP_DIRS = {"node_modules", "dist", "target", "vendor", "__pycache__"}
EXTS = {".py", ".go", ".java", ".ts", ".tsx", ".vue", ".js", ".jsx", ".sh", ".md"}
WORD = re.compile(r"[\w]{2,}", re.UNICODE)
CJK = re.compile(r"[\u4e00-\u9fff]+")


def one_line(text: str) -> str:
    flat = " ".join(str(text).split())
    if len(flat) <= 80:
        return flat
    return flat[:79] + "…"


def clip_err(exc: BaseException) -> str:
    return one_line(f"{type(exc).__name__}: {exc}")


def db_path(repo: Path) -> Path:
    return repo / ".idev" / "rag" / "milvus.db"


def stamp_path(repo: Path) -> Path:
    return repo / ".idev" / "rag" / "stamp"


def token_id(token: str) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % SPACE


def cjk_pairs(text: str) -> list[str]:
    pairs = []
    for run in CJK.findall(text):
        pairs.extend(run[i:i + 2] for i in range(len(run) - 1))
    return pairs


def word_tokens(text: str) -> list[str]:
    return WORD.findall(text.casefold())


def grams(text: str) -> list[str]:
    folded = text.casefold()
    return word_tokens(folded) + cjk_pairs(folded)


def embed_tokens(tokens: list[str]) -> dict[int, float]:
    vector: dict[int, float] = {}
    for token in set(tokens):
        slot = token_id(token)
        if slot != PAD:
            vector[slot] = 1.0
    return vector


def stored_vector(tokens: list[str]) -> dict[int, float]:
    vector = embed_tokens(tokens)
    if vector:
        return vector
    return {PAD: 1.0}


def iter_source(repo: Path) -> list[Path]:
    found: list[Path] = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [name for name in dirs if not name.startswith(".") and name not in SKIP_DIRS]
        found.extend(kept_file(Path(root), name) for name in files)
    return sorted(path for path in found if path is not None)


def kept_file(root: Path, name: str) -> Path | None:
    path = root / name
    if path.suffix.lower() not in EXTS or not path.is_file():
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size == 0 or size > MAX_FILE:
        return None
    return path


def source_stamp(repo: Path) -> str:
    rows = [ALGO]
    for path in iter_source(repo):
        stat = path.stat()
        rel = path.relative_to(repo).as_posix()
        rows.append(f"{rel}\t{stat.st_size}\t{stat.st_mtime_ns}")
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def collect_chunks(repo: Path, files: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in files:
        rows.extend(chunks_for(repo, path))
        if len(rows) >= MAX_CHUNKS:
            return rows[:MAX_CHUNKS]
    return rows


def chunks_for(repo: Path, path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rel = path.relative_to(repo).as_posix()
    rows = []
    start = 1
    while start <= len(lines):
        end = min(start + CHUNK - 1, len(lines))
        body = "\n".join(lines[start - 1:end])
        if body.strip():
            rows.append(chunk_row(rel, (start, end), (lines[start - 1], body)))
        if end >= len(lines):
            break
        start = end + 1
    return rows


def chunk_row(rel: str, span: tuple[int, int], text: tuple[str, str]) -> dict:
    start, end = span
    first, body = text
    summary = first.strip() or body.strip().splitlines()[0]
    return {
        "path": rel,
        "start": start,
        "end": end,
        "summary": one_line(summary),
        "lex": stored_vector(word_tokens(body)),
        "frag": stored_vector(cjk_pairs(body.casefold())),
    }


def index_repo(repo: Path) -> str:
    if not repo.is_dir():
        return "fail: 仓库不存在"
    chunks = collect_chunks(repo, iter_source(repo))
    if not chunks:
        return "fail: 没有可索引的文件"
    status = store_chunks(repo, chunks)
    if status != "ok":
        return status
    stamp_path(repo).write_text(source_stamp(repo) + "\n", encoding="utf-8")
    return f"ok chunks={len(chunks)}"


def store_chunks(repo: Path, chunks: list[dict]) -> str:
    try:
        write_db(repo, chunks)
    except ImportError:
        return "fail: 未安装 pymilvus"
    except OSError as exc:
        return "fail: " + clip_err(exc)
    except Exception as exc:
        return "fail: " + clip_err(exc)
    return "ok"


def reset_db(db: Path) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    lock = db.parent / f".{db.name}.lock"
    for path in (db, lock):
        if path.exists():
            path.unlink()


def span_schema(client):
    from pymilvus import DataType

    schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("lex", DataType.SPARSE_FLOAT_VECTOR)
    schema.add_field("frag", DataType.SPARSE_FLOAT_VECTOR)
    schema.add_field("path", DataType.VARCHAR, max_length=1024)
    schema.add_field("start", DataType.INT64)
    schema.add_field("end", DataType.INT64)
    schema.add_field("summary", DataType.VARCHAR, max_length=512)
    return schema


def span_index(client):
    params = client.prepare_index_params()
    params.add_index(field_name="lex", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")
    params.add_index(field_name="frag", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")
    return params


def transient(exc: BaseException) -> bool:
    text = str(exc).casefold()
    return "connecting" in text or "unavailable" in text or "socket" in text


def fill_db(repo: Path, chunks: list[dict]) -> None:
    client = open_client(db_path(repo))
    try:
        client.create_collection(COLLECTION, schema=span_schema(client), index_params=span_index(client))
        insert_all(client, chunks)
    finally:
        shutdown(client)


def write_db(repo: Path, chunks: list[dict]) -> None:
    last: BaseException | None = None
    for _ in range(2):
        reset_db(db_path(repo))
        try:
            fill_db(repo, chunks)
            return
        except Exception as exc:
            last = exc
            if not transient(exc):
                raise
    if last is not None:
        raise last


def open_client(db: Path):
    os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
    os.environ.setdefault("GLOG_minloglevel", "2")
    warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
    from pymilvus import MilvusClient

    return MilvusClient(str(db))


def shutdown(client) -> None:
    close = getattr(client, "close", None)
    if close is not None:
        close()


def insert_all(client, rows: list[dict]) -> None:
    batch: list[dict] = []
    next_id = 1
    for row in rows:
        batch.append(insert_row(next_id, row))
        next_id += 1
        if len(batch) == 128:
            client.insert(COLLECTION, batch)
            batch = []
    if batch:
        client.insert(COLLECTION, batch)


def insert_row(row_id: int, row: dict) -> dict:
    return {
        "id": row_id,
        "lex": row["lex"],
        "frag": row["frag"],
        "path": row["path"],
        "start": row["start"],
        "end": row["end"],
        "summary": row["summary"],
    }


def search_repo(repo: Path, query: str, top: int) -> tuple[list[dict], str]:
    if not db_path(repo).is_file():
        return [], "absent"
    saved = stamp_path(repo).read_text(encoding="utf-8").strip() if stamp_path(repo).is_file() else ""
    if saved != source_stamp(repo):
        return [], "fail: 索引过期"
    try:
        return query_db(repo, query, top), "ok"
    except ImportError:
        return [], "fail: 未安装 pymilvus"
    except OSError as exc:
        return [], "fail: " + clip_err(exc)
    except Exception as exc:
        return [], "fail: " + clip_err(exc)


def search_field(client, field: str, vector: dict[int, float]):
    return client.search(
        COLLECTION,
        data=[vector],
        anns_field=field,
        limit=CANDIDATES,
        output_fields=FIELDS,
        search_params={"metric_type": "IP"},
    )


def hybrid_of(client, lex_q: dict[int, float], frag_q: dict[int, float]):
    from pymilvus import AnnSearchRequest, RRFRanker

    reqs = [
        AnnSearchRequest(data=[lex_q], anns_field="lex", param={"metric_type": "IP"}, limit=CANDIDATES),
        AnnSearchRequest(data=[frag_q], anns_field="frag", param={"metric_type": "IP"}, limit=CANDIDATES),
    ]
    ranker = RRFRanker(RRF_K)
    return client.hybrid_search(COLLECTION, reqs, ranker, limit=CANDIDATES, output_fields=FIELDS)


def recall_once(repo: Path, lex_q: dict[int, float], frag_q: dict[int, float]):
    client = open_client(db_path(repo))
    try:
        if lex_q and frag_q:
            return hybrid_of(client, lex_q, frag_q)
        if lex_q:
            return search_field(client, "lex", lex_q)
        if frag_q:
            return search_field(client, "frag", frag_q)
        return []
    finally:
        shutdown(client)


def recall(repo: Path, lex_q: dict[int, float], frag_q: dict[int, float]):
    last: BaseException | None = None
    for _ in range(2):
        try:
            return recall_once(repo, lex_q, frag_q)
        except Exception as exc:
            last = exc
            if not transient(exc):
                raise
    if last is not None:
        raise last
    return []


def slice_text(repo: Path, row: dict) -> str | None:
    try:
        lines = (repo / row["path"]).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    start, end = int(row["start"]), int(row["end"])
    if start < 1 or start > len(lines):
        return None
    return "\n".join(lines[start - 1:min(end, len(lines))])


def span_has(repo: Path, row: dict, query: str) -> bool:
    body = slice_text(repo, row)
    if body is None:
        return False
    return bool(set(grams(query)).intersection(grams(body)))


def coverage(wanted: set[str], have: set[str]) -> float:
    if not wanted:
        return 0.0
    return len(wanted.intersection(have)) / len(wanted)


def rerank_key(repo: Path, row: dict, query: str) -> tuple:
    body = slice_text(repo, row) or ""
    exact = int(query.casefold() in body.casefold())
    lex = coverage(set(word_tokens(query)), set(word_tokens(body)))
    frag = coverage(set(cjk_pairs(query.casefold())), set(cjk_pairs(body.casefold())))
    return (exact, lex, frag, -int(row.get("order") or 0))


def confirmed(repo: Path, query: str, found) -> list[dict]:
    rows = [row for row in rows_from_hits(found) if span_has(repo, row, query)]
    return sorted(rows, key=lambda row: rerank_key(repo, row, query), reverse=True)


def query_db(repo: Path, query: str, top: int) -> list[dict]:
    lex_q = embed_tokens(word_tokens(query))
    frag_q = embed_tokens(cjk_pairs(query.casefold()))
    if not lex_q and not frag_q:
        return []
    return confirmed(repo, query, recall(repo, lex_q, frag_q))[:top]


def entity_of(hit) -> dict | None:
    if not isinstance(hit, dict):
        return None
    score = hit.get("distance")
    if not isinstance(score, (int, float)) or float(score) <= 0.0:
        return None
    entity = hit.get("entity")
    return entity if isinstance(entity, dict) else None


def rows_from_hits(found) -> list[dict]:
    group = found[0] if found else []
    rows = []
    for order, hit in enumerate(group):
        entity = entity_of(hit)
        row = None if entity is None else row_from_entity(entity, order)
        if row is not None:
            rows.append(row)
    return rows


def row_from_entity(entity: dict, order: int) -> dict | None:
    path = str(entity.get("path") or "")
    if not path or path.startswith("/") or ".." in Path(path).parts:
        return None
    try:
        start, end = int(entity["start"]), int(entity["end"])
    except (KeyError, TypeError, ValueError):
        return None
    if start < 1 or end < start:
        return None
    return {
        "kind": "rag",
        "id": f"{path}:{start}:{end}",
        "path": path,
        "start": start,
        "end": end,
        "summary": str(entity.get("summary") or ""),
        "order": order,
        "sources": "rag",
    }
