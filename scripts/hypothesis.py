#!/usr/bin/env python3
"""The hypothesis ledger for root-cause work.

conventions/evidence.md requires that every step designs a case and proves
it before the next step is decided, and that a root cause is only written
once the original symptom has gone red at least once. Hypotheses used to
live in the conversation, where they cannot be counted or revisited.

    hypothesis.py add   --feature F --claim "..." [--case "..."]
    hypothesis.py list  --feature F
    hypothesis.py set   --feature F --id H1 [--case ...] [--evidence P]
                        [--repro yes|no|pending] [--status open|proven|disproven]
    hypothesis.py check --feature F

The ledger is <ticket home>/hypotheses.yaml. check exits 1 on a finding.

    hypothesis.py candidates --feature F            # 候选原因与排除状态
    hypothesis.py blast --feature F --id H1 \
        --baseline CASE --guard CASE                # 修复前后的影响范围用例

Disproven hypotheses are kept, never deleted: a ruled-out path is part of
the evidence chain and keeps the next round from walking it again.

## Three kinds of rigour this enforces

**证据分级.** evidence.md ranks材料: AI 反馈不可信, 文档不可信, 代码逻辑可信.
A log line proves a symptom happened; it does not prove *why*. So a root
cause needs at least one `code:` tier evidence — a file:line whose logic
explains the symptom. `check` reports which tier each item rests on.

**穷举候选.** 「推导并论证可能引起问题的所有原因」means the ruled-out ones
are part of the answer. A single proven hypothesis with no siblings is
suspicious: either nothing else was ever considered, or alternatives were
dismissed in someone's head. Candidates make that visible.

**影响范围.** evidence.md step 4 asks for three case classes: 正确性 (red to
green), 影响范围 (paths that must not change), 验收 (the symptom is gone).
The middle one is the one that gets skipped, and it is the one that catches
a fix that breaks something else. `blast` records it per hypothesis.
"""
from __future__ import annotations

import argparse
import datetime as dt
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

REPRO = ("pending", "yes", "no")

# Evidence tiers, weakest to strongest. evidence.md: 代码逻辑可信, 文档不可信.
# A log proves the symptom occurred; only code logic explains why.
# Evidence strength. Two lists drifted here once — TIERS stopped at four
# kinds while EVIDENCE_KINDS grew to eight, so monitoring, traces, config,
# release records and artifact identity were all collapsed into "log".
# TIERS is now derived from one place: EVIDENCE_KINDS below, ordered.
TIER_WHY = {
    "doc": "文档/注释 —— 不可信,只是线索",
    "log": "日志/响应 —— 证明现象发生了,不证明为什么",
    "metric": "监控曲线 —— 证明影响范围与时间窗,不证明机制",
    "trace": "调用链 —— 证明走到了哪里,不证明为什么那样走",
    "config": "配置 —— 证明当时的设定是什么",
    "change": "发布/变更记录 —— 证明什么时候动过什么",
    "artifact": "产物身份 —— 证明跑的是哪一份代码(与源码逻辑互证)",
    "repro": "可复现用例 —— 证明能触发,仍需解释机制",
    "code": "代码逻辑(file:line)—— 解释机制的那一层",
}

# A file:line reference is what "code tier" means in practice.
CODE_REF = re.compile(r"[\w./-]+\.\w+:\d+")

# 关键判断至少双证据: one signal can only be marked 待验证. Two *independent*
# kinds corroborating each other is what makes a conclusion checkable —
# error log with monitoring, code path with a config change.
EVIDENCE_KINDS = {
    "code": re.compile(r"[\w./-]+\.\w+:\d+"),
    "doc": re.compile(r"(?i)\.md\b|readme|wiki|文档|注释"),
    "log": re.compile(r"(?i)\.log\b|logs?/|日志|stderr|stdout"),
    "metric": re.compile(r"(?i)监控|metric|grafana|dashboard|qps|latency|p99"),
    "trace": re.compile(r"(?i)trace|调用链|span|traceid"),
    "config": re.compile(r"(?i)\.ya?ml\b|\.properties\b|\.conf\b|配置|config"),
    "change": re.compile(r"(?i)发布|变更|deploy|release|commit\s*[0-9a-f]{7}|回滚"),
    "repro": re.compile(r"(?i)用例|case|复现|repro|test"),
    # The artifact's own build identity: a different question from "what
    # does the code say", which is why the two corroborate each other.
    "artifact": re.compile(
        r"(?i)artifact-match|git\.properties|MANIFEST|产物.*(?:commit|版本|身份)|"
        r"\bAHEAD\b|产物自述|构建时间"),
}
# Weakest to strongest. Derived from EVIDENCE_KINDS so the two can never
# disagree again: adding a kind without placing it here fails tier_check().
TIER_ORDER = ("doc", "log", "metric", "trace", "config", "change",
              "artifact", "repro", "code")
