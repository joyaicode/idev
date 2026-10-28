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
# 召回(recall)给的是**建议与约束**,不是既定答案:
#   「出现 X 时,先核对 Y,再下结论;若 Z 则不适用」
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
    hits = hits[: args.top]

    if not hits:
        print("(没有匹配的经验)")
        print()
        print("这不是坏消息 —— 没有先验就按证据从头走一遍,")
        print("排查完把有价值的路径用 `lessons.py add` 记成候选。")
        return 0

    print(f"# 相关经验 {len(hits)} 条  (scope={args.scope or '*'})")
    print()
    print("**以下是建议与约束,不是答案。** 仍要回到当前证据验证 ——")
    print("历史结论生搬硬套,正是经验库最大的风险。")
    print()
    for x in hits:
        mark = "权威" if str(x.get("status")) == "authoritative" else "候选(未经人确认)"
        print(f"## {x.get('id')}  [{mark}]  {EVENT_WHY.get(str(x.get('event')), '')}")
        print(f"   现象: {x.get('symptom')}")
        print(f"   建议: {x.get('action')}")
        print(f"   依据: {x.get('evidence')}")
        print(f"   结果: {x.get('outcome')}")
        print(f"   **不适用于**: {x.get('not_when')}")
        if str(x.get("status")) != "authoritative":
            print("   ⚠ 这条还没经人确认,当成一个待验假设,不要当结论")
        print()

    if not args.no_count:
        for x in hits:
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
    print("**台账干净 ≠ 经验正确。** 这里只查六问齐不齐、入库门禁有没有被绕过。")
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
