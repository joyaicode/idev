#!/usr/bin/env python3
"""Locks for knowledge-metrics: §0 extraction, reviewer citations, the
static×runtime matrix, and the zero-hit classification.

Run directly (python3 scripts/test_knowledge_metrics.py) or through
selfcheck.sh. Fixtures are temp directories; the static-layer assertions
run against the real conventions/ pages (they are the contract being
measured, and deep-read-audit's own test already locks the audit itself).
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
sys.path.insert(0, str(HERE))

FAILURES: list[str] = []


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


km = _load("knowledge_metrics_test", "knowledge-metrics.py")


def check(label: str, got, want) -> None:
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"ok   {label}")


CODER_RECORD = """schema_version: 1
feature: f1
step: fix
kind: review.fix
agent: idev-coder
at: 2026-11-08T10:00:00+08:00
attempt: 1
report:
  status: PASS
  raw: |
    STATUS: PASS
    EVIDENCE: docs/task/f1/review.md
    CHANGE_KIND: 行为修正
    CANON_TRIGGER: 拆分
    TABLE_HIT: P15（缺值也当成功往下走）
    HITS: §1 1 命中已改 / §2 已扫 / T8 T6
"""

REVIEW_RECORD = """schema_version: 1
feature: f1
step: report
kind: review.report
agent: idev-reviewer
at: 2026-11-08T09:00:00+08:00
attempt: 1
report:
  status: PASS
  evidence: docs/task/f1/review.md
  raw: |
    STATUS: PASS
    EVIDENCE: docs/task/f1/review.md
"""


def test_coder_facts() -> None:
    record = {
        "agent": "idev-coder",
        "report": {"raw": CODER_RECORD.split("raw: |\n", 1)[1]},
    }
    facts = km.coder_facts(record)
    check("canon trigger", facts["canon_trigger"], "拆分")
    check("table hit text", facts["table_hit"], "P15（缺值也当成功往下走）")
    check("T hits", facts["hits"], ["T6", "T8"])
    # a record without §0 lines is not a coder §0 sample
    check("no s0 lines -> None", km.coder_facts({"report": {"raw": "STATUS: PASS\n"}}), None)
    # real-world TABLE_HIT shapes: declared non-hits must not count
    check("non-hit range excluded",
          km.hit_numbers("P15（已改为抛错）。P1–P14 不命中。"), {"P15"})
    check("multiple hits", km.hit_numbers("C5（注释只写不变量）、C7（吞异常补 log.warn）"), {"C5", "C7"})
    check("zero-hit line", km.hit_numbers("零命中"), set())


def test_matrix_and_classify() -> None:
    kernel = HERE.parent
    coder = [("x", {
        "agent": "idev-coder",
        "report": {"raw": CODER_RECORD.split("raw: |\n", 1)[1]},
    })]
    cites: Counter = Counter({"R1": 1})  # an enforced-covered C# would collide with citations; use R1 (plain row)
    rows, s0_total = km.matrix(kernel, coder, cites)
    check("s0 sample count", s0_total, 1)
    by_id = {r["id"]: r for r in rows}
    check("all 93+ numbers present", len(rows) >= 93, True)
    check("P15 runtime hit", by_id["P15"]["hits"], 1)
    check("T8 runtime hit (HITS line)", by_id["T8"]["hits"], 1)
    # classification follows deep-read-audit's layers
    enforced = [r["id"] for r in rows if r["enforced"]]
    check("enforced rows exist", len(enforced) >= 4, True)
    check("enforced zero-hit is fine",
          km.classify({"id": enforced[0], "hits": 0, "cites": 0, "hit_fail": 0,
                       "enforced": True, "staged": False, "trigger": False}),
          "no-hit-needed")
    check("hit row classifies as hit", km.classify(by_id["P15"]), "hit")
    wording = [r["id"] for r in rows if km.classify(r) == "wording-candidate"]
    check("wording candidates are trigger-only rows", bool(wording), True)


def test_collect_and_citations() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        home = repo / "docs/task/f1/workflow/delegations/r1"
        home.mkdir(parents=True)
        (home / "fix-1.yaml").write_text(CODER_RECORD, encoding="utf-8")
        (home / "report-1.yaml").write_text(REVIEW_RECORD, encoding="utf-8")
        review = repo / "docs/task/f1/review.md"
        review.parent.mkdir(parents=True, exist_ok=True)
        review.write_text("发现 C12 与 P15 各一处;T8 触发。\n", encoding="utf-8")
        shards = repo / "docs/task/f1/review/shards"
        shards.mkdir(parents=True)
        (shards / "s1.md").write_text("C22 在分片里。\n", encoding="utf-8")

        coder, reviewer = km.collect(repo, days=None)
        check("coder records", len(coder), 1)
        check("reviewer records", len(reviewer), 1)
        counter = km.reviewer_citations(reviewer, repo)
        check("review.md citations", (counter["C12"], counter["P15"], counter["T8"]), (1, 1, 1))
        check("shard citations counted", counter["C22"], 1)


def test_static_only_mode() -> None:
    """--kernel without --repo: the matrix degrades to static columns."""
    kernel = HERE.parent
    rows, s0_total = km.matrix(kernel, [], Counter())
    check("no coder records", s0_total, 0)
    check("static rows still 93+", len(rows) >= 93, True)


def main() -> int:
    test_coder_facts()
    test_matrix_and_classify()
    test_collect_and_citations()
    test_static_only_mode()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nall knowledge-metrics locks hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