TIERS = TIER_ORDER


def tier_check() -> list[str]:
    """Every evidence kind must have a rank and a reason. One list, checked."""
    problems = []
    for k in EVIDENCE_KINDS:
        if k not in TIER_ORDER:
            problems.append(f"{k} 有匹配规则但没有强度排序(TIER_ORDER)")
        if k not in TIER_WHY:
            problems.append(f"{k} 有匹配规则但没有说明(TIER_WHY)")
    for k in TIER_ORDER:
        if k not in EVIDENCE_KINDS:
            problems.append(f"{k} 在排序里但没有匹配规则(EVIDENCE_KINDS)")
    return problems
# 调用链必须穿透: a service that merely reports an error is usually relaying
# someone else's failure. The root cause has to bottom out somewhere that
# cannot pass the blame on.
TERMINAL = re.compile(
    r"(?i)数据库|database|\bdb\b|mysql|redis|缓存|cache|kafka|消息|mq|"
    r"第三方|third[- ]party|外部依赖|upstream\s*api|业务输入|入参|配置项|"
    r"磁盘|disk|内存|oom|网络|network|dns")
# Anchoring at line start missed the common Chinese form 「商品服务」 —
# which is exactly the case this check exists for.
MIDDLE_ONLY = re.compile(
    r"(?i)[\w.-]*(?:service|svc|gateway)\b|\bapi\b|"
    r"[一-鿿]{1,6}服务|网关|中台|接口层|上游服务")
STATUS = ("open", "proven", "disproven")


def ledger_path(feature: str, repo: Path | None) -> Path:
    base = (repo or Path.cwd()).resolve()
    return doc_home.homes(base, feature)["task"] / "hypotheses.yaml"


def load(path: Path, feature: str) -> dict:
    """The ledger, or a fresh one. A broken file starts over rather than crashing."""
    if path.is_file():
        data = safeyaml.mapping(path)
        if data is None:
            print(f"WARN unreadable ledger, starting a fresh one: {path}", file=sys.stderr)
        else:
            data.setdefault("items", [])
            if not isinstance(data["items"], list):
                print(f"WARN items is not a list, reset: {path}", file=sys.stderr)
                data["items"] = []
            return data
    return {"schema_version": 1, "feature": feature, "items": []}


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safeyaml.dump(data), encoding="utf-8")


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def next_id(items: list[dict]) -> str:
    used = {str(i.get("id", "")) for i in items}
    n = 1
    while f"H{n}" in used:
        n += 1
    return f"H{n}"


def find(items: list[dict], hid: str) -> dict | None:
    for item in items:
        if str(item.get("id")) == hid:
            return item
    return None


def cmd_add(args: argparse.Namespace) -> int:
    path = ledger_path(args.feature, args.repo)
    data = load(path, args.feature)
    item = {
        "id": next_id(data["items"]),
        "claim": args.claim,
        "case": args.case or "",
        "evidence": [],
        "repro": "pending",
        "status": "open",
        # 影响范围: the cases that prove the fix did not break anything else.
        # evidence.md step 4 class 2 — the one that gets skipped.
        "blast": {"baseline": [], "guard": []},
        # 时间窗必须可追溯: only from when the problem happened, when the
        # alert fired, or when the data last changed — never widened to
        # whatever makes the story work.
        "window": {"from": "", "to": "", "source": ""},
        # 根因报告先回答三问,再展开证据链。
        "impact": "",
        "remedy": "",
        "at": now(),
    }
    data["items"].append(item)
    save(path, data)
    print(f"OK   {item['id']} -> {path}")
    if not args.case:
        print("HINT no case yet; evidence.md wants a runnable case before the next hypothesis")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    path = ledger_path(args.feature, args.repo)
    data = load(path, args.feature)
    item = find(data["items"], args.id)
    if item is None:
        print(f"BLOCKED no such hypothesis: {args.id}", file=sys.stderr)
        return 2
    if args.case:
        item["case"] = args.case
    if args.evidence:
        item.setdefault("evidence", []).extend(args.evidence)
    if args.repro:
        item["repro"] = args.repro
    if args.status:
        item["status"] = args.status
    if getattr(args, "note", None):
        item["note"] = args.note
    for field in ("impact", "remedy"):
        val = getattr(args, field, None)
        if val:
            item[field] = val
    if getattr(args, "window", None) or getattr(args, "window_source", None):
        win = item.get("window") if isinstance(item.get("window"), dict) else {}
        if getattr(args, "window", None):
            lo, _, hi = str(args.window).partition("..")
            win["from"], win["to"] = lo.strip(), hi.strip()
        if getattr(args, "window_source", None):
            win["source"] = args.window_source
        item["window"] = win
    item["at"] = now()
    save(path, data)
    rc = check(data, verbose=False)
    if rc == 0:
        print(f"OK   {args.id} updated -> {path}")
    else:
        # Saved deliberately: the ledger records the process, including a
        # state whose evidence is still being assembled. The finding printed
        # above says what is missing before it counts as proven.
        print(f"SAVED {args.id} -> {path}(已写入,但未通过检查,见上)", file=sys.stderr)
    return rc


