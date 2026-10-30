#!/usr/bin/env python3
"""A ledger for a repeated operation that already has a script.

    sediment.py add --feature F --form program ...
    sediment.py transform --feature F --id S1 --by NAME --repro PATH
    sediment.py recall --feature F --scope S
    sediment.py gc --feature F
    sediment.py retire --feature F --id S1 --why "..."
    sediment.py check --feature F
    sediment.py schema

Facts stay on the troubleshooting ledger. A judgment that depends on
context stays a proposal. This file only records a program: a path to a
script that already exists. One result stays a candidate. A second,
different result and a named person are required before it is kept.

This command does not generate code, does not run it, and does not write
prompt files. External text is refused.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402
import workflow_spec  # noqa: E402

STATUS = ("candidate", "kept", "retired")
FORM = ("fact", "instruction", "program")
TRUST = ("reviewed", "external")
STATUS_WHY = {
    "candidate": "先记下。一次成功还不是能力",
    "kept": "两条不同结果，并且由人确认。仍不是答案",
    "retired": "过时就清，避免下一轮把它读成现行",
}
FORM_WHY = {
    "fact": "不收。带来源的事实走 lessons.py add",
    "instruction": "不收。要看语境的判断写成提案的最小 diff",
    "program": "指向一份已经存在的脚本。本命令不生成，也不执行",
}
TRUST_WHY = {
    "reviewed": "内容来自这次仓库里的结果，人还会在留下时再看一次",
    "external": "内容来自仓库以外或不受信任的文本，只能作为未审记录",
}
TEXT = ("scope", "claim", "not_when")
TEXT_Q = {
    "scope": "在什么范围内",
    "claim": "记下的那句话",
    "not_when": "何时不适用",
}
FORBIDDEN_NAMES = frozenset(
    {"SKILL.md", "AGENTS.md", "CLAUDE.md", "SOUL.md", "MEMORY.md"}
)
SCRIPT_SUFFIXES = frozenset({".py", ".sh"})

SCHEMA = """\
# 知识沉淀(state/sediment.yaml 或 <票目录>/sediment.yaml)
#
# entries:
#   - id: S1
#     status: candidate          # candidate | kept | retired
#     form: program              # 只收 program。fact 走 lessons.py，instruction 走提案
#     trust: reviewed            # 只收 reviewed。external 停在轨迹里
#     scope: 库存回写
#     claim: 积压在生产侧时先看位点，再看消费者
#     not_when: 位点连续推进时不适用
#     evidence: [ev/once.log, ev/twice.log]
#     script: scripts/check.sh   # 仓库里已有的 .py 或 .sh。本命令不生成、不执行
#     from_feature: ticket-123
#     confirmed_by: ""
#     repro: ""
#     bound:                     # transform 时写下。脚本或结果一变，这条就不再是现行能力
#       script: <sha256>
#       evidence:
#         ev/once.log: <sha256>
#         ev/twice.log: <sha256>
#       repro: <sha256>
#     uses: 0
#     at: ...
#
# 留下(transform)才从 candidate 到 kept：
#   - 至少两条内容不同的结果文件。同一条日志复制两份不算
#   - 脚本路径本身不算结果
#   - --by 是人，不能是 agent / ai
#   - --repro 指向仓库里一份非空文件，而且不是起草证据里的路径，内容也不同
#   - trust 必须是 reviewed。external 不进入这本账
# 没有参数能在 add 时直接写成 kept。
#
# 召回是记录、建议或脚本位置，不是答案。本命令不执行脚本，不改提示词。
# gc 只指出重复、包含、失效、字节漂移和只有一条证据的条目，不删除。
"""


def pair_check() -> list[str]:
    """Every enum must have its explanation, and vice versa."""
    out = []
    groups = (
        ("STATUS", STATUS, STATUS_WHY),
        ("FORM", FORM, FORM_WHY),
        ("TRUST", TRUST, TRUST_WHY),
        ("TEXT", TEXT, TEXT_Q),
    )
    for name, keys, why in groups:
        for key in keys:
            if key not in why:
                out.append(f"{name}: {key} 没有说明")
        for key in why:
            if key not in keys:
                out.append(f"{name}: {key} 有说明但不在清单里")
    return out


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def repo_of(args: argparse.Namespace) -> Path:
    if getattr(args, "repo", None):
        return Path(args.repo).expanduser().resolve()
    if os.environ.get("IDEV_PRODUCT_REPO"):
        return Path(os.environ["IDEV_PRODUCT_REPO"]).expanduser().resolve()
    return Path.cwd().resolve()


def ledger_path(repo: Path, feature: str | None) -> Path:
    """Ticket-local when a feature is given, else the kernel-wide ledger."""
    if feature:
        sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
        import doc_home  # noqa: E402

        home = doc_home.homes(repo, feature)["task"]
        if not home.is_dir():
            print(f"BLOCKED no ticket home at {home}", file=sys.stderr)
            print("HINT    feature 名打错了?或这张票还没建立", file=sys.stderr)
            raise SystemExit(2)
        return home / "sediment.yaml"
    return kind_agents.kernel_root() / "state" / "sediment.yaml"


def load(path: Path) -> dict | None:
    """The ledger, or None when the file exists but cannot be read as a mapping.

    A missing file is an empty ledger. A broken file is not: callers must
    refuse to overwrite it.
    """
    if not path.exists():
        return {"schema_version": 1, "entries": []}
    data = safeyaml.mapping(path)
    if data is None:
        return None
    data.setdefault("schema_version", 1)
    data.setdefault("entries", [])
    return data


def refuse_broken(path: Path, data: dict | None) -> int | None:
    if data is not None:
        return None
    print(f"BLOCKED 台账读不了 {path}", file=sys.stderr)
    print("HINT    不覆盖这份文件。先修好或移走，再记新的", file=sys.stderr)
    return 2


def entries_of(data: dict) -> list:
    return [x for x in safeyaml.as_list(data.get("entries")) if isinstance(x, dict)]


def next_id(entries: list) -> str:
    n = 0
    for item in entries:
        if isinstance(item, dict):
            raw = str(item.get("id", "")).lstrip("S")
            if raw.isdigit():
                n = max(n, int(raw))
    return f"S{n + 1}"


def find(entries: list, sid: str) -> dict | None:
    want = sid.upper()
    for item in entries:
        if isinstance(item, dict) and str(item.get("id", "")).upper() == want:
            return item
    return None


def _merge(fresh: dict, item: dict) -> dict:
    fresh.setdefault("schema_version", 1)
    fresh.setdefault("entries", [])
    for n, existing in enumerate(fresh["entries"]):
        if isinstance(existing, dict) and str(existing.get("id")) == str(item.get("id")):
            fresh["entries"][n] = item
            return fresh
    fresh["entries"].append(item)
    return fresh


def _norm(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hex64(text: str) -> bool:
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def bound_map(item: dict) -> dict | None:
    """The hashes stored when a program was kept, or None when they are absent."""
    raw = item.get("bound")
    if not isinstance(raw, dict):
        return None
    evidence = raw.get("evidence")
    script = str(raw.get("script") or "")
    repro = str(raw.get("repro") or "")
    if not isinstance(evidence, dict) or not evidence:
        return None
    if not _hex64(script) or not _hex64(repro):
        return None
    if any(not _hex64(str(value)) for value in evidence.values()):
        return None
    return raw


def snapshot(repo: Path, item: dict, repro: str) -> dict:
    """Pin the script and the results to the bytes that were actually verified."""
    evidence = {
        rel: file_hash(repo / rel)
        for rel in result_evidence(item)
    }
    return {
        "script": file_hash(repo / str(item.get("script"))),
        "evidence": evidence,
        "repro": file_hash(repo / repro),
    }


def drift_of(repo: Path, item: dict) -> list[str]:
    """Kept files that are no longer the bytes pinned at transform."""
    if str(item.get("status")) != "kept":
        return []
    bound = bound_map(item)
    if bound is None:
        return []
    lid = str(item.get("id", "?"))
    lines = []
    script = str(item.get("script") or "")
    if stored_file(repo, script) and file_hash(repo / script) != bound["script"]:
        lines.append(f"{lid}: 脚本已不是留下时的那一份")
    pinned = bound["evidence"]
    for rel in result_evidence(item):
        if rel not in pinned:
            lines.append(f"{lid}: {rel} 留下时没有钉住")
        elif stored_file(repo, rel) and file_hash(repo / rel) != str(pinned[rel]):
            lines.append(f"{lid}: {rel} 已不是留下时的那一份")
    repro = str(item.get("repro") or "")
    if repro and stored_file(repo, repro) and file_hash(repo / repro) != bound["repro"]:
        lines.append(f"{lid}: 复现已不是留下时的那一份")
    return lines


def evolution_block(repo: Path, item: dict, counted: list[str]) -> str:
    """A changed script still backed only by the old results is not a new capability."""
    if str(item.get("status")) != "kept":
        return ""
    bound = bound_map(item)
    if bound is None:
        return ""
    script = str(item.get("script") or "")
    if not stored_file(repo, script) or file_hash(repo / script) == bound["script"]:
        return ""
    old = {str(value) for value in bound["evidence"].values()}
    if any(file_hash(repo / rel) not in old for rel in counted):
        return ""
    return "脚本变了还用原来的结果，一次修改还不是演化"


def accept_file(repo: Path, raw: str, *, script: bool = False) -> tuple[str, str]:
    """Return a repo-relative path, or an error. Does not follow a link outside."""
    text = str(raw or "").strip()
    if not text:
        return "", "缺路径"
    given = Path(text)
    if ".." in given.parts:
        return "", f"{text} 含 .."
    path = given if given.is_absolute() else repo / given
    try:
        resolved = path.resolve()
        rel = resolved.relative_to(repo).as_posix()
    except ValueError:
        return "", f"{text} 不在仓库里"
    if not resolved.is_file():
        return "", f"{text} 不是文件"
    if resolved.stat().st_size <= 0:
        return "", f"{text} 是空文件"
    if script:
        if resolved.name in FORBIDDEN_NAMES or resolved.suffix not in SCRIPT_SUFFIXES:
            return "", f"{text} 不能当程序。只登记已有的 .py 或 .sh，不写提示词"
    return rel, ""


def stored_file(repo: Path, rel: str) -> bool:
    """True when a path already stored in the ledger still names a non-empty file."""
    text = str(rel or "").strip()
    if not text or text.startswith("/") or ".." in Path(text).parts:
        return False
    path = (repo / text).resolve()
    try:
        path.relative_to(repo)
    except ValueError:
        return False
    return path.is_file() and path.stat().st_size > 0


def draft_repro_error(repo: Path, item: dict, repro: str) -> str:
    """The result that keeps an entry must be a run the draft did not already use."""
    text = str(repro or "").strip()
    if not text:
        return ""
    script = str(item.get("script") or "").strip()
    drafts = result_evidence(item)
    if text == script:
        return "留下用的复现不能是脚本本身"
    if text in drafts:
        return "留下用的复现不能是起草时已经用过的那一份"
    if not stored_file(repo, text):
        return ""
    repro_hash = file_hash(repo / text)
    for rel in drafts:
        if stored_file(repo, rel) and file_hash(repo / rel) == repro_hash:
            return "复现和起草证据内容相同，还不是另一份结果"
    return ""


def result_evidence(item: dict) -> list[str]:
    """Evidence paths that count as results. The script file itself does not."""
    script = str(item.get("script") or "")
    out: list[str] = []
    for rel in safeyaml.as_list(item.get("evidence")):
        text = str(rel or "").strip()
        if text and text != script and text not in out:
            out.append(text)
    return out


def hashes_clash(repo: Path, rels: list[str]) -> bool:
    """True when every path exists and two of them are the same bytes."""
    if len(rels) < 2:
        return False
    hashes = []
    for rel in rels:
        path = repo / rel
        if not stored_file(repo, rel):
            return False
        hashes.append(file_hash(path))
    return len(set(hashes)) < len(hashes)


def missing_paths(repo: Path, item: dict) -> list[str]:
    rels: list[str] = []
    for rel in safeyaml.as_list(item.get("evidence")):
        rels.append(str(rel))
    if str(item.get("repro") or "").strip():
        rels.append(str(item.get("repro")))
    if str(item.get("form")) == "program" and str(item.get("script") or "").strip():
        rels.append(str(item.get("script")))
    missing = []
    for rel in rels:
        if rel not in missing and not stored_file(repo, rel):
            missing.append(rel)
    return missing


def script_ok(rel: str) -> bool:
    text = str(rel or "").strip()
    if not text or text.startswith("/") or ".." in Path(text).parts:
        return False
    path = Path(text)
    return path.name not in FORBIDDEN_NAMES and path.suffix in SCRIPT_SUFFIXES


def entry_errors(item: dict, repo: Path) -> list[str]:
    """Hard errors. Missing files are reported by gc, not here."""
    lid = str(item.get("id", "?"))
    errors = []
    status = str(item.get("status", ""))
    form = str(item.get("form", ""))
    trust = str(item.get("trust", ""))
    if status not in STATUS:
        errors.append(f"{lid}: status={status!r} 不在 {'/'.join(STATUS)} 里")
    if form not in FORM:
        errors.append(f"{lid}: form={form!r} 不在 {'/'.join(FORM)} 里")
    if trust not in TRUST:
        errors.append(f"{lid}: trust={trust!r} 不在 {'/'.join(TRUST)} 里")
    for field in TEXT:
        if not str(item.get(field) or "").strip():
            errors.append(f"{lid}: 缺 {field} —— {TEXT_Q[field]}")
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{lid}: 缺证据。没有结果文件的记录无法再验")
    elif any(not str(x or "").strip() for x in evidence):
        errors.append(f"{lid}: 证据里有空路径")
    script = str(item.get("script") or "").strip()
    if form != "program":
        errors.append(f"{lid}: 事实和判断不在这本账。{FORM_WHY.get(form, form)}")
    elif not script:
        errors.append(f"{lid}: program 没有 script。本命令不生成脚本")
    elif not script_ok(script):
        errors.append(f"{lid}: script={script!r} 不能当程序。只登记已有的 .py 或 .sh")
    if trust != "reviewed":
        errors.append(f"{lid}: 外部内容不能写成程序")
    if status == "kept":
        if trust != "reviewed":
            errors.append(f"{lid}: 外部内容不能留下")
        if len(result_evidence(item)) < 2:
            errors.append(f"{lid}: 一次成功还不是能力")
        if not workflow_spec.is_human(str(item.get("confirmed_by", ""))):
            errors.append(
                f"{lid}: kept 但 confirmed_by={item.get('confirmed_by')!r} 不是人"
            )
        repro = str(item.get("repro") or "").strip()
        if not repro:
            errors.append(f"{lid}: kept 但没有 repro")
        else:
            clash = draft_repro_error(repo, item, repro)
            if clash:
                errors.append(f"{lid}: {clash}")
        counted = result_evidence(item)
        if len(counted) >= 2 and hashes_clash(repo, counted):
            errors.append(f"{lid}: 两条证据内容相同，还是一次成功")
        if bound_map(item) is None:
            errors.append(f"{lid}: 留下时没有钉住字节")
        else:
            errors.extend(drift_of(repo, item))
    if status == "retired" and not str(item.get("retired_why") or "").strip():
        errors.append(f"{lid}: retired 却没写 retired_why")
    return errors


def gc_lines(repo: Path, items: list) -> list[str]:
    """Name redundant, stale, and single-result entries. Do not change them."""
    live = [x for x in items if str(x.get("status")) != "retired"]
    lines = []
    for i, left in enumerate(live):
        left_id = str(left.get("id", "?"))
        left_key = (_norm(str(left.get("form"))), _norm(str(left.get("scope"))))
        left_claim = _norm(str(left.get("claim")))
        for right in live[i + 1 :]:
            right_id = str(right.get("id", "?"))
            right_key = (_norm(str(right.get("form"))), _norm(str(right.get("scope"))))
            right_claim = _norm(str(right.get("claim")))
            if left_key != right_key or not left_claim or not right_claim:
                continue
            if left_claim == right_claim:
                lines.append(f"GC duplicate {right_id} 与 {left_id} 同文")
            elif len(left_claim) >= 12 and len(right_claim) >= 12:
                if left_claim in right_claim:
                    lines.append(f"GC overlap {left_id} 含于 {right_id}")
                elif right_claim in left_claim:
                    lines.append(f"GC overlap {right_id} 含于 {left_id}")
        gone = missing_paths(repo, left)
        if gone:
            lines.append(f"GC stale {left_id} 证据不在 {gone[0]}")
        if str(left.get("status")) == "candidate" and len(result_evidence(left)) == 1:
            lines.append(f"GC single {left_id} 只有一条证据，一次成功还不是能力")
        for msg in drift_of(repo, left):
            lines.append("GC drift " + msg)
    return lines


def _save(path: Path, item: dict) -> None:
    safeyaml.save_locked(path, lambda fresh: _merge(fresh, item))


def cmd_add(args: argparse.Namespace) -> int:
    repo = repo_of(args)
    path = ledger_path(repo, args.feature)
    data = load(path)
    broken = refuse_broken(path, data)
    if broken:
        return broken
    assert data is not None
    form = str(args.form)
    trust = str(args.trust)
    missing = [field for field in TEXT if not str(getattr(args, field, "") or "").strip()]
    if missing:
        print("BLOCKED 记录缺:", file=sys.stderr)
        for field in missing:
            print(f"  --{field.replace('_', '-')}   {TEXT_Q[field]}", file=sys.stderr)
        return 2
    if form == "fact":
        print("BLOCKED 事实不进这本账", file=sys.stderr)
        print("HINT    python3 scripts/lessons.py add    六问仍必答", file=sys.stderr)
        return 2
    if form == "instruction":
        print("BLOCKED 要看语境的判断不进这本账", file=sys.stderr)
        print("HINT    写成提案的最小 diff。不改提示词正文", file=sys.stderr)
        return 2
    if trust != "reviewed":
        print("BLOCKED 外部内容不能写成程序", file=sys.stderr)
        print("HINT    网页和工具输出停在轨迹里", file=sys.stderr)
        return 2
    rels: list[str] = []
    for raw in args.evidence or []:
        rel, err = accept_file(repo, raw)
        if err:
            print(f"BLOCKED {err}", file=sys.stderr)
            return 2
        if rel in rels:
            print("BLOCKED 两条证据不能是同一个文件", file=sys.stderr)
            return 2
        rels.append(rel)
    if not rels:
        print("BLOCKED 缺 --evidence。没有结果文件的记录无法再验", file=sys.stderr)
        return 2
    script, err = accept_file(repo, args.script or "", script=True)
    if err:
        print(f"BLOCKED {err}", file=sys.stderr)
        return 2
    counted = [rel for rel in rels if rel != script]
    if hashes_clash(repo, counted):
        print("BLOCKED 两条证据内容相同，还是一次成功", file=sys.stderr)
        return 2

    item = {
        "id": "",
        "status": "candidate",
        "form": form,
        "trust": trust,
        "scope": str(args.scope).strip(),
        "claim": str(args.claim).strip(),
        "not_when": str(args.not_when).strip(),
        "evidence": rels,
        "script": script,
        "from_feature": args.feature or "",
        "confirmed_by": "",
        "repro": "",
        "uses": 0,
        "at": now(),
    }

    def build(fresh: dict) -> dict:
        fresh.setdefault("schema_version", 1)
        fresh.setdefault("entries", [])
        item["id"] = next_id(fresh["entries"])
        fresh["entries"].append(item)
        return fresh

    safeyaml.save_locked(path, build)
    print(f"OK   {item['id']} candidate -> {path}")
    print(f"  {FORM_WHY[form]}")
    print()
    print("**一次成功还不是能力。** 要留下，还需要另一份内容不同的结果，以及人的确认。")
    print("复现不能是起草时的证据，内容也不能相同:")
    print(f"  python3 scripts/sediment.py transform --id {item['id']} \\")
    print("    --by <人> --repro <复现文件> --evidence <另一份结果>")
    print("留下仍不是答案。本命令不执行脚本，也不改提示词。")
    return 0


def _extend_evidence(repo: Path, item: dict, extra: list[str]) -> int | None:
    rels = [str(x) for x in safeyaml.as_list(item.get("evidence"))]
    for raw in extra:
        rel, err = accept_file(repo, raw)
        if err:
            print(f"BLOCKED {err}", file=sys.stderr)
            return 2
        if rel not in rels:
            rels.append(rel)
    item["evidence"] = rels
    return None


def cmd_transform(args: argparse.Namespace) -> int:
    repo = repo_of(args)
    path = ledger_path(repo, args.feature)
    data = load(path)
    broken = refuse_broken(path, data)
    if broken:
        return broken
    assert data is not None
    item = find(entries_of(data), args.id)
    if item is None:
        print(f"BLOCKED no such entry: {args.id}", file=sys.stderr)
        return 2
    if str(item.get("status")) == "retired":
        print(f"BLOCKED {item.get('id')} 已清掉。要留下就另记一条", file=sys.stderr)
        return 2
    if str(item.get("form")) != "program":
        print("BLOCKED 这本账只留下程序", file=sys.stderr)
        return 2
    if str(item.get("trust")) != "reviewed":
        print("BLOCKED 外部内容不能留下", file=sys.stderr)
        print("HINT    人审过之后另记一条 --trust reviewed", file=sys.stderr)
        return 2
    failed = _extend_evidence(repo, item, list(args.evidence or []))
    if failed:
        return failed
    if not workflow_spec.is_human(args.by):
        print(
            f"BLOCKED confirmed_by={args.by!r} 不是人 —— 模型确认自己的结论不叫确认",
            file=sys.stderr,
        )
        return 2
    repro, err = accept_file(repo, args.repro or "")
    if err:
        print(f"BLOCKED {err}", file=sys.stderr)
        return 2
    counted = result_evidence(item)
    if len(counted) < 2:
        print("BLOCKED 一次成功还不是能力", file=sys.stderr)
        script = str(item.get("script") or "")
        if script and script in safeyaml.as_list(item.get("evidence")):
            print("  脚本本身不算一次结果", file=sys.stderr)
        print("HINT    再给一份内容不同的 --evidence", file=sys.stderr)
        return 2
    for rel in counted:
        if not stored_file(repo, rel):
            print(f"BLOCKED {rel} 证据不在", file=sys.stderr)
            return 2
    if hashes_clash(repo, counted):
        print("BLOCKED 两条证据内容相同，还是一次成功", file=sys.stderr)
        return 2
    clash = draft_repro_error(repo, item, repro)
    if clash:
        print(f"BLOCKED {clash}", file=sys.stderr)
        return 2
    if str(item.get("form")) == "program":
        script = str(item.get("script") or "")
        if not script_ok(script) or not stored_file(repo, script):
            print("BLOCKED 程序要指向仓库里已经存在的 .py 或 .sh", file=sys.stderr)
            return 2
    if str(item.get("status")) == "kept" and bound_map(item) is None:
        print("BLOCKED 留下时没有钉住字节。改过的账不能在原地补钉，另记一条", file=sys.stderr)
        return 2
    moved = evolution_block(repo, item, counted)
    if moved:
        print(f"BLOCKED {moved}", file=sys.stderr)
        print("HINT    再给一份内容不同的 --evidence", file=sys.stderr)
        return 2
    item["status"] = "kept"
    item["confirmed_by"] = args.by
    item["repro"] = repro
    item["bound"] = snapshot(repo, item, repro)
    item["at"] = now()
    _save(path, item)
    print(f"OK   {item['id']} kept (by {args.by}) -> {path}")
    print()
    print("留下仍是**记录、建议或脚本位置**，不是答案。")
    print("字节已钉住。脚本再改，原来的结果不能把它重新留下。")
    print("本命令没有执行脚本，也没有改提示词。")
    return 0


def cmd_retire(args: argparse.Namespace) -> int:
    repo = repo_of(args)
    path = ledger_path(repo, args.feature)
    data = load(path)
    broken = refuse_broken(path, data)
    if broken:
        return broken
    assert data is not None
    item = find(entries_of(data), args.id)
    if item is None:
        print(f"BLOCKED no such entry: {args.id}", file=sys.stderr)
        return 2
    if not str(args.why or "").strip():
        print("BLOCKED 缺 --why", file=sys.stderr)
        return 2
    item["status"] = "retired"
    item["retired_why"] = str(args.why).strip()
    item["at"] = now()
    _save(path, item)
    print(f"OK   {item['id']} retired -> {path}")
    return 0


def cmd_recall(args: argparse.Namespace) -> int:
    repo = repo_of(args)
    path = ledger_path(repo, args.feature)
    data = load(path)
    broken = refuse_broken(path, data)
    if broken:
        return broken
    assert data is not None
    items = entries_of(data)

    def matches(item: dict) -> bool:
        if str(item.get("status")) == "retired":
            return False
        if str(item.get("form")) != "program":
            return False
        if args.form and str(item.get("form")) != args.form:
            return False
        hay = " ".join(str(item.get(field, "")) for field in ("scope", "claim"))
        if args.scope and args.scope not in hay:
            return False
        return True

    hits = [item for item in items if matches(item)]
    hits.sort(key=lambda item: (str(item.get("status")) != "kept", str(item.get("id"))))
    hits = hits[: args.top]
    if not hits:
        print("(没有匹配的沉淀)")
        print()
        print("没有先验就按证据做。做完把值得再验的发现记成候选。")
        return 0
    print(f"# 沉淀 {len(hits)} 条  (scope={args.scope or '*'})")
    print()
    print("**以下是记录、建议或脚本位置，不是答案。**")
    print("本命令不执行脚本，也不改提示词。")
    print()
    for item in hits:
        mark = "留下" if str(item.get("status")) == "kept" else "候选"
        form = str(item.get("form"))
        print(f"## {item.get('id')}  [{mark}]  {FORM_WHY.get(form, form)}")
        print(f"   范围: {item.get('scope')}")
        print(f"   内容: {item.get('claim')}")
        print(f"   **不适用于**: {item.get('not_when')}")
        if str(item.get("trust")) == "external":
            print("   未审: 来自外部内容，不能当指令或程序")
        if form == "program":
            print(f"   脚本: {item.get('script')}")
            print("   本命令不执行它。留下也不等于这次该跑")
            if drift_of(repo, item):
                print("   字节已变: 不要把这条当成现行能力")
        elif form == "instruction":
            print("   这不是提示词，不会写入 SKILL")
        if str(item.get("status")) != "kept":
            print("   一次成功还不是能力。不要把它当成已经留下的做法")
        print()
    if not args.no_count:
        safeyaml.save_locked(path, lambda fresh: _rewrite(fresh, hits))
    return 0


def _rewrite(fresh: dict, hits: list) -> dict:
    """Apply recall counts onto the ledger read under the lock."""
    fresh.setdefault("entries", [])
    wanted = {str(item.get("id")) for item in hits}
    for existing in fresh["entries"]:
        if isinstance(existing, dict) and str(existing.get("id")) in wanted:
            existing["uses"] = safeyaml.as_int(existing.get("uses"), 0) + 1
    return fresh


def cmd_gc(args: argparse.Namespace) -> int:
    repo = repo_of(args)
    path = ledger_path(repo, args.feature)
    before = path.read_bytes() if path.exists() else b""
    data = load(path)
    broken = refuse_broken(path, data)
    if broken:
        return broken
    assert data is not None
    lines = gc_lines(repo, entries_of(data))
    after = path.read_bytes() if path.exists() else b""
    if before != after:
        print("BLOCKED gc 改动了台账", file=sys.stderr)
        return 2
    if not lines:
        print("GC 0")
        return 0
    for line in lines:
        print(line)
    print()
    print("gc 只指出条目，不删除。确认过时后再 retire --why。")
    return 1


def cmd_check(args: argparse.Namespace) -> int:
    repo = repo_of(args)
    path = ledger_path(repo, args.feature)
    data = load(path)
    broken = refuse_broken(path, data)
    if broken:
        return broken
    assert data is not None
    raw = safeyaml.as_list(data.get("entries"))
    items = entries_of(data)
    errors = [f"内部不一致 — {item}" for item in pair_check()]
    if len(items) != len(raw):
        errors.append("有条目不是记录")
    seen: set[str] = set()
    for item in items:
        lid = str(item.get("id", ""))
        if not lid:
            errors.append("有条目没有 id")
        elif lid in seen:
            errors.append(f"{lid}: id 重复")
        else:
            seen.add(lid)
        errors.extend(entry_errors(item, repo))
    for line in gc_lines(repo, items):
        if line.startswith("GC drift "):
            continue
        print("WARN " + line, file=sys.stderr)
    used = [
        item
        for item in items
        if str(item.get("status")) == "candidate" and safeyaml.as_int(item.get("uses"), 0) >= 3
    ]
    for item in used:
        print(
            f"WARN {item.get('id')}: 候选被召回 {item.get('uses')} 次却还没留下或清掉",
            file=sys.stderr,
        )
    if errors:
        for err in errors:
            print("FAIL " + err, file=sys.stderr)
        return 1
    kept = sum(1 for item in items if str(item.get("status")) == "kept")
    cand = sum(1 for item in items if str(item.get("status")) == "candidate")
    print(f"sediment PASS {len(items)} 条({kept} 留下 / {cand} 候选)")
    print()
    print("**台账干净 ≠ 这些做法是对的。** 这里只查门禁有没有被绕过。")
    print("召回仍不是答案。本检查不执行脚本。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--feature", help="票内台账;不给则用内核级 state/sediment.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    schema = sub.add_parser("schema")
    schema.set_defaults(fn=lambda a: (print(SCHEMA), 0)[1])

    add = sub.add_parser("add", help="记一条候选")
    add.add_argument("--form", choices=FORM, required=True)
    add.add_argument("--trust", choices=TRUST, required=True)
    for field in TEXT:
        add.add_argument(f"--{field.replace('_', '-')}", dest=field)
    add.add_argument("--evidence", action="append", default=[])
    add.add_argument("--script", default="")
    add.set_defaults(fn=cmd_add)

    transform = sub.add_parser("transform", help="两条不同结果且经人确认后留下")
    transform.add_argument("--id", required=True)
    transform.add_argument("--by", required=True)
    transform.add_argument("--repro", required=True)
    transform.add_argument("--evidence", action="append", default=[])
    transform.set_defaults(fn=cmd_transform)

    retire = sub.add_parser("retire", help="过时就清")
    retire.add_argument("--id", required=True)
    retire.add_argument("--why", required=True)
    retire.set_defaults(fn=cmd_retire)

    recall = sub.add_parser("recall", help="召回记录、建议或脚本位置")
    recall.add_argument("--scope")
    recall.add_argument("--form", choices=FORM)
    recall.add_argument("--top", type=int, default=5)
    recall.add_argument("--no-count", action="store_true")
    recall.set_defaults(fn=cmd_recall)

    gc = sub.add_parser("gc", help="指出重复、包含、失效和只有一条证据的条目")
    gc.set_defaults(fn=cmd_gc)

    check = sub.add_parser("check", help="台账自检")
    check.set_defaults(fn=cmd_check)

    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
