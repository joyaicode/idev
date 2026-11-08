#!/usr/bin/env python3
"""knowledge.py 的测试：CJK bigram 切词、增量同步、检索、read-hash 复核、越界、doctor、questions。

检索结果只是资料，不是执行授权；候选/未过闸不作为已验证事实注入。测试重点
是「什么不该被索引/返回」：越界文件、过期条目、hash 不符的原文。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import knowledge  # noqa: E402


def _run(func, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = func(argparse.Namespace(**kw))
    return rc, buf.getvalue()


class Tokenize(unittest.TestCase):
    def test_cjk_bigram(self):
        self.assertEqual(knowledge.tokenize("实例账本"), "实例 例账 账本")
        self.assertEqual(knowledge.tokenize("账本"), "账本")
        self.assertEqual(knowledge.tokenize("采信"), "采信")

    def test_latin_lowercase(self):
        self.assertEqual(knowledge.tokenize("Hello World 123"), "hello world 123")

    def test_mixed(self):
        self.assertEqual(
            knowledge.tokenize("审批单 Approval 123"),
            "审批 批单 approval 123",
        )


class SearchQuery(unittest.TestCase):
    def test_drops_how_filler(self):
        query = knowledge._search_query("审批单如何创建")
        self.assertIn('"审批"', query)
        self.assertIn('"创建"', query)
        self.assertNotIn('"如何"', query)
        self.assertNotIn('"何创"', query)

    def test_expands_chinese_english_technical_synonyms(self):
        self.assertIn('"handler"', knowledge._search_query("审批处理器 SPI"))
        self.assertIn('"elasticsearch"', knowledge._search_query("弹性搜索"))


class KnowledgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "joypaas"
        (self.repo / "docs" / "design").mkdir(parents=True)
        (self.repo / "docs" / "adr").mkdir(parents=True)
        (self.repo / ".idev" / "pack").mkdir(parents=True)
        (self.repo / ".cursor").mkdir(parents=True)
        self.questions_path = self.root / "knowledge-questions.yaml"
        self._old = (
            knowledge.INDEX_DIR,
            knowledge.DB_PATH,
            knowledge.LOCK_PATH,
            knowledge.QUESTIONS_PATH,
        )
        knowledge.INDEX_DIR = self.root / "state" / "knowledge-index"
        knowledge.DB_PATH = knowledge.INDEX_DIR / "knowledge.db"
        knowledge.LOCK_PATH = knowledge.INDEX_DIR / "knowledge.lock"
        knowledge.QUESTIONS_PATH = self.questions_path

    def tearDown(self):
        (
            knowledge.INDEX_DIR,
            knowledge.DB_PATH,
            knowledge.LOCK_PATH,
            knowledge.QUESTIONS_PATH,
        ) = self._old
        self.tmp.cleanup()

    def _write(self, rel, text):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def _sync(self):
        return _run(knowledge.cmd_sync, repo=str(self.repo), feature="")

    def _search(self, query, **kw):
        kw.setdefault("feature", "")
        kw.setdefault("top", 10)
        kw.setdefault("json", False)
        return _run(knowledge.cmd_search, repo=str(self.repo), query=query, **kw)

    def _questions(self, questions):
        self.questions_path.write_text(
            json.dumps(questions, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _run_questions(self, questions=""):
        return _run(knowledge.cmd_questions, repo=str(self.repo), questions=questions)

    def test_sync_add_update_delete(self):
        self._write("docs/design/arch.md", "# 架构\n\n实例账本\n")
        rc, out = self._sync()
        self.assertEqual(rc, 0)
        self.assertIn("+1", out)

        # 内容变更 -> 重索引
        self._write("docs/design/arch.md", "# 架构\n\n实例账本 采信\n")
        rc, out = self._sync()
        self.assertIn("~1", out)

        # 删除 -> 从索引移除
        (self.repo / "docs/design/arch.md").unlink()
        rc, out = self._sync()
        self.assertIn("-1", out)

    def test_search_hit_and_miss(self):
        self._write("docs/design/arch.md", "# 架构总览\n\n实例账本 采信\n")
        self._write("docs/adr/0001.md", "# 审批单\n\n审批单创建\n")
        self._sync()
        _, out = self._search("账本")
        self.assertIn("docs/design/arch.md", out)
        _, out = self._search("审批单")
        self.assertIn("docs/adr/0001.md", out)
        _, out = self._search("不存在的词")
        self.assertIn("零命中", out)

    def test_search_empty_query_is_error(self):
        self._write("docs/design/arch.md", "# 架构\n\n实例账本\n")
        rc, out = self._search("")
        self.assertEqual(rc, 1)
        self.assertIn("empty query", out)

    def test_search_auto_syncs_new_and_deleted_sources(self):
        self._write("docs/design/arch.md", "# 架构\n\n实例账本\n")
        _, out = self._search("账本")
        self.assertIn("docs/design/arch.md", out)

        (self.repo / "docs/design/arch.md").unlink()
        _, out = self._search("账本")
        self.assertIn("零命中", out)

    def test_search_json(self):
        self._write("docs/design/arch.md", "# 架构\n\n实例账本\n")
        self._sync()
        rc, out = self._search("账本", json=True)
        self.assertEqual(rc, 0)
        import json as _json
        rows = _json.loads(out)
        self.assertEqual(rows[0]["path"], "docs/design/arch.md")
        self.assertEqual(rows[0]["status"], "doc")

    def test_read_hash_verify(self):
        self._write("docs/design/arch.md", "# 架构\n\n实例账本\n")
        self._sync()
        content = (self.repo / "docs/design/arch.md").read_text(encoding="utf-8")
        h = knowledge.sha256(content)
        rc, out = _run(knowledge.cmd_read, id=f"docs/design/arch.md:{h}", repo=str(self.repo))
        self.assertEqual(rc, 0)
        self.assertIn("实例账本", out)
        # 源已变 -> 拒绝
        rc, out = _run(knowledge.cmd_read, id="docs/design/arch.md:deadbeef", repo=str(self.repo))
        self.assertEqual(rc, 1)
        self.assertIn("refuse", out)

    def test_read_escape_refused(self):
        rc, out = _run(knowledge.cmd_read, id="../etc/passwd:deadbeef", repo=str(self.repo))
        self.assertEqual(rc, 1)
        self.assertIn("refuse", out)

    def test_exclude_boundary(self):
        self._write("docs/design/.env", "SECRET=1\n")
        self._write("docs/design/build/out.txt", "build artifact\n")
        self._write("docs/design/ok.md", "# ok\n\n正常文档\n")
        self._sync()
        _, out = self._search("SECRET")
        self.assertIn("零命中", out)
        _, out = self._search("artifact")
        self.assertIn("零命中", out)
        _, out = self._search("正常文档")
        self.assertIn("ok.md", out)

    def test_exclude_raw_material_stems(self):
        # 精读层原始材料（README 三层约定：不入库、可再生）不索引，
        # 避免 OCR/全文噪声把精读缺口的命中挤出 Top-N。
        self.assertTrue(knowledge._excluded("scripts/docs/notes/代码整洁之道-OCR.txt"))
        self.assertTrue(knowledge._excluded("scripts/docs/notes/重构-全文.txt"))
        self.assertFalse(knowledge._excluded("scripts/docs/notes/代码整洁之道-精读缺口.md"))

    def test_doctor_reports_orphan(self):
        self._write("docs/design/arch.md", "# 架构\n\n实例账本\n")
        self._sync()
        rc, _ = _run(knowledge.cmd_doctor, repo=str(self.repo))
        self.assertEqual(rc, 0)
        # 源删除后 doctor 报告孤儿
        (self.repo / "docs/design/arch.md").unlink()
        rc, out = _run(knowledge.cmd_doctor, repo=str(self.repo))
        self.assertEqual(rc, 1)
        self.assertIn("孤儿", out)

    def test_no_whitelist_repo(self):
        other = self.root / "unknown"
        other.mkdir()
        rc, out = _run(knowledge.cmd_sync, repo=str(other), feature="")
        self.assertEqual(rc, 1)
        self.assertIn("no whitelist", out)

    def test_resolve_repo_nonexistent_raises(self):
        # --repo 传仓库名（如 idev）会解析成 ./idev 不存在：拒绝而不是静默清空索引
        with self.assertRaises(FileNotFoundError):
            knowledge._resolve_repo(str(self.root / "does-not-exist"))

    def test_idev_whitelist_repo(self):
        idev = self.root / "idev"
        (idev / "conventions").mkdir(parents=True)
        (idev / "conventions" / "canon.md").write_text("# canon\n\n实例账本\n", encoding="utf-8")
        rc, out = _run(knowledge.cmd_sync, repo=str(idev), feature="")
        self.assertEqual(rc, 0)
        self.assertIn("+1", out)

    def test_questions_missing_file(self):
        rc, out = self._run_questions()
        self.assertEqual(rc, 2)
        self.assertIn("not found", out)

    def test_questions_empty_set(self):
        self._questions([])
        rc, out = self._run_questions()
        self.assertEqual(rc, 2)
        self.assertIn("empty question set", out)

    def test_questions_passes_at_90_percent(self):
        questions = []
        for i in range(1, 10):
            rel = f"docs/design/q{i}.md"
            self._write(rel, f"# 问题{i}\n\n唯一词{i} 账本\n")
            questions.append({
                "id": f"q{i}",
                "query": f"唯一词{i} 账本",
                "expect": [rel],
            })
        questions.append({
            "id": "q10",
            "query": "完全不存在的主题",
            "expect": ["docs/design/missing.md"],
        })
        self._questions(questions)
        rc, out = self._run_questions()
        self.assertEqual(rc, 0)
        self.assertIn("9/10", out)
        self.assertIn("MISS q10", out)

    def test_questions_fail_below_90_percent(self):
        questions = []
        for i in range(1, 9):
            rel = f"docs/design/q{i}.md"
            self._write(rel, f"# 问题{i}\n\n唯一词{i} 账本\n")
            questions.append({
                "id": f"q{i}",
                "query": f"唯一词{i} 账本",
                "expect": [rel],
            })
        for i in (9, 10):
            questions.append({
                "id": f"q{i}",
                "query": "完全不存在的主题",
                "expect": ["docs/design/missing.md"],
            })
        self._questions(questions)
        rc, out = self._run_questions()
        self.assertEqual(rc, 1)
        self.assertIn("8/10", out)
        self.assertIn("MISS q9", out)

    def test_questions_explicit_path(self):
        self._write("docs/design/arch.md", "# 架构\n\n实例账本 采信\n")
        self._sync()
        explicit = self.root / "explicit-questions.yaml"
        explicit.write_text(json.dumps([
            {"id": "explicit", "query": "实例账本",
             "expect": ["docs/design/arch.md"], "note": "hit"},
        ], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._questions([
            {"id": "default", "query": "完全不相干的词",
             "expect": ["docs/design/missing.md"], "note": "miss"},
        ])
        rc, out = self._run_questions(str(explicit))
        self.assertEqual(rc, 0)
        self.assertIn("PASS explicit", out)
        self.assertNotIn("default", out)

    def test_questions_default_path_when_not_specified(self):
        self._write("docs/design/arch.md", "# 架构\n\n实例账本 采信\n")
        self._sync()
        explicit = self.root / "explicit-questions.yaml"
        explicit.write_text(json.dumps([
            {"id": "explicit", "query": "完全不相干的词",
             "expect": ["docs/design/missing.md"], "note": "miss"},
        ], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._questions([
            {"id": "default", "query": "实例账本",
             "expect": ["docs/design/arch.md"], "note": "hit"},
        ])
        rc, out = self._run_questions()
        self.assertEqual(rc, 0)
        self.assertIn("PASS default", out)
        self.assertNotIn("explicit", out)

    def test_questions_threshold_and_miss(self):
        # questions 回归：门槛按 len*9//10；过线 PASS 退出 0，差一条退出 1。
        # 用临时问题集钉住判定（不碰真 state/knowledge-questions.yaml）。
        questions = [
            {"id": "q1", "query": "实例账本",
             "expect": ["docs/design/arch.md"], "note": "hit"},
            {"id": "q2", "query": "完全不相干的词",
             "expect": ["docs/design/arch.md"], "note": "miss"},
        ]
        old = knowledge.QUESTIONS_PATH
        qfile = self.root / "knowledge-questions.yaml"
        import yaml as _yaml
        qfile.write_text(_yaml.safe_dump(questions, allow_unicode=True), encoding="utf-8")
        knowledge.QUESTIONS_PATH = qfile
        try:
            self._write("docs/design/arch.md", "# 架构\n\n实例账本 采信\n")
            self._sync()
            # 2 条门槛 = 2*9//10 = 1；1 命中 >= 1 -> PASS
            rc, out = self._run_questions()
            self.assertEqual(rc, 0)
            self.assertIn("1/2", out)
            self.assertIn("PASS q1", out)
            self.assertIn("MISS q2", out)
            # 两条全 miss -> 退出 1
            questions[0]["expect"] = ["docs/design/none.md"]
            qfile.write_text(_yaml.safe_dump(questions, allow_unicode=True), encoding="utf-8")
            rc, out = self._run_questions()
            self.assertEqual(rc, 1)
        finally:
            knowledge.QUESTIONS_PATH = old


if __name__ == "__main__":
    unittest.main()