def cmd_list(args: argparse.Namespace) -> int:
    data = load(ledger_path(args.feature, args.repo), args.feature)
    if not data["items"]:
        print("(no hypotheses)")
        return 0
    for item in safeyaml.as_list(data.get("items")):
        if not isinstance(item, dict):
            print(f"(非 mapping 条目,跳过: {item!r})")
            continue
        ev = len(safeyaml.as_list(item.get("evidence")))
        tier = tier_of(safeyaml.as_list(item.get("evidence"))) or "-"
        blast = item.get("blast") if isinstance(item.get("blast"), dict) else {}
        guards = len(safeyaml.as_list(blast.get("guard")))
        print(f"{item.get('id')}  {item.get('status','?'):10} repro={item.get('repro','?'):7} "
              f"evidence={ev}({tier}) guard={guards}  {item.get('claim','')}")
        if item.get("case"):
            print(f"      case: {item['case']}")
    return 0


def kinds_of(evidence: list) -> set[str]:
    """Which independent evidence kinds this item rests on."""
    out: set[str] = set()
    for e in evidence:
        s = str(e)
        for kind, rx in EVIDENCE_KINDS.items():
            if rx.search(s):
                out.add(kind)
    return out


def tier_of(evidence: list) -> str:
    """The strongest tier this evidence reaches, by TIER_ORDER."""
    kinds = kinds_of(evidence)
    best = ""
    for k in TIER_ORDER:
        if k in kinds:
            best = k
    return best


