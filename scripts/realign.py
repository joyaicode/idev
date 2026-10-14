#!/usr/bin/env python3
"""Realign every stage artifact after the baseline moved.

    realign.py --feature F [--repo DIR]
    realign.py --feature F --plan      # what to redo, in order

deliver-schema.md already says what must happen after a reopen or a rewind:

    reopen: revision + 1；旧 id 的 slice / case 全部作废
    回退:   origin 之后的 accepted / aligned 失效

Nothing executed it. check-feature.py compares req/arch baseline_revision,
but not plan cases, not ops, and it never answers the question that actually
matters after a correction: **what is now stale, and in what order do I
redo it?**

Without that, a reopened ticket keeps its old slices, its old plan and its
old accepted flags — and the next round validates new requirements against
evidence produced for the old ones. The baseline is supposed to be the
measuring stick (deliver-schema.md: 验收尺是基线); a stale downstream
artifact silently replaces it with whatever was true before.

So this answers three questions:

  1. which artifacts no longer match the current baseline revision
  2. which signoffs the schema says are void (and are still sitting true)
  3. in what order to redo them, so the basis is re-established forward

It writes nothing. Realigning is the conductor's job, step by step, with
the human gates in their usual places — this only makes the drift visible.

Exit: 0 aligned, 1 drift found, 2 cannot read the inputs.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402
import textwidth as tw  # noqa: E402

sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
try:
    import doc_home  # noqa: E402
except ImportError:
    print(f"BLOCKED cannot import doc_home from {kind_agents.kernel_root()}", file=sys.stderr)
    raise SystemExit(2) from None

# Forward order of the stages, so "redo from here" is a slice of this.
ORDER = ("req-review", "req", "arch", "code", "test", "done")


class Drift:
    __slots__ = ("kind", "where", "detail", "redo")

    def __init__(self, kind: str, where: str, detail: str, redo: str) -> None:
        self.kind, self.where, self.detail, self.redo = kind, where, detail, redo


def load(home: Path, rel: str) -> dict:
    return safeyaml.mapping(home / rel) or {}


def item_ids(baseline: dict) -> set[str]:
    out = set()
    for item in safeyaml.as_list(baseline.get("items")):
        if isinstance(item, dict) and item.get("id"):
            out.add(str(item["id"]))
    return out


def scan(home: Path) -> tuple[list[Drift], dict]:
    baseline = load(home, "baseline.yaml")
    deliver = load(home, "deliver.yaml")
    req = load(home, "req.yaml")
    arch = load(home, "arch.yaml")
    plan = load(home, "verify/plan.yaml")
    ops = load(home, "ops.yaml")

    b_rev = safeyaml.as_int(baseline.get("revision"), 0)
    stage = str(deliver.get("stage") or "?")
    reopened = bool(deliver.get("reopen_baseline")) or not baseline.get("sealed", False)
    rewind = deliver.get("last_rewind") if isinstance(deliver.get("last_rewind"), dict) else {}
    origin = str(rewind.get("origin") or "")

    out: list[Drift] = []
    ids = item_ids(baseline)

    # --- 1. revision drift: an artifact built against an older baseline ---
    for name, doc, rel in (("req", req, "req.yaml"), ("arch", arch, "arch.yaml")):
        if not doc:
            continue
        rev = safeyaml.as_int(doc.get("baseline_revision"), -1)
        if rev != b_rev:
            out.append(Drift(
                "revision", rel,
                f"baseline_revision={rev} 而基线现在是 revision={b_rev}",
                name))

    # --- 2. dangling anchors: the id it points at no longer exists ---
    # deliver-schema.md: reopen 时「旧 id 的 slice / case 全部作废」。An id that
    # survived a reopen may also have been reused for a different must, which
    # is why the schema forbids reuse — either way the anchor is not trustworthy.
    for s in safeyaml.as_list(req.get("slices")):
        if not isinstance(s, dict):
            continue
        anchor = str(s.get("baseline_item_id") or "")
        if anchor and ids and anchor not in ids:
            out.append(Drift("dangling", f"req.slices[{s.get('id', '?')}]",
                             f"挂的 {anchor} 在当前基线里不存在了", "req"))

    for ci in safeyaml.as_list(arch.get("case_intents")):
        if isinstance(ci, dict):
            anchor = str(ci.get("baseline_item_id") or "")
            if anchor and ids and anchor not in ids:
                out.append(Drift("dangling", f"arch.case_intents[{ci.get('id', '?')}]",
                                 f"挂的 {anchor} 已不存在", "arch"))

    for c in safeyaml.as_list(plan.get("cases")):
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id", "?"))
        anchor = str(c.get("baseline_item_id") or "")
        if anchor and ids and anchor not in ids:
            out.append(Drift("dangling", f"plan.cases[{cid}]",
                             f"挂的 {anchor} 已不存在 —— 它在证明一条不再存在的需求",
                             "test"))

    # --- 3. uncovered baseline items: the correction added something ---
    covered = {str(s.get("baseline_item_id")) for s in safeyaml.as_list(req.get("slices"))
               if isinstance(s, dict)}
    for iid in sorted(ids - covered):
        if req:  # only meaningful once a decomposition exists
            out.append(Drift("uncovered", f"baseline.items[{iid}]",
                             "订正后新增/改动,但没有 slice 覆盖它", "req"))

    proven = {str(c.get("baseline_item_id")) for c in safeyaml.as_list(plan.get("cases"))
              if isinstance(c, dict)}
    if plan:
        for iid in sorted(ids - proven):
            out.append(Drift("unproven-item", f"baseline.items[{iid}]",
                             "没有任何 case 在证明它", "test"))

    # --- 4. signoffs the schema already declares void ---
    # 回退：origin 之后的 accepted / aligned 失效。Still sitting true means the
    # next round would read them as current.
    if origin and origin in ORDER:
        after = ORDER[ORDER.index(origin) + 1 :]
        if "req" in after and req.get("accepted"):
            out.append(Drift("stale-signoff", "req.accepted",
                             f"回退到 {origin} 之后它已失效,但仍是 true", "req"))
        if "arch" in after and arch.get("accepted"):
            out.append(Drift("stale-signoff", "arch.accepted",
                             f"回退到 {origin} 之后它已失效,但仍是 true", "arch"))
        if deliver.get("aligned"):
            out.append(Drift("stale-signoff", "deliver.aligned",
                             f"回退到 {origin} 之后提测对齐已失效,但仍是 true", "test"))
        gates = deliver.get("semantic_gate") if isinstance(deliver.get("semantic_gate"), dict) else {}
        for st in after:
            g = gates.get(st)
            if isinstance(g, dict) and g.get("passed"):
                out.append(Drift("stale-signoff", f"deliver.semantic_gate.{st}",
                                 f"回退到 {origin} 之后它已失效,但仍是 passed", st))

    if reopened:
        if plan.get("accepted"):
            out.append(Drift("stale-signoff", "plan.accepted",
                             "基线已解封,旧 plan 的 accepted 作废", "test"))
        for c in safeyaml.as_list(plan.get("cases")):
            if isinstance(c, dict) and str(c.get("status", "")).upper() == "PASS":
                out.append(Drift("stale-evidence", f"plan.cases[{c.get('id', '?')}]",
                                 "基线已解封,这条 PASS 证的是旧需求"
                                 "(证据保留,但不算当前基线的达标)", "test"))
                break  # one is enough to make the point

    if ops and str(ops.get("defect_origin") or "") and not origin:
        out.append(Drift("pending-rewind", "ops.defect_origin",
                         f"ops 已定 origin={ops.get('defect_origin')},"
                         "但 deliver.last_rewind 还没记 —— 回退没落实", "req"))

    state = {
        "stage": stage, "baseline_revision": b_rev, "sealed": bool(baseline.get("sealed")),
        "reopened": reopened, "origin": origin, "items": len(ids),
    }
    return out, state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--feature", required=True)
    parser.add_argument("--plan", action="store_true", help="only print the redo order")
    args = parser.parse_args()

    repo = args.repo or (Path(os.environ["IDEV_PRODUCT_REPO"])
                         if os.environ.get("IDEV_PRODUCT_REPO") else Path.cwd())
    home = doc_home.homes(repo.resolve(), args.feature)["task"]
    if not home.is_dir():
        print(f"BLOCKED no ticket home at {home}", file=sys.stderr)
        return 2

    drifts, state = scan(home)

    # The redo order is a forward slice: re-establish the basis from the
    # earliest drifting stage, so later stages are built on a current one.
    stages_hit = [s for s in ORDER if any(d.redo == s for d in drifts)]
    first = stages_hit[0] if stages_hit else None

    if args.plan:
        if not first:
            print("已对准,无需重做")
            return 0
        start = ORDER.index(first)
        print(f"从 {first} 开始,依次重新贯彻:")
        for s in ORDER[start:]:
            n = sum(1 for d in drifts if d.redo == s)
            mark = f"  ({n} 项待对准)" if n else ""
            print(f"  {s}{mark}")
        print()
        print("每一格仍走原有停问点:请签前 check-feature + stage-gate,签字仍要人确认用语。")
        return 1

    print(f"# realign  {args.feature}")
    print(f"# {home}")
    print(f"# stage={state['stage']}  baseline.revision={state['baseline_revision']}  "
          f"sealed={state['sealed']}  items={state['items']}"
          + (f"  rewind.origin={state['origin']}" if state["origin"] else "")
          + ("  (已解封)" if state["reopened"] else ""))
    print()

    if not drifts:
        print("realign PASS  所有阶段产物都对准当前基线")
        print()
        print("**对准 ≠ 做对了。** 这里只查「产物指向的基线还在不在、失效的签字清没清」。")
        print("内容是否忠实于订正后的需求,仍要人按 experts.md 过 + grill 拷问。")
        return 0

    groups: dict[str, list[Drift]] = {}
    for d in drifts:
        groups.setdefault(d.kind, []).append(d)

    labels = {
        "revision": "产物建在旧基线上",
        "dangling": "挂的基线 item 已不存在",
        "uncovered": "订正后的 item 没人覆盖",
        "unproven-item": "没有 case 在证明它",
        "stale-signoff": "按 schema 已失效,但仍是 true",
        "stale-evidence": "证的是旧需求",
        "pending-rewind": "回退没落实",
    }
    for kind, items in groups.items():
        print(f"## {labels.get(kind, kind)}  ({len(items)})")
        print()
        for d in items:
            print(f"  {tw.ljust(d.where, 36)} {d.detail}")
        print()

    print(f"realign FAIL  {len(drifts)} 处未对准")
    print()
    if first:
        start = ORDER.index(first)
        print(f"重做顺序(从最早的那一格起,确保后面建在当前基线上):")
        print("  " + " → ".join(ORDER[start:]))
        print()
    print("**失效的签字要清掉,不是留着**:下一轮会把它读成当前有效,")
    print("于是新需求被旧证据验收 —— 那正是 deliver-schema.md 要防的事。")
    print("清签字仍是人的动作;本工具只让漂移可见,不写任何文件。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
