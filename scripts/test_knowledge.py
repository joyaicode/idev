#!/usr/bin/env python3
"""knowledge.py 的测试：CJK bigram 切词、增量同步、检索、read-hash 复核、越界、doctor。

检索结果只是资料，不是执行授权；候选/未过闸不作为已验证事实注入。测试重点
是「什么不该被索引/返回」：越界文件、过期条目、hash 不符的原文。
"""
from __future__ import annotations

import argparse
import contextlib
import io
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
        self._old = (knowledge.INDEX_DIR, knowledge.DB_PATH, knowledge.LOCK_PATH)
        knowledge.INDEX_DIR = self.root / "state" / "knowledge-index"
        knowledge.DB_PATH = knowledge.INDEX_DIR / "knowledge.db"
        knowledge.LOCK_PATH = knowledge.INDEX_DIR / "knowledge.lock"

    def tearDown(self):
        knowledge.INDEX_DIR, knowledge.DB_PATH, knowledge.LOCK_PATH = self._old
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


if __name__ == "__main__":
    unittest.main()