def check(data: dict, verbose: bool = True) -> int:
    items = safeyaml.as_list(data.get("items"))
    errors: list[str] = []
    warns: list[str] = []

    for item in items:
        if not isinstance(item, dict):
            errors.append(f"items 里有非 mapping 条目,无法检查: {item!r}")
            continue
        hid = item.get("id", "?")
        status = str(item.get("status", "open"))
        raw_evidence = item.get("evidence")
        evidence = safeyaml.as_list(raw_evidence)
        if raw_evidence and not evidence:
            # A bare string would otherwise iterate character by character
            # and report every letter as a missing path.
            warns.append(f"{hid}: evidence 应是列表,已忽略: {raw_evidence!r}")

        if status == "proven":
            if str(item.get("repro")) != "yes":
                errors.append(f"{hid}: proven-needs-repro — status proven but repro={item.get('repro')}")
            if not evidence:
                errors.append(f"{hid}: proven-needs-evidence — status proven with no evidence path")
            else:
                # 结论要有直接证据支撑: a log says the symptom happened; only
                # code logic says why. Without a file:line the mechanism is
                # still a story.
                tier = tier_of(evidence)
                if tier != "code":
                    errors.append(
                        f"{hid}: proven-needs-code-evidence — 证据最强只到 {tier} "
                        f"({TIER_WHY.get(tier, tier)});根因要有 file:line 级的"
                        "代码逻辑解释机制,否则只是「现象发生过」")
            # 关键判断至少双证据. One signal is 待验证, not proven: a log line
            # and a code path corroborating each other is checkable; either
            # one alone is a story that happens to fit.
            kinds = kinds_of(evidence)
            if len(kinds) < 2:
                errors.append(
                    f"{hid}: proven-needs-two-sources — 证据只有 "
                    f"{'/'.join(sorted(kinds)) or '一类'} 一类。"
                    "关键判断至少要两类**互相印证**的证据(错误日志 × 监控异常、"
                    "代码路径 × 配置变更……);单一信号只能标 open")
            # 调用链必须穿透: a middle service relaying someone else's error
            # is the most common wrong answer in a distributed system.
            claim = str(item.get("claim", ""))
            if not TERMINAL.search(claim) and MIDDLE_ONLY.search(claim):
                warns.append(
                    f"{hid}: root-cause-not-terminal — 根因落在一个中间服务上,"
                    "而它报错往往只是在转述上游的失败。原则上要追到数据库 / 缓存 / "
                    "消息 / 第三方 / 明确的业务输入异常;中间服务不能作为唯一根因。"
                    "确实到底了就在 claim 里写明是哪一类终端原因")
            # 时间窗可追溯: an unsourced window is how unrelated evidence
            # gets swept in.
            win = item.get("window") if isinstance(item.get("window"), dict) else {}
            if (win.get("from") or win.get("to")) and not str(win.get("source") or "").strip():
                errors.append(
                    f"{hid}: window-without-source — 写了时间窗却没写来源。"
                    "时间窗只能来自问题发生时间 / 告警时间 / 数据更新时间,"
                    "随意扩大会把无关证据卷进来")
            # 根因报告三问: 根因是什么 / 影响是什么 / 建议怎么做。
            for field, q in (("impact", "影响是什么(影响范围、异常时间窗、受影响业务或数据)"),
                             ("remedy", "建议怎么做(修复建议、验证方式、回滚或止损动作)")):
                if not str(item.get(field) or "").strip():
                    errors.append(
                        f"{hid}: report-missing-{field} — 根因报告要先回答三问,"
                        f"缺「{q}」。只说根因是什么,拿到它的人不知道下一步做什么")
            # 影响范围: a proven root cause is about to be fixed. Without a
            # guard case, nobody knows whether the fix broke a neighbour.
            blast = item.get("blast") if isinstance(item.get("blast"), dict) else {}
            if not safeyaml.as_list(blast.get("guard")):
                errors.append(
                    f"{hid}: proven-needs-blast-radius — 没有 blast.guard 用例。"
                    "evidence.md 第 4 步要三类用例,影响范围那一类最常被跳过,"
                    "而它正是挡住「修一个坏三个」的那一类。"
                    f"用 hypothesis.py blast --id {hid} --guard <case> 记上")
        for path in evidence:
            if not Path(str(path)).exists():
                warns.append(f"{hid}: evidence path not found: {path}")

    # 排除也要举证. A ruled-out candidate with no reason sends the next
    # round down the same path — the record exists to stop exactly that.
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("status")) == "disproven":
            why = str(item.get("note") or "").strip()
            ev = safeyaml.as_list(item.get("evidence"))
            if not why and not ev:
                errors.append(
                    f"{item.get('id')}: disproven-needs-proof — 标了已排除但没有依据。"
                    "排除也要举证:写 --note 说明怎么排除的,或挂上证据路径。"
                    "没有依据的排除,下一轮会重走这条路")

    # 穷举候选: 「论证可能引起问题的所有原因」. One proven item with no
    # disproven siblings means either nothing else was considered, or the
    # alternatives were dismissed without record.
    proven_ids = [str(i.get("id")) for i in items
                  if isinstance(i, dict) and str(i.get("status")) == "proven"]
    disproven = [i for i in items if isinstance(i, dict) and str(i.get("status")) == "disproven"]
    if proven_ids and not disproven and len(items) == 1:
        warns.append(
            f"{proven_ids[0]}: 只有一条假设且直接证成,没有任何被排除的候选 —— "
            "第一个猜想恰好就是根因是可能的,但更常见的是别的可能性从未被写下来。"
            "把考虑过又排除的原因记成 disproven,它们是证据链的一部分")

    # case-before-next: an open hypothesis with no case, while later ones exist.
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if str(item.get("status", "open")) == "open" and not str(item.get("case", "")).strip():
            if i < len(items) - 1:
                errors.append(
                    f"{item.get('id','?')}: case-before-next — still open with no case, "
                    f"but {len(items) - i - 1} later hypothesis(es) were added"
                )

    for warn in warns:
        print("WARN " + warn, file=sys.stderr)
    if errors:
        for err in errors:
            print("FAIL " + err, file=sys.stderr)
        return 1
    if verbose:
        proven = sum(1 for i in items if i.get("status") == "proven")
        disproven = sum(1 for i in items if i.get("status") == "disproven")
        print(f"hypothesis PASS {len(items)} items ({proven} proven, {disproven} disproven)")
    return 0


