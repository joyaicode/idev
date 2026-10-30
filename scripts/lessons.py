#!/usr/bin/env python3
"""A ledger of reusable troubleshooting experience, with a promotion gate.

    lessons.py add --feature F --scope S --symptom T ...   # 记一条候选
    lessons.py recall --scope S [--symptom T]              # 任务前召回
    lessons.py promote --id L1 --by NAME --repro PATH      # 人确认后入库
    lessons.py retire --id L1 --why "..."                  # 过时就清
    lessons.py check                                       # 台账自检
    lessons.py schema

A conclusion that was useful once is worth keeping. A conclusion that was
*wrong* once, kept and recalled, turns one local mistake into a systematic
one — so this ledger's whole design is about the gate, not the storage.

## Candidate is not authority

A lesson enters as `candidate` and stays there. Promotion to `authoritative`
needs two things a machine can check are present: a **reproduction** (the
lesson was replayed, not just remembered) and a **named person** who
confirmed it. This is the same shape as the kernel's proposal path —
起草 → grill → 人确认 → land (references/feedback-loop.md) — because it
answers the same danger: an unverified conclusion being cited as fact.

## Six questions

A reusable lesson answers all six, or it is a process log rather than
decision knowledge:

    scope       在什么范围内    (system / domain / node)
    symptom     什么现象下
    evidence    依据哪些证据
    action      采取什么动作
    outcome     得到什么结果
    not_when    何时不适用      ← the one that gets skipped

`not_when` is required on purpose. A lesson without a stated boundary gets
applied where it does not hold, and that is how a correct lesson becomes a
wrong one.

## Decision prefix

When the failure is one step, `--prefix` names a yaml file: the goal, the
environment, the agent and tool versions, a file frozen before that step,
the acceptable next actions, and the forbidden ones. `check` only looks at
that shape. It does not run an agent, and a score cannot promote the lesson.
A factual lesson leaves the block off.

## Recall advises, it does not decide

`recall` prints lessons as **建议与约束**, never as answers: "when X, check
Y before concluding Z". The agent still has to reach its own conclusion from
current evidence — hypothesis.py's guards still apply. A lesson that
short-circuits the evidence chain would be worse than no lesson.

Exit: 0 ok, 1 findings, 2 cannot read.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402
# The signoff blacklist lives in workflow_spec; reusing it keeps one list.
# Two copies would drift, and this list is the whole implementation of
# "a model may not confirm its own conclusion".
import workflow_spec  # noqa: E402

STATUS = ("candidate", "authoritative", "retired")
# 学习事件分类: what kind of thing was learned. Each has a different reuse
# value, which is why they are not one undifferentiated pile.
EVENT = ("verified", "ruled-out", "failed-action", "user-correction", "stale-knowledge")
EVENT_WHY = {
    "verified": "某个判断被证实 —— 复用价值最高",
    "ruled-out": "某条路径被排除 —— 省下一次重走",
    "failed-action": "某个动作失败了 —— 防止再试一次",
    "user-correction": "人纠正了 Agent 的结论 —— 最该记的一类",
    "stale-knowledge": "既有知识已过时 —— 记下来是为了让它被清掉",
}
SIX = ("scope", "symptom", "evidence", "action", "outcome", "not_when")
SIX_Q = {
    "scope": "在什么范围内(系统 / 业务域 / 节点)",
    "symptom": "什么现象下",
    "evidence": "依据哪些证据",
    "action": "采取什么动作",
    "outcome": "得到什么结果",
    "not_when": "何时不适用 —— **这条最常被跳过**,而它正是边界",
}

SCHEMA = """\
# 经验台账(state/lessons.yaml 或 <票目录>/lessons.yaml)
#
# 一条可复用经验至少回答六个问题,否则它只是过程日志,不是决策知识:
#
# lessons:
#   - id: L1
#     status: candidate            # candidate | authoritative | retired
#     event: verified              # verified|ruled-out|failed-action|user-correction|stale-knowledge
#     scope: 商品数据链路 / 库存回写
#     symptom: 库存回写延迟,下游读到旧值
#     evidence: 消息积压 kafka-lag 指标 + 幂等表 idempotent_log 无新记录
#     action: 先核对消息积压与幂等记录,再看消费者
#     outcome: 积压在上游生产侧,消费者正常
#     not_when: 消费位点连续推进时不适用 —— 那种情况不要优先判断为消费者停滞
#                                  ↑ 何时不适用:六问里最常被跳过的一条。
#                                    没有边界的经验会被用在它不成立的地方,
#                                    那正是一条正确经验变成错误经验的方式。
#     prefix:                      # 可选。没有决策步就不要写
#       goal: 把失败沉淀成下次还能核对的下一步
#       env: 本机 idev 内核
#       agent: 导体
#       tools: scripts/lessons.py
#       before: state/lessons/L2-before.md
#       first_error:
#         step: 写入经验
#         kind: message            # message | tool
#         category: 流程与规范缺失
#         evidence: 当时的 schema 只有六问
#         cause: 失败被写成建议
#         consequence: 召回无法核对下一步
#       accept: [有决策步就写 prefix]
#       forbid: [把召回正文当作答案]
#     from_feature: ticket-123     # 来自哪次排查
#     confirmed_by: ""             # 人确认才填(promote 时写)
#     repro: ""                    # 旁路复现的证据路径(promote 时写)
#     uses: 0                      # 被召回过几次
#     at: ...
#
# 入库门禁(promote):**候选 ≠ 权威**
#   - 要有 repro(旁路复现过,不是只凭印象)
#   - 要有 confirmed_by(具体的人,不能是 agent/ai/cursor/assistant)
#   二者缺一不得 authoritative。错误结论一旦入库会被后续分析反复引用 ——
#   一次局部偏差就变成系统性偏差。
#
# 决策步的 prefix 只验形状:目标、环境、版本、首错前的非空文件、
# 可接受动作、禁止动作要一起在。不执行 Agent,也不用分数决定 promote。
# user-correction / failed-action 没写 prefix 时 check 警告,不因此失败。
#
# 召回(recall)给的是**建议与约束**,不是既定答案:
#   「出现 X 时,先核对 Y,再下结论;若 Z 则不适用」
# 同一 scope 上 action 不同时打 CONFLICT，被 --top 截掉的那一条也列出。
# 不改旧行，不挑较新的一条当答案。check 只警告。
# Agent 仍要回到当前证据自己走一遍 —— hypothesis.py 的六条强约束照常生效。
#
# 过时就清(retire):知识过期不清,下一轮会把它读成当前有效。
"""


def pair_check() -> list[str]:
    """Every enum must have its explanation, and vice versa.

    hypothesis.py once had two lists of evidence kinds drift apart in
    silence; these pairs are the same shape, so they get the same guard.
    """
    out = []
    for name, keys, why in (("EVENT", EVENT, EVENT_WHY), ("SIX", SIX, SIX_Q)):
        for k in keys:
            if k not in why:
                out.append(f"{name}: {k} 没有说明")
        for k in why:
            if k not in keys:
                out.append(f"{name}: {k} 有说明但不在清单里")
    return out


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def ledger_path(repo: Path | None, feature: str | None) -> Path:
    """Ticket-local when a feature is given, else the kernel-wide ledger."""
    if feature:
        sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
        import doc_home  # noqa: E402

        base = repo or (Path(os.environ["IDEV_PRODUCT_REPO"])
                        if os.environ.get("IDEV_PRODUCT_REPO") else Path.cwd())
        home = doc_home.homes(base.resolve(), feature)["task"]
        if not home.is_dir():
            # Every other tool BLOCKs here. Returning a path under a ticket
            # that does not exist made `check` report "PASS 0 条" and
            # `recall` report "no matching lessons" — so a typo in the
            # feature name read as "the ledger is clean" / "nothing known".
            print(f"BLOCKED no ticket home at {home}", file=sys.stderr)
            print("HINT    feature 名打错了?或这张票还没建立", file=sys.stderr)
            raise SystemExit(2)
        return home / "lessons.yaml"
    return kind_agents.kernel_root() / "state" / "lessons.yaml"


def load(path: Path) -> dict:
    data = safeyaml.mapping(path)
    if data is None:
        return {"schema_version": 1, "lessons": []}
    data.setdefault("lessons", [])
    return data


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safeyaml.dump(data), encoding="utf-8")


def _merge(fresh: dict, item: dict) -> dict:
    """Put one lesson back into the ledger as it stands right now."""
    fresh.setdefault("schema_version", 1)
    fresh.setdefault("lessons", [])
    for n, existing in enumerate(fresh["lessons"]):
        if isinstance(existing, dict) and str(existing.get("id")) == str(item.get("id")):
            fresh["lessons"][n] = item
            return fresh
    fresh["lessons"].append(item)
    return fresh


def next_id(lessons: list) -> str:
    n = 0
    for item in lessons:
        if isinstance(item, dict):
            raw = str(item.get("id", "")).lstrip("L")
            if raw.isdigit():
                n = max(n, int(raw))
    return f"L{n + 1}"


def find(lessons: list, lid: str) -> dict | None:
    want = lid.upper()
    for item in lessons:
        if isinstance(item, dict) and str(item.get("id", "")).upper() == want:
            return item
    return None


PREFIX_TEXT = ("goal", "env", "agent", "tools", "before")
ERROR_TEXT = ("step", "kind", "category", "evidence", "cause", "consequence")
ERROR_KIND = ("message", "tool")
PREFIX_EVENT = ("user-correction", "failed-action")


def nonblank(value) -> str:
    return str(value or "").strip()


def string_list(value) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    out = []
    for item in value:
        text = nonblank(item)
        if not text:
            return None
        out.append(text)
    return out


def bound_root(repo: Path | None, feature: str | None) -> Path:
    if feature:
        if repo is not None:
            return repo.resolve()
        if os.environ.get("IDEV_PRODUCT_REPO"):
            return Path(os.environ["IDEV_PRODUCT_REPO"]).resolve()
        return Path.cwd().resolve()
    return kind_agents.kernel_root()


def before_file(root: Path, raw: str) -> str:
    text = nonblank(raw)
    if not text or text.startswith("/") or ".." in Path(text).parts:
        return "before 必须是台账根下的相对路径"
    path = (root / text).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return "before 必须是台账根下的相对路径"
    if not path.is_file() or path.stat().st_size <= 0:
        return f"before 不是非空文件: {text}"
    return ""


def error_problems(err) -> list[str]:
    if not isinstance(err, dict):
        return ["prefix.first_error 必须写明首错"]
    problems = [f"prefix.first_error 缺 {key}" for key in ERROR_TEXT if not nonblank(err.get(key))]
    kind = nonblank(err.get("kind"))
    if kind and kind not in ERROR_KIND:
        problems.append("prefix.first_error.kind 只能是 message 或 tool")
    return problems


def prefix_problems(prefix, root: Path) -> list[str]:
    if not isinstance(prefix, dict):
        return ["prefix 必须是一组字段"]
    problems = [f"prefix 缺 {key}" for key in PREFIX_TEXT if not nonblank(prefix.get(key))]
    if nonblank(prefix.get("before")):
        bad = before_file(root, str(prefix.get("before") or ""))
        if bad:
            problems.append(bad)
    problems.extend(error_problems(prefix.get("first_error")))
    for key in ("accept", "forbid"):
        if string_list(prefix.get(key)) is None:
            problems.append(f"prefix.{key} 至少一条")
    return problems


def prefix_source(root: Path, raw: str) -> tuple[Path | None, str]:
    text = nonblank(raw)
    if not text or ".." in Path(text).parts:
        return None, "prefix 文件必须在台账根下"
    path = Path(text)
    full = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        full.relative_to(root.resolve())
    except ValueError:
        return None, "prefix 文件必须在台账根下"
    return full, ""


def load_prefix(path: Path) -> tuple[dict | None, str]:
    data = safeyaml.mapping(path)
    if not data:
        return None, f"读不到 prefix: {path}"
    return data, ""


def read_prefix(args: argparse.Namespace) -> tuple[dict | None, str]:
    root = bound_root(args.repo, args.feature)
    path, err = prefix_source(root, args.prefix)
    if err or path is None:
        return None, err or "读不到 prefix"
    data, err = load_prefix(path)
    if err or data is None:
        return None, err or "读不到 prefix"
    problems = prefix_problems(data, root)
    if not problems:
        return data, ""
    return None, "prefix 不完整:\n  " + "\n  ".join(problems)


def print_prefix(prefix) -> None:
    if not isinstance(prefix, dict):
        return
    err = prefix.get("first_error") if isinstance(prefix.get("first_error"), dict) else {}
    accept = string_list(prefix.get("accept")) or []
    forbid = string_list(prefix.get("forbid")) or []
    print(f"   决策边界: 首错 {err.get('step')} ({err.get('kind')}) {err.get('cause')}")
    print("   可接受: " + "；".join(accept))
    print("   禁止: " + "；".join(forbid))
    print(f"   后果不算主因: {err.get('consequence')}")
    print("   这是要重新核对的边界，不是答案")


def cmd_add(args: argparse.Namespace) -> int:
    path = ledger_path(args.repo, args.feature)
    data = load(path)  # for the six-question check below
    missing = [f for f in SIX if not str(getattr(args, f, "") or "").strip()]
    if missing:
        print("BLOCKED 六问缺:", file=sys.stderr)
        for f in missing:
            print(f"  --{f.replace('_', '-')}   {SIX_Q[f]}", file=sys.stderr)
        print("\n六问不全的不是决策知识,是过程日志 —— 记了也不敢复用。", file=sys.stderr)
        return 2

    prefix = None
    if args.prefix:
        prefix, err = read_prefix(args)
        if err:
            print("BLOCKED " + err, file=sys.stderr)
            return 2

    item = {
        "id": next_id(data["lessons"]),
        # Always candidate. There is no flag to add an authoritative lesson
        # directly: that would be the gate this file exists to hold.
        "status": "candidate",
        "event": args.event,
        **{f: str(getattr(args, f)) for f in SIX},
        "from_feature": args.feature or "",
        "confirmed_by": "",
        "repro": "",
        "uses": 0,
        "at": now(),
    }
    if prefix is not None:
        item["prefix"] = prefix
    # Built and appended under the lock: computing the id outside it would
    # give two concurrent adds the same L1.
    def build(fresh: dict) -> dict:
        fresh.setdefault("schema_version", 1)
        fresh.setdefault("lessons", [])
        item["id"] = next_id(fresh["lessons"])
        fresh["lessons"].append(item)
        return fresh

    safeyaml.save_locked(path, build)
    print(f"OK   {item['id']} candidate -> {path}")
    print(f"  {EVENT_WHY.get(args.event, args.event)}")
    print()
    print("**候选 ≠ 权威。** 要被后续排查当作可信先验,还需要:")
    print(f"  python3 scripts/lessons.py promote --id {item['id']} \\")
    print("    --by <确认的人> --repro <旁路复现的证据路径>")
    print("错误结论一旦入库会被反复引用 —— 一次局部偏差就变成系统性偏差。")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    path = ledger_path(args.repo, args.feature)
    data = load(path)
    item = find(data["lessons"], args.id)
    if item is None:
        print(f"BLOCKED no such lesson: {args.id}", file=sys.stderr)
        return 2

    # The same blacklist that guards signoff: a model confirming its own
    # conclusion is not confirmation.
    if not workflow_spec.is_human(args.by):
        print(f"BLOCKED confirmed_by={args.by!r} 不是人 —— "
              "模型确认自己的结论不叫确认", file=sys.stderr)
        return 2
    repro = str(args.repro or "").strip()
    if not repro:
        print("BLOCKED 缺 --repro —— 入库前要旁路复现过,不是只凭印象", file=sys.stderr)
        return 2

    target = args.repo or (Path(os.environ["IDEV_PRODUCT_REPO"])
                           if os.environ.get("IDEV_PRODUCT_REPO") else Path.cwd())
    script = Path(__file__).resolve().parent / "codegraph-sync.sh"
    refreshed = subprocess.run(
        ["bash", str(script), "--repo", str(target.resolve()), "docs"],
        check=False,
    )
    if refreshed.returncode != 0:
        return refreshed.returncode

    item["status"] = "authoritative"
    item["confirmed_by"] = args.by
    item["repro"] = repro
    item["at"] = now()
    save(path, data)
    print(f"OK   {item['id']} authoritative (by {args.by}) -> {path}")
    print()
    print("它现在会被 recall 当作可信先验给出 —— 但仍是**建议与约束**,不是既定答案。")
    print("用它的 Agent 仍要回到当前证据自己走一遍。")
    return 0


def cmd_retire(args: argparse.Namespace) -> int:
    path = ledger_path(args.repo, args.feature)
    data = load(path)
    item = find(data["lessons"], args.id)
    if item is None:
        print(f"BLOCKED no such lesson: {args.id}", file=sys.stderr)
        return 2
    if not str(args.why or "").strip():
        print("BLOCKED 缺 --why —— 为什么它过时了?不写下来,下次有人会把它加回去",
              file=sys.stderr)
        return 2
    item["status"] = "retired"
    item["retired_why"] = args.why
    item["at"] = now()
    safeyaml.save_locked(path, lambda fresh: _merge(fresh, item))
    print(f"OK   {item['id']} retired -> {path}")
    print("知识过期不清,下一轮会把它读成当前有效。")
    return 0


def same_scope_conflicts(items: list) -> list[list]:
    """Same scope, different action. Retired rows stay on disk and do not conflict."""
    grouped: dict[str, list] = {}
    for item in items:
        if not isinstance(item, dict) or str(item.get("status")) == "retired":
            continue
        key = str(item.get("scope") or "").strip()
        if not key:
            continue
        grouped.setdefault(key, []).append(item)
    found = []
    for group in grouped.values():
        actions = {str(item.get("action") or "").strip() for item in group}
        actions.discard("")
        if len(group) >= 2 and len(actions) >= 2:
            found.append(group)
    return found


def cmd_recall(args: argparse.Namespace) -> int:
    path = ledger_path(args.repo, args.feature)
    data = load(path)
    lessons = [x for x in safeyaml.as_list(data.get("lessons")) if isinstance(x, dict)]

    def matches(item: dict) -> bool:
        if str(item.get("status")) == "retired":
            return False
        hay = " ".join(str(item.get(f, "")) for f in ("scope", "symptom"))
        if args.scope and args.scope not in hay:
            return False
        if args.symptom and args.symptom not in hay:
            return False
        return True

    hits = [x for x in lessons if matches(x)]
    # Authoritative first, then by how often it has helped. Not a score —
    # just "tried and confirmed before untried".
    hits.sort(key=lambda x: (str(x.get("status")) != "authoritative",
                             -safeyaml.as_int(x.get("uses"), 0)))
    conflicts = same_scope_conflicts(hits)
    shown = list(hits[: args.top])
    shown_ids = {str(item.get("id")) for item in shown}
    for group in conflicts:
        ids = {str(item.get("id")) for item in group}
        if not ids & shown_ids:
            continue
        for item in group:
            iid = str(item.get("id"))
            if iid not in shown_ids:
                shown.append(item)
                shown_ids.add(iid)

    if not shown:
        print("(没有匹配的经验)")
        print()
        print("这不是坏消息 —— 没有先验就按证据从头走一遍,")
        print("排查完把有价值的路径用 `lessons.py add` 记成候选。")
        return 0

    print(f"# 相关经验 {len(shown)} 条  (scope={args.scope or '*'})")
    print()
    print("**以下是建议与约束,不是答案。** 仍要回到当前证据验证 ——")
    print("历史结论生搬硬套,正是经验库最大的风险。")
    print()
    conflicted = False
    for group in conflicts:
        ids = [str(item.get("id")) for item in group]
        if set(ids) & shown_ids:
            print("CONFLICT " + " ".join(ids))
            conflicted = True
    if conflicted:
        print("同一范围里动作不同。两条都看，用各自的「不适用于」区分。不要改旧行，也不要只留较新的一条。")
        print()
    for x in shown:
        mark = "权威" if str(x.get("status")) == "authoritative" else "候选(未经人确认)"
        print(f"## {x.get('id')}  [{mark}]  {EVENT_WHY.get(str(x.get('event')), '')}")
        print(f"   现象: {x.get('symptom')}")
        print(f"   建议: {x.get('action')}")
        print(f"   依据: {x.get('evidence')}")
        print(f"   结果: {x.get('outcome')}")
        print(f"   **不适用于**: {x.get('not_when')}")
        if x.get("prefix") is not None:
            print_prefix(x.get("prefix"))
        if str(x.get("status")) != "authoritative":
            print("   ⚠ 这条还没经人确认,当成一个待验假设,不要当结论")
        print()

    if not args.no_count:
        for x in shown:
            real = find(data["lessons"], str(x.get("id")))
            if real is not None:
                real["uses"] = safeyaml.as_int(real.get("uses"), 0) + 1
        save(path, data)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    path = ledger_path(args.repo, args.feature)
    data = load(path)
    lessons = [x for x in safeyaml.as_list(data.get("lessons")) if isinstance(x, dict)]
    errors: list[str] = [f"内部不一致 — {p}" for p in pair_check()]
    warns: list[str] = []

    for x in lessons:
        lid = str(x.get("id", "?"))
        status = str(x.get("status", ""))
        if status not in STATUS:
            errors.append(f"{lid}: status={status!r} 不在 {'/'.join(STATUS)} 里")
        if str(x.get("event", "")) not in EVENT:
            errors.append(f"{lid}: event={x.get('event')!r} 不在 {'/'.join(EVENT)} 里")
        for f in SIX:
            if not str(x.get(f) or "").strip():
                errors.append(
                    f"{lid}: 缺 {f} —— {SIX_Q[f]}。六问不全的不是决策知识,"
                    "是过程日志 —— 补齐它,或 retire 掉")
        if status == "authoritative":
            # The gate, re-checked on read: a ledger edited by hand must not
            # be able to smuggle an unconfirmed lesson into authority.
            if not workflow_spec.is_human(str(x.get("confirmed_by", ""))):
                errors.append(
                    f"{lid}: authoritative 但 confirmed_by={x.get('confirmed_by')!r} 不是人 —— "
                    "入库门禁被绕过了。改回 status: candidate,然后走 "
                    f"`lessons.py promote --id {lid} --by <人> --repro <复现证据>`")
            if not str(x.get("repro") or "").strip():
                errors.append(
                    f"{lid}: authoritative 但没有 repro —— 没复现过不算验证。"
                    "旁路复现一次,把证据路径填进 repro;或改回 candidate")
        if status == "retired" and not str(x.get("retired_why") or "").strip():
            warns.append(f"{lid}: retired 却没写 retired_why,下次有人会把它加回去")
        prefix = x.get("prefix")
        if prefix is not None:
            root = bound_root(args.repo, args.feature)
            errors.extend(f"{lid}: {problem}" for problem in prefix_problems(prefix, root))
        elif str(x.get("event")) in PREFIX_EVENT:
            warns.append(
                f"{lid}: {x.get('event')} 没有 prefix。"
                "这次纠正若落在某一步决策上，补上首错前的上下文、可接受动作和禁止动作；"
                "纯事实不用造前缀")

    for group in same_scope_conflicts(lessons):
        ids = " ".join(str(item.get("id")) for item in group)
        warns.append(
            f"{ids}: 同一 scope 动作不同。recall 会打 CONFLICT。"
            "不要改旧行，也不要只留较新的一条")

    cand = sum(1 for x in lessons if str(x.get("status")) == "candidate")
    auth = sum(1 for x in lessons if str(x.get("status")) == "authoritative")
    used_cand = [x for x in lessons
                 if str(x.get("status")) == "candidate"
                 and safeyaml.as_int(x.get("uses"), 0) >= 3]
    for x in used_cand:
        warns.append(
            f"{x.get('id')}: 候选被召回 {x.get('uses')} 次却一直没人确认 —— "
            "要么复现后 promote,要么 retire。久留的候选会被当成权威用")

    for w in warns:
        print("WARN " + w, file=sys.stderr)
    if errors:
        for e in errors:
            print("FAIL " + e, file=sys.stderr)
        return 1
    print(f"lessons PASS {len(lessons)} 条({auth} 权威 / {cand} 候选)")
    print()
    print("**台账干净 ≠ 经验正确。** 这里只查六问齐不齐、prefix 形状齐不齐、入库门禁有没有被绕过。")
    print("经验本身对不对,要靠下一次排查回到证据验证它。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--feature", help="票内台账;不给则用内核级 state/lessons.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("schema")
    p.set_defaults(fn=lambda a: (print(SCHEMA), 0)[1])

    p = sub.add_parser("add", help="记一条候选经验(六问必答)")
    p.add_argument("--event", choices=EVENT, default="verified")
    for f in SIX:
        p.add_argument(f"--{f.replace('_', '-')}", dest=f, help=SIX_Q[f])
    p.add_argument("--prefix", help="决策步 yaml。没有决策步不要传")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("promote", help="人确认 + 复现后入库")
    p.add_argument("--id", required=True)
    p.add_argument("--by", required=True, help="确认的人(不能是 agent/ai/cursor/assistant)")
    p.add_argument("--repro", required=True, help="旁路复现的证据路径")
    p.set_defaults(fn=cmd_promote)

    p = sub.add_parser("retire", help="过时就清")
    p.add_argument("--id", required=True)
    p.add_argument("--why", required=True)
    p.set_defaults(fn=cmd_retire)

    p = sub.add_parser("recall", help="任务前召回(给建议与约束,不给答案)")
    p.add_argument("--scope", help="系统 / 业务域 / 节点")
    p.add_argument("--symptom")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--no-count", action="store_true", help="不计入 uses")
    p.set_defaults(fn=cmd_recall)

    p = sub.add_parser("check", help="台账自检")
    p.set_defaults(fn=cmd_check)

    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
