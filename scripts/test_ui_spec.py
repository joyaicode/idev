#!/usr/bin/env python3
"""ui 块要能单独点中，并且写明进行中看到什么。"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("ui_spec", SCRIPTS / "ui-spec.py")
ui_spec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui_spec)  # type: ignore[union-attr]


def _action(name: str = "保存") -> dict:
    return {
        "name": name,
        "on_success": "页面显示已保存",
        "on_failure": "页面显示失败，可以再试",
        "on_pending": "按钮禁用并显示保存中",
    }


def _item(actions: list, fields: list | None = None, screen: str = "资料", iid: str = "B1") -> dict:
    ui = {
        "screen": screen,
        "intent": "改完能看见结果",
        "states": {"loading": "骨架", "error": "网络不可用"},
        "actions": actions,
    }
    if fields:
        ui["fields"] = fields
    return {"id": iid, "ui": ui}


class SurfaceTest(unittest.TestCase):
    def test_pending_and_a_unique_name_pass(self) -> None:
        findings: list[str] = []
        ui_spec.check_ui([_item([_action()])], findings)
        self.assertEqual(findings, [])

    def test_missing_pending_is_reported(self) -> None:
        action = _action()
        action.pop("on_pending")
        findings: list[str] = []
        ui_spec.check_ui([_item([action])], findings)
        self.assertTrue(any("on_pending" in item for item in findings))

    def test_the_same_name_on_one_screen_is_reported(self) -> None:
        findings: list[str] = []
        ui_spec.check_ui([_item([_action("确认"), _action("确认")])], findings)
        self.assertTrue(any("确认" in item for item in findings))
        other = _item([_action("确认")], screen="订单", iid="B2")
        separate: list[str] = []
        ui_spec.check_ui([_item([_action("确认")]), other], separate)
        self.assertFalse(any("确认" in item and "出现了" in item for item in separate))

    def test_the_same_label_across_items_on_one_screen_is_reported(self) -> None:
        field = {"name": "address", "label": "地址", "type": "text", "rule": "非空"}
        first = _item([_action("寄")], [field], iid="B1")
        second = _item([_action("寄")], [dict(field, name="ship")], iid="B2")
        findings: list[str] = []
        ui_spec.check_ui([first, second], findings)
        self.assertTrue(any("地址" in item for item in findings))
        self.assertTrue(any("寄" in item for item in findings))

    def test_the_same_name_in_two_scopes_can_both_be_pointed_at(self) -> None:
        dialog = _action("确认")
        dialog["scope"] = "补发对话框"
        table = _action("确认")
        table["scope"] = "表格"
        findings: list[str] = []
        ui_spec.check_ui([_item([dialog, table])], findings)
        self.assertFalse(any("出现了" in item for item in findings))

    def test_pending_and_success_must_be_different_sentences(self) -> None:
        action = _action()
        action["on_success"] = action["on_pending"]
        findings: list[str] = []
        ui_spec.check_ui([_item([action])], findings)
        self.assertTrue(any("同一句" in item for item in findings))


if __name__ == "__main__":
    unittest.main()