def cmd_candidates(args: argparse.Namespace) -> int:
    """What was considered, and what is ruled out. The ruled-out ones matter."""
    data = load(ledger_path(args.feature, args.repo), args.feature)
    items = [i for i in safeyaml.as_list(data.get("items")) if isinstance(i, dict)]
    if not items:
        print("(还没有候选原因)")
        print("排障要「推导并论证可能引起问题的所有原因」——")
        print("先把想到的都 add 进来,再逐个证成或排除。")
        return 0

    by_status: dict[str, list[dict]] = {}
    for i in items:
        by_status.setdefault(str(i.get("status", "open")), []).append(i)

    print(f"# 候选原因  {args.feature}   共 {len(items)} 条")
    print()
    for status, label in (("proven", "已证成"), ("open", "待验"), ("disproven", "已排除")):
        group = by_status.get(status, [])
        if not group:
            continue
        print(f"## {label}  ({len(group)})")
        for i in group:
            tier = tier_of(safeyaml.as_list(i.get("evidence"))) or "-"
            print(f"  {i.get('id')}  [{tier}]  {i.get('claim','')}")
            if status == "disproven":
                # Why it was ruled out is the part that stops the next round
                # from walking the same path.
                why = str(i.get("note") or i.get("case") or "")
                if why:
                    print(f"       排除依据: {why[:70]}")
                else:
                    print("       排除依据: (空)—— 写上它,否则下一轮会重走这条路")
        print()

    if not by_status.get("disproven"):
        print("**没有任何被排除的候选。** 这不一定错,但值得问一句:")
        print("别的可能性是真的考虑过并排除了,还是从没写下来?")
        print()
    return 0


def cmd_blast(args: argparse.Namespace) -> int:
    """Record the cases that prove a fix stayed inside its blast radius."""
    path = ledger_path(args.feature, args.repo)
    data = load(path, args.feature)
    item = find(safeyaml.as_list(data.get("items")), args.id)
    if item is None:
        print(f"BLOCKED no such hypothesis: {args.id}", file=sys.stderr)
        return 2
    blast = item.get("blast") if isinstance(item.get("blast"), dict) else {}
    blast.setdefault("baseline", [])
    blast.setdefault("guard", [])
    for c in args.baseline or []:
        if c not in blast["baseline"]:
            blast["baseline"].append(c)
    for c in args.guard or []:
        if c not in blast["guard"]:
            blast["guard"].append(c)
    if args.note:
        blast["note"] = args.note
    item["blast"] = blast
    item["at"] = now()
    save(path, data)

    print(f"OK   {args.id} blast -> {path}")
    print(f"  baseline(修复前的现状,用来对照): {len(blast['baseline'])} 条")
    print(f"  guard(不该变的路径,修复后必须仍绿): {len(blast['guard'])} 条")
    if not blast["guard"]:
        print()
        print("HINT guard 还是空的。evidence.md 第 4 步的三类用例里,")
        print("     「影响范围:不该变的路径保持原行为」最常被跳过 ——")
        print("     而它正是挡住「修一个坏三个」的那一类。")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    return check(load(ledger_path(args.feature, args.repo), args.feature))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="add a hypothesis")
    p.add_argument("--feature", required=True)
    p.add_argument("--claim", required=True)
    p.add_argument("--case", help="the runnable case that would prove or disprove it")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("set", help="update a hypothesis")
    p.add_argument("--feature", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--case")
    p.add_argument("--evidence", action="append", help="repeatable")
    p.add_argument("--repro", choices=REPRO)
    p.add_argument("--status", choices=STATUS)
    p.add_argument("--note", help="disproven 时写排除依据,否则下一轮会重走这条路")
    p.add_argument("--impact", help="影响范围 / 异常时间窗 / 受影响业务(根因报告三问之二)")
    p.add_argument("--remedy", help="修复建议 / 验证方式 / 回滚动作(根因报告三问之三)")
    p.add_argument("--window", help="时间窗,格式 <from>..<to>")
    p.add_argument("--window-source", help="时间窗来自哪:问题发生 / 告警 / 数据更新时间")
    p.set_defaults(fn=cmd_set)

    p = sub.add_parser("list", help="list hypotheses")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("candidates", help="what was considered and what is ruled out")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_candidates)

    p = sub.add_parser("blast", help="record the blast-radius cases for a hypothesis")
    p.add_argument("--feature", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--baseline", action="append", help="修复前的现状用例(可重复)")
    p.add_argument("--guard", action="append", help="不该变的路径,修复后必须仍绿(可重复)")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_blast)

    p = sub.add_parser("check", help="exit 1 on a finding")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_check)

    args = parser.parse_args()
    if args.repo is None and os.environ.get("IDEV_PRODUCT_REPO"):
        args.repo = Path(os.environ["IDEV_PRODUCT_REPO"])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
