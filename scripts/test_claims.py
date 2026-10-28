#!/usr/bin/env python3
"""Cases for the ticket claim index. Each test maps to one case_intent."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "claims.py"
REALIGN = ROOT / "scripts" / "realign.py"
LESSONS = ROOT / "scripts" / "lessons.py"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ClaimIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.ticket = self.repo / ".idev" / "task" / "demo"
        write(self.ticket / "baseline.yaml", "revision: 1\nitems:\n  - id: B1\n    must: 索引只在票目录\n")
        write(self.ticket / "deliver.yaml", "stage: code\n")
        write(
            self.ticket / "req.yaml",
            "slices:\n  - id: s1\n    baseline_item_id: B1\n    must: 索引只在票目录\n    must_not: 无\n",
        )
        write(self.ticket / "design.md", "方案正文，没有主张行。\n")
        write(self.repo / "scripts" / "lessons.py", "# ledger\n")
        write(self.repo / "scripts" / "realign.py", "# drift\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_claims(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--repo", str(self.repo)],
            capture_output=True,
            text=True,
        )

    def test_ops_exist(self):
        for command in ("ingest", "query", "calibrate"):
            result = self.run_claims(command, "--feature", "demo", "--subject", "B1")
            self.assertNotEqual(result.returncode, 2, result.stderr)
        ingested = self.run_claims("ingest", "--feature", "demo")
        self.assertEqual(ingested.returncode, 0, ingested.stdout + ingested.stderr)
        queried = self.run_claims("query", "--feature", "demo", "--subject", "B1")
        self.assertEqual(queried.returncode, 0, queried.stderr)
        calibrated = self.run_claims("calibrate", "--feature", "demo")
        self.assertEqual(calibrated.returncode, 0, calibrated.stdout)

    def test_no_extra(self):
        imports = [
            line
            for line in SCRIPT.read_text(encoding="utf-8").splitlines()
            if line.startswith("import ") or line.startswith("from ")
        ]
        blob = "\n".join(imports)
        self.assertNotIn("lessons", blob)
        self.assertNotIn("realign", blob)
        self.assertNotIn("check-feature", blob)
        self.assertNotIn("requests", blob)
        before = (ROOT / "scripts" / "check-feature.py").read_bytes()
        self.run_claims("ingest", "--feature", "demo")
        self.assertEqual(before, (ROOT / "scripts" / "check-feature.py").read_bytes())

    def test_source_required(self):
        write(self.ticket / "design.md", "主张: 这句话不在来源里 | 来源: missing.txt\n")
        failed = self.run_claims("ingest", "--feature", "demo")
        self.assertEqual(failed.returncode, 1)
        self.assertFalse((self.ticket / "claims.yaml").exists())
        self.assertIn("missing.txt", failed.stdout)
        write(self.ticket / "design.md", "方案正文，没有主张行。\n")
        self.assertEqual(self.run_claims("ingest", "--feature", "demo").returncode, 0)
        queried = self.run_claims("query", "--feature", "demo", "--subject", "B1")
        self.assertIn("baseline.yaml", queried.stdout)

    def test_ticket_only(self):
        self.assertEqual(self.run_claims("ingest", "--feature", "demo").returncode, 0)
        found = list(self.repo.rglob("claims.yaml"))
        self.assertEqual(found, [self.ticket / "claims.yaml"])

    def test_claim_from_artifact(self):
        write(self.ticket / "notes.md", "主张: 只在聊天里 | 来源: baseline.yaml\n")
        write(self.repo / "src" / "rule.txt", "工件里的这一句\n")
        write(
            self.ticket / "design.md",
            "普通叙述不产生记录。\n主张: 工件里的这一句 | 来源: src/rule.txt\n",
        )
        self.assertEqual(self.run_claims("ingest", "--feature", "demo").returncode, 0)
        chat = self.run_claims("query", "--feature", "demo", "--subject", "只在聊天里")
        self.assertNotEqual(chat.returncode, 0)
        indexed = (self.ticket / "claims.yaml").read_text(encoding="utf-8")
        self.assertNotIn("只在聊天里", indexed)
        self.assertIn("工件里的这一句", indexed)

    def test_conflict_nonzero(self):
        write(self.repo / "src" / "rule.txt", "甲说法\n乙说法\n")
        write(
            self.ticket / "design.md",
            "主张: 甲说法 | 来源: src/rule.txt | 主题: rule\n"
            "主张: 乙说法 | 来源: src/rule.txt | 主题: rule\n",
        )
        self.assertEqual(self.run_claims("ingest", "--feature", "demo").returncode, 0)
        result = self.run_claims("calibrate", "--feature", "demo")
        self.assertEqual(result.returncode, 1)
        self.assertIn("src/rule.txt", result.stdout)

    def test_ledgers_stay(self):
        before_lessons = LESSONS.read_bytes()
        before_realign = REALIGN.read_bytes()
        local_lessons = (self.repo / "scripts" / "lessons.py").read_bytes()
        local_realign = (self.repo / "scripts" / "realign.py").read_bytes()
        self.assertEqual(self.run_claims("ingest", "--feature", "demo").returncode, 0)
        self.assertEqual(LESSONS.read_bytes(), before_lessons)
        self.assertEqual(REALIGN.read_bytes(), before_realign)
        self.assertEqual((self.repo / "scripts" / "lessons.py").read_bytes(), local_lessons)
        self.assertEqual((self.repo / "scripts" / "realign.py").read_bytes(), local_realign)
        imports = [
            line
            for line in SCRIPT.read_text(encoding="utf-8").splitlines()
            if line.startswith("import ") or line.startswith("from ")
        ]
        blob = "\n".join(imports)
        self.assertNotIn("lessons", blob)
        self.assertNotIn("realign", blob)

    def test_guard_doc(self):
        write(self.repo / "src" / "rule.txt", "甲说法\n乙说法\n")
        design = "主张: 甲说法 | 来源: src/rule.txt | 主题: rule\n主张: 乙说法 | 来源: src/rule.txt | 主题: rule\n"
        write(self.ticket / "design.md", design)
        self.assertEqual(self.run_claims("ingest", "--feature", "demo").returncode, 0)
        before = {
            name: (self.ticket / name).read_bytes()
            for name in ("design.md", "req.yaml", "verify/plan.yaml")
            if (self.ticket / name).is_file()
        }
        result = self.run_claims("calibrate", "--feature", "demo")
        self.assertEqual(result.returncode, 1)
        for name, body in before.items():
            self.assertEqual((self.ticket / name).read_bytes(), body)

    def test_guard_code(self):
        code = self.repo / "src" / "rule.txt"
        write(code, "索引只在票目录\n")
        write(self.ticket / "design.md", "主张: 索引只在票目录 | 来源: src/rule.txt\n")
        other = self.repo / "src" / "other.txt"
        write(other, "untouched\n")
        self.assertEqual(self.run_claims("ingest", "--feature", "demo").returncode, 0)
        # Break the indexed sentence without going through ingest.
        saved = (self.ticket / "claims.yaml").read_text(encoding="utf-8")
        (self.ticket / "claims.yaml").write_text(saved.replace("索引只在票目录", "对不上的句子"), encoding="utf-8")
        named = self.run_claims("guard", "--feature", "demo", "--path", "src/rule.txt")
        self.assertEqual(named.returncode, 1)
        self.assertEqual(code.read_text(encoding="utf-8"), "索引只在票目录\n")
        unnamed = self.run_claims("guard", "--feature", "demo", "--path", "src/other.txt")
        self.assertEqual(unnamed.returncode, 0)
        self.assertEqual(other.read_text(encoding="utf-8"), "untouched\n")


if __name__ == "__main__":
    unittest.main()
