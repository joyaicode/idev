#!/usr/bin/env python3
"""Per-ticket factual metrics from idev traces and the feature deliver.yaml.
Facts only, no scoring. Unknown -> n/a (never guessed)."""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from doc_home import homes  # noqa: E402
from product_sink import product_repo  # noqa: E402

try:
    import yaml
except ImportError:
    raise SystemExit("ticket-metrics requires PyYAML")

REOPEN_RE = re.compile(r"(解除密封|reopen)", re.I)
OVERTURN_RE = re.compile(r"(作废|推翻|回退|rewind|overturn|invalidate)", re.I)


def parse_at(s):
    try:
        return datetime.fromisoformat(str(s).strip())
    except Exception:
        return None


def load(p: Path):
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8", errors="replace"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def find_repo(arg: str | None) -> Path | None:
    """--repo, else the product checkout around cwd. The install ledger is not the session."""
    if arg:
        return Path(arg).expanduser()
    return product_repo()


def main() -> int:
    args = sys.argv[1:]
    root = Path(__file__).resolve().parent.parent
    repo_arg = None
    if "--repo" in args:
        i = args.index("--repo")
        repo_arg = args[i + 1]
    repo = find_repo(repo_arg)
    if repo is not None:
        tdir = repo / ".idev" / "traces"
    else:
        tdir = root / "state" / "traces"

    per: dict[str, dict] = {}
    for f in sorted(tdir.glob("*.yaml")):
        d = load(f)
        feat = str(d.get("feature") or "-")
        at = parse_at(d.get("at"))
        sc = (d.get("route") or {}).get("scenario") if isinstance(d.get("route"), dict) else None
        e = per.setdefault(feat, {"ats": [], "traces": 0, "s2": 0})
        e["traces"] += 1
        if at:
            e["ats"].append(at)
        if sc == "S2":
            e["s2"] += 1

    print("# ticket-metrics（事实汇总，不打分）")
    print(f"traces: {tdir}")
    print(f"tickets repo: {repo if repo else 'n/a (未指定 --repo，当前目录也不在产品仓)'}")
    print()
    print("| feature | traces | 首次 trace | 最近 trace | 跨度(天) | S2 推进次数 | reopen 次数 | 签字后被推翻次数 |")
    print("|---------|--------|-----------|-----------|---------|-------------|-------------|------------------|")
    for feat in sorted(per, key=lambda k: (k == "-", k)):
        e = per[feat]
        ats = sorted(e["ats"])
        first = ats[0].date().isoformat() if ats else "n/a"
        last = ats[-1].date().isoformat() if ats else "n/a"
        span = str((ats[-1].date() - ats[0].date()).days) if ats else "n/a"
        reopen = overturn = "n/a"
        if feat != "-" and repo:
            y = homes(repo, feat)["deliver"]
            if y.exists():
                dy = load(y)
                revs = dy.get("revisions") if isinstance(dy.get("revisions"), list) else []
                notes = [str((r or {}).get("note", "")) for r in revs if isinstance(r, dict)]
                by_note = sum(1 for n in notes if REOPEN_RE.search(n))
                br = dy.get("baseline_revision")
                by_rev = (br - 1) if isinstance(br, int) and br > 1 else 0
                reopen = str(max(by_note, by_rev))
                ov = sum(1 for n in notes if OVERTURN_RE.search(n))
                if dy.get("last_rewind") and ov == 0:
                    ov = 1  # last_rewind present = at least one recorded rewind
                overturn = str(ov)
        print(f"| {feat} | {e['traces']} | {first} | {last} | {span} | {e['s2']} | {reopen} | {overturn} |")
    print()
    print("口径：S2=trace 中 route.scenario 为 S2 的条数；reopen=max(revisions[] 备注含「解除密封/reopen」条数, baseline_revision-1)；")
    print("被推翻=revisions[] 备注含「作废/推翻/回退/rewind」条数（仅有 last_rewind 时记 1，为下界）；无票 yaml / 未绑票 → n/a。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
