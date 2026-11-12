#!/usr/bin/env python3
"""deep-read-audit --pending-gaps: inventory 真缺口 entries by landing state.

Complements audit(): that answers "did landed numbers reach code", this
answers "did each report's own gaps get landed at all". The cases pin the
three landing signals (item marker, section note, proposed number now
defined) and the shapes that must NOT count.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("dra", ROOT / "scripts" / "deep-read-audit.py")
dra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dra)

LANDED_ITEM = """## 一、精读范围

x

## 二、对照结论

已由 T1 承载。

## 三、真缺口

### 1. 已落地的一条

**书中依据**：第 1 条。
**落点**（已于 12ab1c4 落地）：canon.md T14 的 DO 增补。

## 四、重点候选裁定

无。
"""

PENDING_ITEM = """## 一、精读范围

x

## 二、对照结论

已由 T1 承载。

## 三、真缺口

### 1. 还没落地的一条

**书中依据**：第 2 条。
**落点**：canon.md T14 的 DO 增补。

## 四、重点候选裁定

无。
"""

PROPOSED_NOW_DEFINED = """## 三、真缺口

### 1. 建议新增编号且编号已在真源

**书中依据**：第 3 条。
**建议落点**：`conventions/coding-tables.md` §2 末尾新增 C33：循环不变式。

## 四、重点候选裁定

无。
"""

CITES_KIN_NOT_LANDED = """## 三、真缺口

### 1. 只引用近邻编号的一条

**书中依据**：第 4 条。
**落点**：deliver/SKILL.md arch 步骤 5。多步骤业务流程先分析工作流（T3 / T4 / T10 / C23）。

## 四、重点候选裁定

无。
"""

STATED_ZERO = """## 三、真缺口

无。本书可推广的工程原则已由 T1/T3/T4 承载。

## 四、重点候选裁定

无。
"""

SECTION_NOTE = """## 二、对照结论

### 2. 两批真缺口（2 条，均已落地）

## 三、真缺口

### 1. 靠节级标记落地的一条

**书中依据**：第 5 条。
**落点**：domain-modeling.md 新增一节。
"""


class PendingGaps(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.kernel = Path(self.tmp.name)
        notes = self.kernel / "scripts" / "docs" / "notes"
        notes.mkdir(parents=True)
        self.notes = notes
        tables = self.kernel / "conventions"
        tables.mkdir()
        (tables / "coding-tables.md").write_text("| C33 | x | y |\n", encoding="utf-8")
        (tables / "canon.md").write_text("### T14\n\nx\n", encoding="utf-8")

    def write(self, name: str, text: str) -> None:
        (self.notes / name).write_text(text, encoding="utf-8")

    def test_landed_item_marker(self) -> None:
        self.write("a-精读缺口.md", LANDED_ITEM)
        entries, unparsed = dra.pending_gaps(self.kernel)
        self.assertEqual((len(entries), unparsed), (1, []))
        self.assertTrue(entries[0]["landed"])

    def test_pending_item(self) -> None:
        self.write("a-精读缺口.md", PENDING_ITEM)
        entries, _ = dra.pending_gaps(self.kernel)
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]["landed"])

    def test_proposed_number_now_defined_counts(self) -> None:
        self.write("a-精读缺口.md", PROPOSED_NOW_DEFINED)
        entries, _ = dra.pending_gaps(self.kernel)
        self.assertTrue(entries[0]["landed"])

    def test_citing_kin_numbers_is_not_landed(self) -> None:
        self.write("a-精读缺口.md", CITES_KIN_NOT_LANDED)
        entries, _ = dra.pending_gaps(self.kernel)
        self.assertFalse(entries[0]["landed"])

    def test_stated_zero_is_not_unparsed(self) -> None:
        self.write("a-精读缺口.md", STATED_ZERO)
        entries, unparsed = dra.pending_gaps(self.kernel)
        self.assertEqual((entries, unparsed), ([], []))

    def test_section_level_landed_note(self) -> None:
        self.write("a-精读缺口.md", SECTION_NOTE)
        entries, _ = dra.pending_gaps(self.kernel)
        self.assertTrue(entries[0]["landed"])


if __name__ == "__main__":
    unittest.main()
