#!/usr/bin/env python3
"""A SUGGEST that names the same kernel thing twice becomes a weekly-review signal.

    python3 scripts/test_suggest_review.py
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOW = dt.datetime.now().astimezone().isoformat(timespec="seconds")


def report(suggest: str, conclusion: str = "已审完。") -> str:
    return (
        "STATUS: PASS\nEVIDENCE: review.md\nFACTS: codegraph 查到 src/app.py:main\nDOC_DRIFT: 无\n"
        f"ASSUMED: 无\nSUGGEST:{(' ' + suggest) if suggest else ''}\nCONCLUSION: {conclusion}\n"
    )


class SuggestReview(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        (self.repo / ".git").mkdir(parents=True)
        self.base = self.repo / ".idev" / "task" / "feat" / "workflow" / "delegations" / "R1"
        self.base.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def record(self, step: str, said: str, **extra) -> None:
        brief = {"ticket_home": ".idev/task/feat", "repo": ".", "stage": "code",
                 "must_read": "conventions/coding.md", "idev_root": str(HERE.parent)}
        body = {"schema_version": 1, "feature": "feat", "step": step, "kind": "review.report",
                "agent": "idev-reviewer", "attempt": 1, "at": NOW, "brief": brief,
                "report": {"status": "PASS", "raw": report(said)}, **extra}
        (self.base / f"{step}-1.yaml").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")

    def metrics(self, *args: str) -> str:
        done = subprocess.run([sys.executable, str(HERE / "agent-metrics.py"), "--repo", str(self.repo), *args],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_two_suggestions_about_one_script_raise_a_signal(self) -> None:
        self.record("report", "coding-scan.sh 的 find 管道扫进 node_modules 被 head 截断")
        self.record("rereport", "coding-scan 只打印语言和指南，不产出逐文件命中")
        out = self.metrics("--signal")
        self.assertIn("signal=yes", out)
        self.assertIn("HIT suggest coding-scan.sh: 2 条(≥2)", out)

    def test_one_suggestion_is_listed_but_raises_nothing(self) -> None:
        self.record("report", "fix 类委派统一用「方法名 + 第 N 个该构造」式定位")
        self.record("other", "", suggest="CONCLUSION: 11 条 selftest 都是 PASS。")
        self.assertIn("signal=no", self.metrics("--signal"))
        listed = self.metrics("--suggestions")
        self.assertIn("fix 类委派统一用「方法名 + 第 N 个该构造」式定位", listed)
        self.assertNotIn("selftest", listed)

    def test_the_weekly_review_carries_the_suggestions(self) -> None:
        self.record("report", "coding-scan.sh 的 find 管道扫进 node_modules 被 head 截断")
        self.record("rereport", "coding-scan 只打印语言和指南，不产出逐文件命中")
        done = subprocess.run(
            ["bash", str(HERE / "agent-review.sh"), "--repo", str(self.repo), "--out", str(Path(self._tmp.name) / "out"),
             "--dry-run"],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("signal=yes", done.stdout)
        self.assertIn("## agent 的建议", done.stdout)
        self.assertIn("coding-scan 只打印语言和指南", done.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
