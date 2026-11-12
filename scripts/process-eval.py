#!/usr/bin/env python3
"""Judge a process step before it costs a person a turn.

    python3 scripts/process-eval.py stop --stop "请确认实现审核"
    python3 scripts/process-eval.py stop --quote "验收" --stop ""
    python3 scripts/process-eval.py scan --traces <dir> [--propose]

now=CORRECT follows a rule that is already written. later=PROPOSE writes a
draft only with --propose. This command does not edit SKILL.md, does not
score, and does not treat a model name as evidence that a step can go.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import workflow_spec as w  # noqa: E402

NON_STOPS = (
    "审查签收",
    "实现审核",
    "测试结果确认",
    "文档定稿",
    "要不要继续",
    "是否继续",
    "请确认通过",
    "要不要提测",
    "是否验收",
    "请验收",
    "请确认一下",
    "是否没问题",
    "可以继续吗",
    "要不要推进",
    "是否对齐",
    "确认一下方案",
    "可以吗",
    "没问题吧",
    "继续吗",
    "这样可以吗",
    "先这样吧",
    "请审核一下",
    "麻烦确认",
    "看下可以吗",
    "帮确认一下",
    "是否可行",
    "这样行吗",
    "帮看下",
    "瞅一眼",
    "过一下",
    "走个确认",
    "确认下",
    "再确认",
    "最后确认一下",
    "顺便确认",
)
# Never auto-decide. Single source: scripts/lib/drive_mode.HARD_HOLDS.
try:
    from drive_mode import HARD_HOLDS  # noqa: WPS433
except ImportError:  # pragma: no cover
    HARD_HOLDS = (
        "解封",
        "解除密封",
        "启封",
        "开封",
        "unseal",
        "打开基线",
        "重新打开基线",
        "打開基線",
        "重新打開基線",
        "reopen",
        "回退",
        "回滚",
        "rollback",
        "roll back",
        "promote",
        "生产写",
        "写入生产",
        "写生产",
        "上生产",
        "上线生产",
        "生产发布",
        "发布到生产",
        "生产变更",
        "write to production",
        "production write",
        "deploy to production",
        "生產寫",
        "寫入生產",
        "寫生產",
        "上生產",
        "上線生產",
        "生產發布",
        "發布到生產",
        "生產變更",
        "git push",
        "经验入库",
        "經驗入庫",
    )
# B-class / cognitive forks. Auto mode may adopt --recommend.
SOFT_HOLDS = (
    "矛盾",
    "冲突",
    "衝突",  # traditional
    "不清楚",
    "frontier",
    "BLOCKED",
    "ARTIFACT",
    "SIGNAL",
    "baseline-conflict",
    "baseline_conflict",  # underscore form of the same token
    "baseline conflict",  # spaced form
    "未决",
    "未決",  # traditional
    "承重",
)
HOLDS = HARD_HOLDS + SOFT_HOLDS
MEMORY_MARKERS = ("没读", "未读", "未打开", "重读", "must_read", "忘记", "忘了")
PROPOSE_AT = 2
CLOSED = {"landed", "archived", "rejected", "ga"}
DO = {
    "rubber-proceed": "做当前阶段还开着的事。不改密封基线的 goal、items、non_goal。不记 stop，不写 next。",
    "leave-decision": "决策保持开着。做不依赖它的那一步。这句不是批准。",
    "ask-known": "按既有规则把这一步做完。检查没过就改到通过。不问人确认。",
    "drive-auto": "采纳推荐并 decide --all-open --source auto --quote auto:recommend；by 写编制真人。不停问。",
    "drive-need-recommend": (
        "先写出推荐选项与理由，再带 --recommend 重跑 process-eval；"
        "或在回报盖 RECOMMEND: / AI 建议: / AI建議: <档>；"
        "PASS 且仅 [承重] 时可默认档 1。不要空手停问。"
    ),
    "ask": "停下来问。",
    "none": "没有要判断的停问。",
    "propose": "只起草提案。不改 Skill。起草用过的轨迹不能当接受证据。",
}
CHANGE = {
    "ask-known": "删掉仍把审查签收、实现审核、测试结果确认、文档定稿或催办式提问当成停点的句子。",
    "rubber-proceed": "找出仍把催办记成 stop 或 next 的写入点。",
    "stop-on-nudge": "删掉上游仍要求人说继续才往下走的句子。",
    "context-replay": "失败原因不是没读文件时，不要把原文整段重放进委派包。",
}


def unquote(value: str) -> str:
    value = value.strip()
    if value in {">", "|", ">-", "|-", ">+", "|+", "~", "null", "''", '""'}:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def top_field(text: str, key: str) -> str:
    """A column-0 scalar. A block scalar is joined; nested keys are ignored."""
    lines = text.splitlines()
    markers = {">", "|", ">-", "|-", ">+", "|+"}
    for index, line in enumerate(lines):
        match = re.match(rf"^{re.escape(key)}:\s*(.*)$", line)
        if match is None:
            continue
        raw = match.group(1).strip()
        if raw not in markers:
            return unquote(raw)
        body = []
        for follow in lines[index + 1:]:
            if follow.strip() == "":
                body.append("")
                continue
            if follow[:1] not in " \t":
                break
            body.append(follow.strip())
        return "\n".join(body).strip()
    return ""


def child_block(text: str, key: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not re.match(rf"^{re.escape(key)}:\s*$", line):
            continue
        body = []
        for follow in lines[index + 1:]:
            if follow.strip() == "":
                body.append(follow)
                continue
            if follow[0] not in " \t":
                break
            body.append(follow)
        return "\n".join(body)
    return ""


def indented_field(text: str, key: str) -> str:
    match = re.search(rf"(?m)^[ \t]+{re.escape(key)}:\s*(.*)$", text)
    return unquote(match.group(1)) if match else ""


def hard_held(*parts: str) -> bool:
    try:
        import drive_mode  # noqa: WPS433

        return drive_mode.hard_held(*parts)
    except Exception:
        blob = "\n".join(str(p or "") for p in parts)
        return any(mark in blob for mark in HARD_HOLDS)


def soft_held(*parts: str) -> bool:
    """True when a soft-hold marker appears.

    ASCII markers (frontier, BLOCKED, SIGNAL, …) match as whole phrases,
    case-insensitively after stripping English negation (no BLOCKED).
    CJK markers stay exact substring after stripping negation+mark
    (不矛盾 / 无需冲突 / 不涉及冲突 do not soft-hold;「不清楚」itself still does).
    """
    import re

    try:
        import drive_mode  # noqa: WPS433

        strip = drive_mode._strip_hold_negations  # noqa: SLF001
    except Exception:
        def strip(blob: str, marks: tuple[str, ...] | list[str]) -> str:
            # Last-resort mirror of drive_mode._strip_hold_negations (CJK only).
            import re as _re
            import unicodedata as _ud

            cleaned = _ud.normalize("NFKC", str(blob or ""))
            cleaned = _re.sub("[\u200b\u200c\u200d\u2060\ufeff\u00ad]", "", cleaned)
            cleaned = cleaned.translate(str.maketrans({
                "開": "开", "線": "线", "產": "产", "寫": "写", "發": "发",
                "經": "经", "驗": "验", "庫": "库", "衝": "冲", "決": "决",
                "議": "议", "無": "无", "沒": "没", "該": "该", "應": "应",
                "別": "别", "於": "于", "會": "会", "辦": "办", "絕": "绝",
                "對": "对", "過": "过", "並": "并", "緩": "缓", "遲": "迟",
                "後": "后", "暫": "暂", "滾": "滚",
            }))
            cleaned = _re.sub(
                r"(?<=[^\x00-\x7F])\s+(?=[^\x00-\x7F])",
                "",
                cleaned,
            )
            prefixes = (
                "不涉及", "不需要", "无需再", "永不再", "并不是", "没办法",
                "沒辦法", "用不着", "犯不着", "不至于", "不至於", "禁止", "避免",
                "拒绝", "反对",
                "取消", "跳过", "忽略", "切莫", "莫要", "暂缓", "推迟", "延后",
                "无法", "無法", "无需", "無需", "无须", "無須", "毋须", "毋庸",
                "未尝", "不用", "不必", "不要", "不会", "不會", "不再", "不是",
                "不该", "不該", "不应", "不應", "不宜", "不可", "未能",
                "未曾", "未有", "没有", "沒有", "没法", "沒法", "永不",
                "不", "无", "無", "勿", "别", "別", "非", "未", "没", "沒",
                "莫", "慎", "拒",
            )
            for mark in sorted(
                (m for m in marks if not str(m).isascii()),
                key=len,
                reverse=True,
            ):
                for prefix in prefixes:
                    phrase = prefix + mark
                    if not (prefix.startswith("不") and len(prefix) >= 2):
                        cleaned = cleaned.replace(phrase, "")
                        continue
                    parts: list[str] = []
                    idx = 0
                    while True:
                        pos = cleaned.find(phrase, idx)
                        if pos < 0:
                            parts.append(cleaned[idx:])
                            break
                        if (
                            pos > 0
                            and pos + 1 < len(cleaned)
                            and cleaned[pos - 1] == cleaned[pos + 1]
                        ):
                            parts.append(cleaned[idx : pos + len(phrase)])
                            idx = pos + len(phrase)
                            continue
                        parts.append(cleaned[idx:pos])
                        idx = pos + len(phrase)
                    cleaned = "".join(parts)
            return cleaned

    blob = "\n".join(str(p or "") for p in parts)
    cleaned = strip(blob, SOFT_HOLDS)
    for mark in SOFT_HOLDS:
        if not mark.isascii():
            if mark in cleaned:
                return True
            continue
        try:
            import drive_mode as _dm  # noqa: WPS433

            pat = _dm._ascii_mark_pattern(mark)  # noqa: SLF001
        except Exception:
            pat = r"(?i)\b" + re.escape(mark) + r"\b"
        if re.search(pat, cleaned):
            return True
    return False


def held(*parts: str) -> bool:
    return hard_held(*parts) or soft_held(*parts)


def ask_known(text: str) -> bool:
    return any(phrase in text for phrase in NON_STOPS)


def blank(value: str) -> str:
    value = str(value or "").strip()
    return "" if value in {"-", "无", "none", "null"} else value


def finding(fid: str, kind: str, now: str, later: str, rule: str, count: int,
            evidence: str, fires: int = 0, failures: int = 0,
            remove: str = "", keep: str = "") -> dict:
    return {
        "id": fid,
        "kind": kind,
        "now": now,
        "later": later,
        "rule": rule,
        "count": count,
        "fires": fires,
        "failures": failures,
        "evidence": evidence or "-",
        "remove": remove,
        "keep": keep,
    }


def judge_stop(
    quote: str,
    stop: str,
    nxt: str,
    signals: str,
    decision: bool,
    drive: str = "assisted",
    recommend: str = "",
) -> dict:
    quote, stop, nxt, signals = blank(quote), blank(stop), blank(nxt), blank(signals)
    recommend = blank(recommend)
    drive = str(drive or "assisted").strip().lower() or "assisted"
    parts = (quote, stop, nxt, signals)
    if hard_held(*parts):
        return finding("real-hold", "keep", "ASK", "", "chat-confirm", 1, "-")
    # Decision gates (push / evolve land) never auto — same as assisted.
    if decision:
        if quote and w.is_nudge(quote) and not w.is_answer(quote):
            return finding("leave-decision", "waste", "CORRECT", "", "H1", 1, "-")
        return finding("decision-gate", "keep", "ASK", "", "chat-confirm", 1, "-")
    # Auto: soft holds, or any stop written as a cognitive fork, with recommend.
    if drive == "auto" and soft_held(*parts):
        if recommend:
            return finding("drive-auto", "keep", "CORRECT", "", "drive-auto", 1, recommend)
        return finding("drive-need-recommend", "keep", "ASK", "", "drive-auto", 1, "-")
    if soft_held(*parts) or held(*parts):
        return finding("real-hold", "keep", "ASK", "", "chat-confirm", 1, "-")
    if quote and w.is_nudge(quote):
        return finding("rubber-proceed", "waste", "CORRECT", "", "H1", 1, "-")
    if quote and w.nudge_kind(quote) == "named":
        return finding("named", "keep", "ASK", "", "chat-confirm", 1, "-")
    if quote and w.nudge_kind(quote) == "reply":
        return finding("reply", "keep", "ASK", "", "chat-confirm", 1, "-")
    if quote and w.nudge_kind(quote) == "work":
        return finding("work", "keep", "ASK", "", "chat-confirm", 1, "-")
    if not quote and ask_known(stop):
        return finding("ask-known", "unreasonable", "CORRECT", "", "chat-confirm", 1, "-")
    # Auto + recommend on a plain stop (no person quote) = adopt, don't ask.
    if drive == "auto" and recommend and stop and not quote:
        return finding("drive-auto", "keep", "CORRECT", "", "drive-auto", 1, recommend)
    if stop or quote:
        return finding("unclassified", "keep", "ASK", "", "chat-confirm", 1, "-")
    return finding("none", "keep", "KEEP", "", "", 0, "-")


def read_trace(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    invoke = child_block(text, "invoke")
    return {
        "name": path.name,
        "feature": top_field(text, "feature"),
        "trigger": indented_field(invoke, "trigger") or top_field(text, "trigger"),
        "stop": top_field(text, "stop"),
        "next": top_field(text, "next"),
    }


def names(rows: list[dict], limit: int = 12) -> str:
    got = [row["name"] for row in rows]
    if len(got) <= limit:
        return ",".join(got)
    return ",".join(got[:limit]) + ",+%d" % (len(got) - limit)


def load_scaffolds(path: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    current: dict | None = None
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if re.match(r"^\s+-\s+id:\s*", line):
            current = {"id": unquote(line.split(":", 1)[1])}
            found[current["id"]] = current
            continue
        if current is None:
            continue
        match = re.match(r"^\s+([A-Za-z0-9_]+):\s*(.*)$", line)
        if match:
            current[match.group(1)] = unquote(match.group(2))
    return found


def scaffold_spec(table: dict[str, dict], fid: str) -> dict:
    spec = table.get(fid, {})
    try:
        fires = int(spec.get("min_fires") or PROPOSE_AT)
    except ValueError:
        fires = PROPOSE_AT
    return {
        "min_fires": fires,
        "remove": spec.get("remove") or CHANGE.get(fid, ""),
        "keep": spec.get("keep") or "",
    }


def judge_traces(rows: list[dict], table: dict[str, dict]) -> tuple[list[dict], list[str]]:
    findings = []
    unproven = []
    bad = [row for row in rows if w.is_nudge(row["trigger"]) and w.nudge_errors(row["trigger"], row["stop"], row["next"])]
    if bad:
        later = "PROPOSE" if len(bad) >= PROPOSE_AT else ""
        findings.append(finding(
            "rubber-proceed", "waste", "", later, "H1", len(bad), names(bad),
            remove=CHANGE["rubber-proceed"], keep="nudge 校验不放宽",
        ))
    asked = [row for row in rows if ask_known(row["stop"]) and not held(row["stop"], row["next"])]
    if asked:
        later = "PROPOSE" if len(asked) >= PROPOSE_AT else ""
        findings.append(finding(
            "ask-known", "unreasonable", "", later, "chat-confirm", len(asked), names(asked),
            remove=CHANGE["ask-known"], keep="矛盾、冲突、不清楚和点名动作仍要停",
        ))
    spec = scaffold_spec(table, "stop-on-nudge")
    fires = []
    failures = 0
    for prev, cur in zip(rows, rows[1:]):
        if prev["feature"] != cur["feature"] or not w.is_nudge(cur["trigger"]):
            continue
        if not blank(prev["stop"]) or held(prev["stop"], prev["next"]):
            continue
        fires.append(cur)
        if w.nudge_errors(cur["trigger"], cur["stop"], cur["next"]):
            failures += 1
    if failures:
        findings.append(finding(
            "stop-on-nudge", "scaffold", "KEEP", "", "process-eval", failures, names(fires),
            fires=len(fires), failures=failures, remove=spec["remove"], keep=spec["keep"],
        ))
    elif len(fires) >= spec["min_fires"]:
        findings.append(finding(
            "stop-on-nudge", "scaffold", "", "PROPOSE", "process-eval", len(fires), names(fires),
            fires=len(fires), failures=0, remove=spec["remove"], keep=spec["keep"],
        ))
    else:
        unproven.append("stop-on-nudge")
    return findings, unproven


def read_delegation(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    brief = child_block(text, "brief")
    attempt = top_field(text, "attempt")
    try:
        number = int(attempt)
    except ValueError:
        number = 0
    prior = indented_field(brief, "prior_failure") or top_field(text, "prior_failure")
    return {"name": path.name, "attempt": number, "prior": prior}


def judge_replay(directory: Path | None, table: dict[str, dict]) -> tuple[list[dict], list[str]]:
    spec = scaffold_spec(table, "context-replay")
    if directory is None:
        return [], ["context-replay"]
    rows = []
    for path in sorted(directory.rglob("*.yaml")):
        if path.is_file():
            rows.append(read_delegation(path))
    retries = [row for row in rows if row["attempt"] > 1]
    memory = [row for row in retries if any(mark in row["prior"] for mark in MEMORY_MARKERS)]
    if memory:
        return [finding(
            "context-replay", "scaffold", "KEEP", "", "process-eval", len(memory), names(memory),
            fires=len(retries), failures=len(memory), remove=spec["remove"], keep=spec["keep"],
        )], []
    if len(retries) >= spec["min_fires"]:
        return [finding(
            "context-replay", "scaffold", "", "PROPOSE", "process-eval", len(retries), names(retries),
            fires=len(retries), failures=0, remove=spec["remove"], keep=spec["keep"],
        )], []
    return [], ["context-replay"]


def line_of(row: dict) -> str:
    return (
        "FINDING id=%s kind=%s now=%s later=%s count=%s rule=%s evidence=%s fires=%s failures=%s"
        % (row["id"], row["kind"], row["now"], row["later"], row["count"], row["rule"],
           row["evidence"], row["fires"], row["failures"])
    )


def emit(findings: list[dict], unproven: list[str], mode: str) -> str:
    if mode == "stop":
        now = findings[0]["now"] if findings else "KEEP"
        later = findings[0]["later"] if findings else ""
    else:
        now = ""
        later = "PROPOSE" if any(row["later"] == "PROPOSE" for row in findings) else ""
    waste = sum(row["count"] for row in findings if row["kind"] == "waste")
    unreasonable = sum(row["count"] for row in findings if row["kind"] == "unreasonable")
    idle = sum(1 for row in findings if row["kind"] == "scaffold" and row["later"] == "PROPOSE")
    lines = [
        "PROCESS now=%s later=%s waste=%s unreasonable=%s scaffold_idle=%s unproven=%s"
        % (now, later, waste, unreasonable, idle, ",".join(unproven))
    ]
    lines.extend(line_of(row) for row in findings if row["id"] != "none")
    if mode == "stop" and findings:
        action = DO.get(findings[0]["id"], DO["ask"] if findings[0]["now"] == "ASK" else DO["none"])
        lines.append("DO " + action)
    elif later == "PROPOSE":
        lines.append("DO " + DO["propose"])
    return "\n".join(lines) + "\n"


def except_names(path: str) -> set[str]:
    if not path:
        return set()
    nameset = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if item and not item.startswith("#"):
            nameset.add(Path(item).name)
    return nameset


def trace_rows(directory: Path, window: int, skip: set[str]) -> list[dict]:
    files = [path for path in directory.glob("*.yaml") if path.is_file() and path.name not in skip]
    files.sort(key=lambda path: path.name)
    if window > 0:
        files = files[-window:]
    rows = []
    for path in files:
        try:
            rows.append(read_trace(path))
        except OSError:
            continue
    return rows


def proposal_status(path: Path) -> str:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return ""
    match = re.search(r"(?m)^status:\s*(\S+)", head)
    return match.group(1).strip().strip('"').lower() if match else ""


def open_draft(directory: Path) -> Path | None:
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*-process-eval.md")):
        if "source: process-eval.py" in path.read_text(encoding="utf-8", errors="replace")[:2500]:
            if proposal_status(path) not in CLOSED:
                return path
    return None


def write_proposal(findings: list[dict], out: Path) -> tuple[Path, bool]:
    out.mkdir(parents=True, exist_ok=True)
    existing = open_draft(out)
    if existing is not None:
        return existing, False
    chosen = [row for row in findings if row["later"] == "PROPOSE"]
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = out / ("%s-process-eval.md" % stamp)
    blocks = []
    for row in chosen:
        blocks.append(
            "- id=%s：%s 留下：%s。证据：%s"
            % (row["id"], row["remove"] or CHANGE.get(row["id"], "待填"), row["keep"] or "待填", row["evidence"])
        )
    body = "\n".join([
        "# process-eval 草稿（待拷问）",
        "",
        "status: draft",
        "at: %s" % dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source: process-eval.py",
        "accept: later",
        "ids: %s" % ",".join(row["id"] for row in chosen),
        "",
        "## 要改什么",
        "",
        "须 grill 之后人确认才改真源。下面是草案，不是已落地的改动。",
        "",
        *blocks,
        "",
        "## 不改什么",
        "",
        "- 不改 SKILL、schema、ledger.phase，除非人确认这份草案",
        "- 不删仍在挡住失败的校验",
        "- 不打分，不按模型名字判断变强",
        "- 上面点名的轨迹是起草证据，不能再当接受证据",
        "",
    ])
    dest.write_text(body, encoding="utf-8")
    return dest, True


def proposals_dir(explicit: str) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("IDEV_PROPOSALS_DIR", "").strip()
    if env:
        return Path(env)
    import product_sink  # noqa: WPS433
    return product_sink.sink_dir("proposals", mkdir=True)


def cmd_stop(args: argparse.Namespace, _table: dict[str, dict]) -> int:
    drive = str(getattr(args, "drive", "") or "").strip().lower()
    drive_mod = None
    if not drive:
        try:
            import drive_mode as drive_mod  # noqa: WPS433
            from product_sink import product_repo  # noqa: WPS433
            from roots import kernel_root  # noqa: WPS433

            drive, _source = drive_mod.resolve(product_repo(), kernel_root() / "state")
        except Exception:
            drive = "assisted"
    print("DRIVE mode=%s" % drive)
    recommend = blank(getattr(args, "recommend", "") or "")
    if drive == "auto" and not recommend:
        if drive_mod is None:
            try:
                import drive_mode as drive_mod  # noqa: WPS433
            except Exception:
                drive_mod = None
        if drive_mod is not None:
            inferred = drive_mod.report_recommend(
                "\n".join(
                    [
                        str(getattr(args, "stop", "") or ""),
                        str(getattr(args, "signals", "") or ""),
                        str(getattr(args, "next", "") or ""),
                    ]
                ),
                loose=True,
            )
            if inferred:
                recommend = inferred
                print("DRIVE_AUTO infer-recommend=%s" % recommend)
    row = judge_stop(
        args.quote, args.stop, args.next, args.signals, args.decision,
        drive=drive, recommend=recommend,
    )
    print(emit([row], [], "stop"), end="")
    return 0


def cmd_scan(args: argparse.Namespace, table: dict[str, dict]) -> int:
    directory = Path(args.traces)
    if not directory.is_dir():
        print("PROCESS now= later= waste=0 unreasonable=0 scaffold_idle=0 unproven=no-traces")
        return 0
    skip = except_names(args.except_file)
    rows = trace_rows(directory, args.window, skip)
    findings, unproven = judge_traces(rows, table)
    extra, missing = judge_replay(Path(args.delegations) if args.delegations else None, table)
    findings.extend(extra)
    unproven.extend(missing)
    text = emit(findings, unproven, "scan")
    print(text, end="")
    if not args.propose:
        return 0
    if not any(row["later"] == "PROPOSE" for row in findings):
        print("PROPOSE no")
        return 0
    dest, created = write_proposal(findings, proposals_dir(args.out))
    print(("wrote %s" if created else "PROPOSE open %s") % dest)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scaffolds", default=str(Path(__file__).resolve().parent.parent / "references" / "scaffolds.yaml"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    stop = sub.add_parser("stop", help="judge the question about to be asked")
    stop.add_argument("--quote", default="")
    stop.add_argument("--stop", default="")
    stop.add_argument("--next", default="")
    stop.add_argument("--signals", default="")
    stop.add_argument("--decision", action="store_true")
    stop.add_argument("--drive", default="", help="assisted|auto; empty reads session/product default")
    stop.add_argument("--recommend", default="", help="AI recommendation; required for drive-auto")
    stop.set_defaults(func=cmd_stop)

    scan = sub.add_parser("scan", help="judge recent traces")
    scan.add_argument("--traces", required=True)
    scan.add_argument("--window", type=int, default=50)
    scan.add_argument("--delegations", default="")
    scan.add_argument("--except", dest="except_file", default="")
    scan.add_argument("--propose", action="store_true")
    scan.add_argument("--out", default="")
    scan.set_defaults(func=cmd_scan)

    args = parser.parse_args(argv)
    table = load_scaffolds(Path(args.scaffolds))
    return args.func(args, table)


if __name__ == "__main__":
    raise SystemExit(main())
