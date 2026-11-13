#!/usr/bin/env python3
"""drive_mode resolve / set / process-eval auto / decide --source auto."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / "lib"))

import drive_mode  # noqa: E402

pe_spec = importlib.util.spec_from_file_location("process_eval", HERE / "process-eval.py")
pe = importlib.util.module_from_spec(pe_spec)
pe_spec.loader.exec_module(pe)


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HERE / "drive-mode.py"), *args],
        capture_output=True, text=True, check=False,
    )


def run_pe(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HERE / "process-eval.py"), *args],
        capture_output=True, text=True, check=False,
    )


class Resolve(unittest.TestCase):
    def test_session_beats_product_beats_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            idev = repo / ".idev"
            idev.mkdir()
            (idev / "marker.yaml").write_text("marker: idev\nid: demo\n", encoding="utf-8")
            (idev / "workflow-defaults.yaml").write_text("drive_mode: auto\n", encoding="utf-8")
            mode, source = drive_mode.resolve(repo, repo / "kernel-state")
            self.assertEqual((mode, source), ("auto", "product"))
            drive_mode.set_mode(repo, "assisted", by="tester", kernel_state=repo / "kernel-state")
            mode, source = drive_mode.resolve(repo, repo / "kernel-state")
            self.assertEqual((mode, source), ("assisted", "session"))
            drive_mode.clear(repo, repo / "kernel-state")
            mode, source = drive_mode.resolve(repo, repo / "kernel-state")
            self.assertEqual((mode, source), ("auto", "product"))

    def test_kernel_checkout_uses_state_not_dot_idev(self):
        from roots import kernel_root  # noqa: WPS433

        kernel = kernel_root()
        state = kernel / "state"
        path = drive_mode.session_path(kernel, state)
        self.assertEqual(path, state / "drive-mode.yaml")
        mode, source = drive_mode.resolve(kernel, state)
        # Whatever is on disk; source must not be product for the kernel tree.
        self.assertIn(source, {"session", "default"})
        self.assertNotEqual(source, "product")

    def test_cli_set_and_show(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / ".idev").mkdir()
            done = run_cli("--repo", str(repo), "set", "auto", "--by", "tester")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("mode=auto", done.stdout)
            shown = run_cli("--repo", str(repo), "show")
            self.assertIn("mode=auto", shown.stdout)
            self.assertIn("source=session", shown.stdout)

    def test_normalize_and_quote_mode_i18n(self):
        self.assertEqual(drive_mode.normalize("自動模式"), "auto")
        self.assertEqual(drive_mode.normalize("非自動"), "assisted")
        self.assertEqual(drive_mode.normalize("協助"), "assisted")
        self.assertEqual(drive_mode.quote_mode("開啟自動模式"), "auto")
        self.assertEqual(drive_mode.quote_mode("關閉自動"), "assisted")
        self.assertEqual(
            drive_mode.quote_mode("ｄｒｉｖｅ ａｕｔｏ"),
            "auto",
        )
        self.assertIsNone(drive_mode.quote_mode("開啟自動模式吧"))


class ProcessEvalAuto(unittest.TestCase):
    def test_soft_hold_autos_with_recommend(self):
        done = run_pe(
            "stop", "--drive", "auto", "--recommend", "1",
            "--stop", "请确认 SIGNAL 未决", "--signals", "SIGNAL foo",
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("now=CORRECT", done.stdout)
        self.assertIn("id=drive-auto", done.stdout)
        self.assertIn("--source auto", done.stdout)
        self.assertIn("--all-open", done.stdout)

    def test_hard_hold_never_autos(self):
        done = run_pe(
            "stop", "--drive", "auto", "--recommend", "1",
            "--stop", "解除密封",
        )
        self.assertIn("now=ASK", done.stdout)
        self.assertIn("id=real-hold", done.stdout)
        self.assertNotIn("id=drive-auto", done.stdout)

    def test_hard_hold_ascii_case_insensitive(self):
        self.assertTrue(drive_mode.hard_held("please Promote this"))
        self.assertTrue(drive_mode.hard_held("Reopen the baseline"))
        self.assertTrue(pe.hard_held("please Promote this"))
        self.assertFalse(drive_mode.hard_held("promotion plan"))
        self.assertFalse(drive_mode.hard_held("reopening discussion"))
        self.assertEqual(drive_mode.report_status("  STATUS: PASS\n"), "PASS")
        self.assertEqual(
            drive_mode.resolve_signal_recommend(
                "  STATUS: PASS\n  RECOMMEND: 1\n", ["[承重] x"],
            ),
            ("1", "auto:recommend"),
        )

    def test_hard_hold_prod_write_not_non_prod(self):
        self.assertTrue(drive_mode.hard_held("请确认生产写入"))
        self.assertTrue(drive_mode.hard_held("准备生产发布"))
        self.assertFalse(drive_mode.hard_held("非生产环境只读"))
        self.assertFalse(drive_mode.hard_held("非生产写"))
        self.assertFalse(drive_mode.hard_held("非生产发布"))
        self.assertFalse(drive_mode.hard_held("未生产写"))
        self.assertFalse(drive_mode.hard_held("确认生产配置"))
        self.assertFalse(drive_mode.hard_held_signal("[承重] 生产库是空的"))
        self.assertTrue(drive_mode.hard_held("请确认回退"))
        self.assertTrue(drive_mode.hard_held("请确认回滚"))
        self.assertTrue(drive_mode.hard_held("请确认回滾"))
        self.assertTrue(drive_mode.hard_held("please rollback"))
        self.assertTrue(drive_mode.hard_held("please roll back"))
        self.assertTrue(drive_mode.hard_held("please unseal"))
        self.assertTrue(drive_mode.hard_held("请确认启封"))
        self.assertTrue(drive_mode.hard_held("请确认开封"))
        self.assertTrue(drive_mode.hard_held("write to production"))
        self.assertTrue(drive_mode.hard_held("production write"))
        self.assertTrue(drive_mode.hard_held("deploy to production"))
        self.assertTrue(drive_mode.hard_held("准备上线生产"))
        self.assertFalse(drive_mode.hard_held("不回退"))
        self.assertFalse(drive_mode.hard_held("不回滚"))
        self.assertFalse(drive_mode.hard_held("no rollback"))
        self.assertFalse(drive_mode.hard_held("do not roll back"))
        self.assertFalse(drive_mode.hard_held("do not unseal"))
        self.assertFalse(drive_mode.hard_held("no unseal"))
        self.assertFalse(drive_mode.hard_held("不要启封"))
        self.assertFalse(drive_mode.hard_held("no production write"))
        self.assertFalse(drive_mode.hard_held("do not write to production"))
        self.assertFalse(pe.hard_held("我们不回退"))
        self.assertTrue(drive_mode.hard_held("不回退，但要回退 origin"))
        self.assertFalse(drive_mode.hard_held("不解封"))
        self.assertFalse(drive_mode.hard_held("不打开基线"))
        self.assertFalse(drive_mode.hard_held("不重新打开基线"))
        self.assertFalse(drive_mode.hard_held("不解除密封"))
        self.assertFalse(drive_mode.hard_held("不经验入库"))
        self.assertFalse(drive_mode.hard_held("绝不回退"))
        self.assertFalse(drive_mode.hard_held("无回退"))
        self.assertFalse(drive_mode.hard_held("勿回退"))
        self.assertFalse(drive_mode.hard_held("别解封"))
        self.assertFalse(drive_mode.hard_held("尚未回退"))
        self.assertFalse(drive_mode.hard_held("未解封"))
        self.assertFalse(drive_mode.hard_held("无需回退"))
        self.assertFalse(drive_mode.hard_held("不用打开基线"))
        self.assertFalse(drive_mode.hard_held("不必回退"))
        self.assertFalse(drive_mode.hard_held("不要解封"))
        self.assertFalse(drive_mode.hard_held("没有生产写"))
        self.assertFalse(drive_mode.hard_held("没回退"))
        self.assertFalse(drive_mode.hard_held("不涉及生产写"))
        self.assertFalse(drive_mode.hard_held("不会回退"))
        self.assertFalse(drive_mode.hard_held("未能解封"))
        self.assertFalse(drive_mode.hard_held("未曾回退"))
        self.assertFalse(drive_mode.hard_held("不需要回退"))
        self.assertFalse(drive_mode.hard_held("无法回退"))
        self.assertFalse(drive_mode.hard_held("禁止回退"))
        self.assertFalse(drive_mode.hard_held("避免生产写"))
        self.assertFalse(drive_mode.hard_held("no promote"))
        self.assertFalse(drive_mode.hard_held("do not reopen"))
        self.assertFalse(drive_mode.hard_held("do  not promote"))
        self.assertFalse(drive_mode.hard_held("without promote"))
        self.assertFalse(drive_mode.hard_held("never reopen"))
        self.assertFalse(drive_mode.hard_held("avoid promote"))
        self.assertFalse(drive_mode.hard_held("not promote"))
        self.assertFalse(drive_mode.hard_held("doesn't promote"))
        self.assertFalse(drive_mode.hard_held("won't promote"))
        self.assertFalse(drive_mode.hard_held("cannot promote"))
        self.assertFalse(drive_mode.hard_held("can't reopen"))
        self.assertFalse(drive_mode.hard_held("拒绝回退"))
        self.assertFalse(drive_mode.hard_held("跳过解封"))
        self.assertFalse(drive_mode.hard_held("永不回退"))
        self.assertFalse(drive_mode.hard_held("永不再回退"))
        self.assertFalse(drive_mode.hard_held("不再回退"))
        self.assertFalse(drive_mode.hard_held("不是回退"))
        self.assertFalse(drive_mode.hard_held("并不是生产写"))
        self.assertFalse(drive_mode.hard_held("这不是解封"))
        self.assertFalse(drive_mode.hard_held("切莫回退"))
        self.assertFalse(drive_mode.hard_held("莫要回退"))
        self.assertFalse(drive_mode.hard_held("未有生产写"))
        self.assertFalse(drive_mode.hard_held("无需再回退"))
        self.assertFalse(drive_mode.hard_held("无须回退"))
        self.assertFalse(drive_mode.hard_held("不该回退"))
        self.assertFalse(drive_mode.hard_held("不应生产写"))
        self.assertFalse(drive_mode.hard_held("不可回退"))
        self.assertFalse(drive_mode.hard_held("没法回退"))
        self.assertFalse(drive_mode.hard_held("没办法解封"))
        self.assertFalse(drive_mode.hard_held("用不着回退"))
        self.assertFalse(drive_mode.hard_held("暂缓回退"))
        self.assertFalse(drive_mode.hard_held("推迟解封"))
        self.assertFalse(drive_mode.hard_held("不必 promote"))
        self.assertFalse(drive_mode.hard_held("不要 reopen"))
        self.assertFalse(drive_mode.hard_held("无须 promote"))
        self.assertFalse(drive_mode.hard_held("请勿 promote"))
        self.assertFalse(drive_mode.hard_held("切勿 reopen"))
        self.assertTrue(drive_mode.hard_held("未来要回退"))  # 未回退 not contiguous
        self.assertTrue(drive_mode.hard_held("要不要回退"))  # A不A must stay
        self.assertTrue(drive_mode.hard_held("会不会回退"))
        self.assertTrue(drive_mode.hard_held("需不需要回退"))
        self.assertTrue(drive_mode.hard_held("是不是回退"))
        self.assertTrue(drive_mode.hard_held("要不要 promote"))
        self.assertTrue(drive_mode.hard_held("可不可以回退"))
        self.assertTrue(drive_mode.hard_held("解除密封"))
        self.assertTrue(drive_mode.hard_held("重新打开基线"))
        self.assertTrue(drive_mode.hard_held("需要回退"))
        self.assertTrue(drive_mode.hard_held("please promote"))
        self.assertTrue(drive_mode.hard_held("准备" + "git" + " " + "push"))
        self.assertTrue(drive_mode.hard_held("执行" + "git" + "  " + "push"))
        self.assertTrue(drive_mode.hard_held("生产 写"))
        self.assertTrue(drive_mode.hard_held("打开 基线"))
        self.assertTrue(drive_mode.hard_held("经验 入库"))
        self.assertTrue(drive_mode.hard_held("解除 密封"))
        self.assertFalse(drive_mode.hard_held("不 回退"))
        self.assertFalse(drive_mode.hard_held("无需 回退"))
        self.assertFalse(drive_mode.hard_held("不\u200b回退"))
        self.assertFalse(drive_mode.hard_held("不\u200c回退"))
        self.assertTrue(drive_mode.hard_held("请确认\u200b回退"))
        self.assertTrue(drive_mode.hard_held("生产\u200b写"))
        self.assertTrue(drive_mode.hard_held("ｐｒｏｍｏｔｅ"))
        self.assertTrue(drive_mode.hard_held("请确认ｒｅｏｐｅｎ"))
        self.assertFalse(drive_mode.hard_held_signal("［承重］生产写"))
        self.assertTrue(drive_mode.hard_held("打開基線"))
        self.assertTrue(drive_mode.hard_held("生產寫"))
        self.assertTrue(drive_mode.hard_held("經驗入庫"))
        self.assertTrue(drive_mode.hard_held("生产寫"))  # mixed script
        self.assertTrue(drive_mode.hard_held("打开基線"))
        self.assertTrue(drive_mode.hard_held("打開基线"))
        self.assertTrue(drive_mode.hard_held("生產写"))
        self.assertFalse(drive_mode.hard_held("不打開基線"))
        self.assertFalse(drive_mode.hard_held("非生產寫"))
        self.assertFalse(drive_mode.hard_held("無需生產寫"))
        self.assertFalse(drive_mode.hard_held("沒有回退"))
        self.assertFalse(drive_mode.hard_held("非生产寫"))
        self.assertFalse(drive_mode.hard_held("promotion plan"))

    def test_report_bom_tolerates_utf8_bom(self):
        raw = "\ufeffSTATUS: PASS\nRECOMMEND: 1\nASSUMED: [承重] x\n"
        self.assertEqual(drive_mode.report_status(raw), "PASS")
        self.assertEqual(drive_mode.report_recommend(raw), "1")
        self.assertEqual(
            drive_mode.resolve_signal_recommend(raw, ["[承重] x"]),
            ("1", "auto:recommend"),
        )

    def test_soft_hold_ascii_case_insensitive(self):
        self.assertTrue(pe.soft_held("blocked on logic"))
        self.assertTrue(pe.soft_held("Frontier unclear"))
        self.assertTrue(pe.soft_held("open signal remains"))
        self.assertTrue(pe.soft_held("baseline_conflict open"))
        self.assertTrue(pe.soft_held("baseline-conflict open"))
        self.assertTrue(pe.soft_held("baseline conflict open"))
        self.assertTrue(pe.soft_held("ARTIFACT remaining"))
        self.assertTrue(pe.held("blocked on logic"))
        self.assertFalse(pe.soft_held("signaling only"))  # word-boundary
        self.assertFalse(pe.soft_held("不矛盾"))
        self.assertFalse(pe.soft_held("无冲突"))
        self.assertFalse(pe.soft_held("非冲突"))
        self.assertFalse(pe.soft_held("无未决"))
        self.assertFalse(pe.soft_held("无需冲突"))
        self.assertFalse(pe.soft_held("不涉及冲突"))
        self.assertFalse(pe.soft_held("没有冲突"))
        self.assertFalse(pe.soft_held("没冲突"))
        self.assertFalse(pe.soft_held("不用冲突"))
        self.assertFalse(pe.soft_held("no BLOCKED"))
        self.assertFalse(pe.soft_held("not frontier"))
        self.assertFalse(pe.soft_held("no ARTIFACT"))
        self.assertFalse(pe.soft_held("拒绝冲突"))
        self.assertFalse(pe.soft_held("跳过冲突"))
        self.assertFalse(pe.soft_held("无须冲突"))
        self.assertFalse(pe.soft_held("不该冲突"))
        self.assertFalse(pe.soft_held("不可冲突"))
        self.assertFalse(pe.soft_held("没法冲突"))
        self.assertFalse(pe.soft_held("不 矛盾"))
        self.assertTrue(pe.soft_held("有 冲突"))
        self.assertTrue(pe.soft_held("有衝突"))
        self.assertTrue(pe.soft_held("未決"))
        self.assertFalse(pe.soft_held("不衝突"))
        self.assertTrue(pe.soft_held("不清楚"))  # marker itself starts with 不
        self.assertTrue(pe.soft_held("有矛盾"))
        self.assertTrue(pe.soft_held("要不要冲突"))  # A不A must stay
        self.assertTrue(pe.soft_held("是不是冲突"))
        self.assertTrue(pe.soft_held("still BLOCKED"))
        # ARTIFACT with recommend under auto → drive-auto; without → need recommend
        done = run_pe(
            "stop", "--drive", "auto", "--recommend", "1",
            "--stop", "ARTIFACT remaining",
        )
        self.assertIn("now=CORRECT", done.stdout)
        self.assertIn("id=drive-auto", done.stdout)
        need = run_pe(
            "stop", "--drive", "auto",
            "--stop", "ARTIFACT remaining",
        )
        self.assertIn("id=drive-need-recommend", need.stdout)
        # Auto + lowercase blocked + recommend should drive-auto, not ask.
        done = run_pe(
            "stop", "--drive", "auto", "--recommend", "1",
            "--stop", "blocked on fork",
        )
        self.assertIn("now=CORRECT", done.stdout)
        self.assertIn("id=drive-auto", done.stdout)

    def test_assisted_soft_hold_still_asks(self):
        done = run_pe(
            "stop", "--drive", "assisted", "--recommend", "1",
            "--stop", "有矛盾", "--signals", "frontier",
        )
        self.assertIn("now=ASK", done.stdout)
        self.assertIn("id=real-hold", done.stdout)

    def test_auto_soft_hold_without_recommend_hints(self):
        done = run_pe(
            "stop", "--drive", "auto",
            "--stop", "有矛盾", "--signals", "frontier",
        )
        self.assertIn("now=ASK", done.stdout)
        self.assertIn("id=drive-need-recommend", done.stdout)
        self.assertIn("先写出推荐", done.stdout)

    def test_nudge_toggles_drive_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            (repo / ".idev").mkdir()
            env = {**dict(**{k: v for k, v in __import__("os").environ.items()}), "IDEV_PRODUCT_REPO": str(repo)}
            on = subprocess.run(
                [sys.executable, str(HERE / "nudge.py"), "--quote", "开启自动模式"],
                capture_output=True, text=True, check=False, env=env, cwd=repo,
            )
            self.assertEqual(on.returncode, 0, on.stderr)
            self.assertIn("NUDGE drive-auto", on.stdout)
            self.assertIn("mode=auto", on.stdout)
            mode, source = drive_mode.resolve(repo, repo / "kernel-state")
            # Session file is under product .idev when product_repo is set.
            self.assertEqual(mode, "auto")
            self.assertEqual(source, "session")

    def test_signal_guide_mentions_auto(self):
        self.assertIn("--source auto", drive_mode.signal_guide("auto"))
        self.assertIn("--all-open", drive_mode.signal_guide("auto", step="plan", feature="demo"))
        self.assertIn("ask the person", drive_mode.signal_guide("assisted"))
        self.assertIn(
            "decide plan --all-open --source auto --recommend <档> --feature demo",
            drive_mode.decide_hint("plan", "demo"),
        )

    def test_extra_non_stops_correct(self):
        done = run_pe("stop", "--drive", "assisted", "--stop", "请确认一下")
        self.assertIn("now=CORRECT", done.stdout)
        self.assertIn("id=ask-known", done.stdout)

    def test_p0_cognitive_autos_with_recommend(self):
        row = pe.judge_stop(
            "", "需求边界不清楚", "", "未决", False,
            drive="auto", recommend="a",
        )
        self.assertEqual(row["now"], "CORRECT")
        self.assertEqual(row["id"], "drive-auto")

    def test_plain_stop_autos_with_recommend(self):
        row = pe.judge_stop(
            "", "方案选 A 还是 B", "", "", False,
            drive="auto", recommend="A",
        )
        self.assertEqual(row["now"], "CORRECT")
        self.assertEqual(row["id"], "drive-auto")
        assisted = pe.judge_stop(
            "", "方案选 A 还是 B", "", "", False,
            drive="assisted", recommend="A",
        )
        self.assertEqual(assisted["now"], "ASK")
        self.assertEqual(assisted["id"], "unclassified")

    def test_decision_gate_never_autos(self):
        row = pe.judge_stop(
            "", "提交推送", "", "", True,
            drive="auto", recommend="1",
        )
        self.assertEqual(row["now"], "ASK")
        self.assertEqual(row["id"], "decision-gate")
        hard = pe.judge_stop(
            "", "git push", "", "", True,
            drive="auto", recommend="1",
        )
        self.assertEqual(hard["now"], "ASK")

    def test_report_recommend_stamps(self):
        self.assertEqual(
            drive_mode.report_recommend("STATUS: PASS\nRECOMMEND: 1\n"),
            "1",
        )
        self.assertEqual(
            drive_mode.report_recommend("STATUS: PASS\nAI建议：mark\n"),
            "mark",
        )
        self.assertEqual(
            drive_mode.report_recommend("AI 建议: a，因为边界清楚"),
            "a",
        )
        self.assertEqual(
            drive_mode.report_recommend("RECOMMEND: 1;note\n"),
            "1",
        )
        self.assertEqual(
            drive_mode.report_recommend("AI建议：2；因为边界清楚\n"),
            "2",
        )
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 1)\n"), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 2）\n"), "2")
        self.assertEqual(drive_mode.report_recommend('RECOMMEND: "1"\n'), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 'mark'\n"), "mark")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: “a”\n"), "a")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: `1`\n"), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 1!\n"), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 1?\n"), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 1...\n"), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 1…\n"), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 1（首选）\n"), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND:（1）\n"), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 【1】\n"), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 1／a\n"), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 1、2\n"), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: A|B\n"), "A")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: A｜B\n"), "A")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND＝1\n"), "1")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND:＝2\n"), "2")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND:\u200b3\n"), "3")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 4\u200b\n"), "4")
        self.assertEqual(drive_mode.report_recommend("AI建議: 5\n"), "5")
        self.assertEqual(drive_mode.report_status("STATUS：PASS\n"), "")  # ASCII colon only
        self.assertEqual(drive_mode.report_status("STATUS: ＰＡＳＳ\n"), "PASS")
        self.assertEqual(drive_mode.report_status("STATUS: ＦＡＩＬ\n"), "FAIL")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 1.0\n"), "1.0")
        self.assertEqual(drive_mode.report_recommend("RECOMMEND: 2.1\n"), "2.1")
        self.assertEqual(
            drive_mode.resolve_signal_recommend(
                "STATUS: ＰＡＳＳ\n", ["[承重] x"],
            ),
            ("1", "auto:default-accept"),
        )
        self.assertEqual(
            drive_mode.report_recommend("ASSUMED: [承重] foo RECOMMEND=1"),
            "1",
        )
        self.assertEqual(drive_mode.report_recommend("STATUS: PASS\n"), "")
        # Bare「建议:」is loose-only; settle must not treat prose tips as stamps.
        self.assertEqual(drive_mode.report_recommend("建议: A\n"), "")
        self.assertEqual(drive_mode.report_recommend("建议: A\n", loose=True), "A")
        self.assertEqual(
            drive_mode.resolve_signal_recommend(
                "STATUS: PASS\n建议: 继续观察\n", ["[承重] x"],
            ),
            ("1", "auto:default-accept"),
        )

    def test_default_recommend_for_chengzhong_pass(self):
        raw = "STATUS: PASS\nASSUMED: [承重] 回放库开跑前是空的\n"
        self.assertEqual(
            drive_mode.default_signal_recommend(raw, ["[承重] 回放库开跑前是空的"]),
            "1",
        )
        self.assertEqual(
            drive_mode.resolve_signal_recommend(
                raw, ["[承重] 回放库开跑前是空的"],
            ),
            ("1", "auto:default-accept"),
        )
        # Domain words like 生产/回退 inside [承重] must not block default.
        self.assertEqual(
            drive_mode.default_signal_recommend(
                "STATUS: PASS\nASSUMED: [承重] 生产库是空的\n",
                ["[承重] 生产库是空的"],
            ),
            "1",
        )
        self.assertFalse(
            drive_mode.hard_held_signals(["[承重] 生产库是空的", "[承重] 回退前备份"]),
        )
        self.assertTrue(
            drive_mode.hard_held_signals(["请确认生产写入"]),
        )
        # Explicit STATUS: PASS is required; missing/empty status is not a default.
        self.assertEqual(
            drive_mode.default_signal_recommend(
                "ASSUMED: [承重] x\n", ["[承重] x"],
            ),
            "",
        )
        self.assertEqual(
            drive_mode.default_signal_recommend(
                "", ["[承重] x"],
            ),
            "",
        )
        self.assertEqual(
            drive_mode.default_signal_recommend(
                "STATUS: FAIL\n", ["[承重] x"],
            ),
            "",
        )
        self.assertEqual(
            drive_mode.default_signal_recommend(
                "STATUS: PASS\n", ["BLOCKED(logic)"],
            ),
            "",
        )
        self.assertEqual(
            drive_mode.default_signal_recommend(
                "STATUS: PASS\nRECOMMEND: 2\n", ["[承重] x"],
            ),
            "2",
        )
        self.assertEqual(
            drive_mode.resolve_signal_recommend(
                "STATUS: PASS\nRECOMMEND: 2\n", ["[承重] x"],
            ),
            ("2", "auto:recommend"),
        )
        # Stamped recommend still requires PASS — do not settle FAIL/BLOCKED.
        self.assertEqual(
            drive_mode.resolve_signal_recommend(
                "STATUS: FAIL\nRECOMMEND: 1\n", ["[承重] x"],
            ),
            ("", ""),
        )
        self.assertEqual(
            drive_mode.resolve_signal_recommend(
                "RECOMMEND: 1\n", ["[承重] x"],
            ),
            ("", ""),
        )
        self.assertEqual(
            drive_mode.resolve_signal_recommend(
                "RECOMMEND: 1\n", ["[承重] x"], status="PASS",
            ),
            ("1", "auto:recommend"),
        )
        self.assertEqual(
            drive_mode.resolve_signal_recommend(
                "STATUS: PASS(with notes)\nASSUMED: [承重] x\n",
                ["[承重] x"],
            ),
            ("1", "auto:default-accept"),
        )
        self.assertEqual(drive_mode.report_status("STATUS: PASS(with notes)\n"), "PASS")
        self.assertEqual(drive_mode.report_status("STATUS: FAIL\n"), "FAIL")
        self.assertEqual(drive_mode.report_status(""), "")
        self.assertEqual(
            drive_mode.resolve_signal_recommend(
                "ASSUMED: [承重] x\n", ["[承重] x"], status="PASS",
            ),
            ("1", "auto:default-accept"),
        )
        self.assertEqual(
            drive_mode.resolve_signal_recommend(
                "ASSUMED: [承重] x\n", ["[承重] x"], status="FAIL",
            ),
            ("", ""),
        )
        # Fullwidth colon is not STATUS contract (workflow line_field is ASCII).
        self.assertEqual(
            drive_mode.resolve_signal_recommend(
                "STATUS：PASS\nASSUMED: [承重] x\n", ["[承重] x"],
            ),
            ("", ""),
        )

    def test_process_eval_infers_recommend_from_stop(self):
        done = run_pe(
            "stop", "--drive", "auto",
            "--stop", "方案分叉\n建议: A",
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("infer-recommend=A", done.stdout)
        self.assertIn("id=drive-auto", done.stdout)
        self.assertIn("now=CORRECT", done.stdout)


class AuditCounts(unittest.TestCase):
    def test_drive_auto_counts_from_decisions(self):
        import audit_traces_lib as atl

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            traces = root / ".idev" / "traces"
            task = root / ".idev" / "task" / "demo"
            traces.mkdir(parents=True)
            task.mkdir(parents=True)
            (task / "decisions.yaml").write_text(
                "decisions:\n"
                "  - id: D1\n"
                "    source: auto\n"
                "    overturned: false\n"
                "  - id: D2\n"
                "    source: auto\n"
                "    overturned: true\n"
                "  - id: D3\n"
                "    source: human\n"
                "    overturned: false\n",
                encoding="utf-8",
            )
            auto, overturned = atl._drive_auto_counts(traces)
            self.assertEqual(auto, 2)
            self.assertEqual(overturned, 1)


class StaffingAutoSolo(unittest.TestCase):
    def test_unassigned_writes_solo_under_auto(self):
        import staffing  # noqa: WPS433

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            idev = root / ".idev"
            idev.mkdir()
            (idev / "people.yaml").write_text(
                "people:\n  - alice\n  - bob\n", encoding="utf-8"
            )
            drive_mode.set_mode(root, "auto", kernel_state=root / "kstate")
            old = __import__("os").environ.get("IDEV_PRODUCT_REPO")
            __import__("os").environ["IDEV_PRODUCT_REPO"] = str(root)
            try:
                staff, written = staffing.auto_solo_under_drive(
                    root, git_name="alice", chat="alice"
                )
                self.assertIsNotNone(written)
                self.assertEqual(staff.mode, "solo")
                self.assertEqual(staff.chat, "alice")
                self.assertTrue((idev / "staffing.yaml").is_file())
            finally:
                if old is None:
                    __import__("os").environ.pop("IDEV_PRODUCT_REPO", None)
                else:
                    __import__("os").environ["IDEV_PRODUCT_REPO"] = old


class VerifyFeedbackSettle(unittest.TestCase):
    def test_settle_writes_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            task = root / ".idev" / "task" / "demo"
            (task / "verify").mkdir(parents=True)
            (task / "deliver.yaml").write_text("stage: test\n", encoding="utf-8")
            (root / ".idev" / "marker.yaml").write_text("marker: idev\nid: demo\n", encoding="utf-8")
            drive_mode.set_mode(root, "auto", kernel_state=root / "kstate")
            old = __import__("os").environ.get("IDEV_PRODUCT_REPO")
            __import__("os").environ["IDEV_PRODUCT_REPO"] = str(root)
            try:
                path = drive_mode.settle_verify_feedback(root, "demo")
                self.assertIsNotNone(path)
                text = path.read_text(encoding="utf-8")
                self.assertIn("status: none", text)
                self.assertIn("auto:drive-mode", text)
                # second call is a no-op
                self.assertIsNone(drive_mode.settle_verify_feedback(root, "demo"))
            finally:
                if old is None:
                    __import__("os").environ.pop("IDEV_PRODUCT_REPO", None)
                else:
                    __import__("os").environ["IDEV_PRODUCT_REPO"] = old

    def test_settle_skips_missing_ticket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".idev").mkdir()
            (root / ".idev" / "marker.yaml").write_text(
                "marker: idev\nid: demo\n", encoding="utf-8",
            )
            drive_mode.set_mode(root, "auto", kernel_state=root / "kstate")
            old = __import__("os").environ.get("IDEV_PRODUCT_REPO")
            __import__("os").environ["IDEV_PRODUCT_REPO"] = str(root)
            try:
                self.assertIsNone(drive_mode.settle_verify_feedback(root, "demo"))
                self.assertIsNone(drive_mode.settle_verify_feedback(root, "-"))
                self.assertIsNone(drive_mode.settle_scope_debt(root, "-"))
                self.assertFalse(
                    (root / ".idev" / "task" / "demo" / "verify" / "feedback.yaml").exists()
                )
            finally:
                if old is None:
                    __import__("os").environ.pop("IDEV_PRODUCT_REPO", None)
                else:
                    __import__("os").environ["IDEV_PRODUCT_REPO"] = old


class ScopeDebtSettle(unittest.TestCase):
    def test_pending_adopts_recommend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            task = root / ".idev" / "task" / "demo"
            task.mkdir(parents=True)
            arch = task / "arch.yaml"
            arch.write_text(
                "scope_debt:\n  decision: pending\n  recommend: mark\n  child: \"\"\n",
                encoding="utf-8",
            )
            (root / ".idev" / "marker.yaml").write_text("marker: idev\nid: demo\n", encoding="utf-8")
            drive_mode.set_mode(root, "auto", kernel_state=root / "kstate")
            old = __import__("os").environ.get("IDEV_PRODUCT_REPO")
            __import__("os").environ["IDEV_PRODUCT_REPO"] = str(root)
            try:
                path = drive_mode.settle_scope_debt(root, "demo")
                self.assertIsNotNone(path)
                text = arch.read_text(encoding="utf-8")
                self.assertIn("decision: mark", text)
                self.assertIn("auto:drive-mode", text)
                self.assertIsNone(drive_mode.settle_scope_debt(root, "demo"))
            finally:
                if old is None:
                    __import__("os").environ.pop("IDEV_PRODUCT_REPO", None)
                else:
                    __import__("os").environ["IDEV_PRODUCT_REPO"] = old

    def test_assisted_leaves_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            task = root / ".idev" / "task" / "demo"
            task.mkdir(parents=True)
            (task / "arch.yaml").write_text(
                "scope_debt:\n  decision: pending\n  recommend: fix-first\n",
                encoding="utf-8",
            )
            drive_mode.set_mode(root, "assisted", kernel_state=root / "kstate")
            old = __import__("os").environ.get("IDEV_PRODUCT_REPO")
            __import__("os").environ["IDEV_PRODUCT_REPO"] = str(root)
            try:
                self.assertIsNone(drive_mode.settle_scope_debt(root, "demo"))
            finally:
                if old is None:
                    __import__("os").environ.pop("IDEV_PRODUCT_REPO", None)
                else:
                    __import__("os").environ["IDEV_PRODUCT_REPO"] = old

    def test_already_decided_does_not_rewrite_arch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            task = root / ".idev" / "task" / "demo"
            task.mkdir(parents=True)
            arch = task / "arch.yaml"
            original = (
                "# keep\nsummary: x\nscope_debt:\n"
                "  decision: mark\n  recommend: mark\n"
            )
            arch.write_text(original, encoding="utf-8")
            (root / ".idev" / "marker.yaml").write_text(
                "marker: idev\nid: demo\n", encoding="utf-8",
            )
            drive_mode.set_mode(root, "auto", kernel_state=root / "kstate")
            old = __import__("os").environ.get("IDEV_PRODUCT_REPO")
            __import__("os").environ["IDEV_PRODUCT_REPO"] = str(root)
            try:
                self.assertIsNone(drive_mode.settle_scope_debt(root, "demo"))
                self.assertEqual(arch.read_text(encoding="utf-8"), original)
            finally:
                if old is None:
                    __import__("os").environ.pop("IDEV_PRODUCT_REPO", None)
                else:
                    __import__("os").environ["IDEV_PRODUCT_REPO"] = old


class SlotAutofill(unittest.TestCase):
    def test_feature_slot_fills_from_run(self):
        import workflow  # noqa: WPS433

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".idev").mkdir()
            drive_mode.set_mode(root, "auto", kernel_state=root / "kstate")
            old = __import__("os").environ.get("IDEV_PRODUCT_REPO")
            __import__("os").environ["IDEV_PRODUCT_REPO"] = str(root)
            try:
                run = {
                    "feature": "demo-feat",
                    "params": {},
                    "status": "running",
                    "steps": [{
                        "id": "look", "kind": "route.s4", "slots": ["feature"],
                        "status": "pending",
                    }],
                }
                found = workflow.slots_to_autofill(run)
                self.assertEqual(found, {"feature": "demo-feat"})
                filled = workflow.try_autofill_slots(run)
                self.assertEqual(filled, ["feature"])
                self.assertEqual(run["params"]["feature"], "demo-feat")
                scoped = {
                    "feature": "demo-feat",
                    "params": {},
                    "status": "running",
                    "steps": [{
                        "id": "look", "kind": "route.s4", "slots": ["scope"],
                        "with": {"scope": "api"},
                        "status": "pending",
                    }],
                }
                self.assertEqual(workflow.slots_to_autofill(scoped), {"scope": "api"})
            finally:
                if old is None:
                    __import__("os").environ.pop("IDEV_PRODUCT_REPO", None)
                else:
                    __import__("os").environ["IDEV_PRODUCT_REPO"] = old


class AgentFeedbackAuto(unittest.TestCase):
    def test_auto_writes_none_and_clears_stop(self):
        import workflow  # noqa: WPS433
        import testenv  # noqa: WPS433

        testenv.pin()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            wf = root / "workflow"
            wf.mkdir(parents=True)
            run_path = wf / "run.yaml"
            run_path.write_text(
                "schema_version: 1\nworkflow_id: demo\nfeature: demo\nstatus: running\n"
                "steps:\n"
                "  - id: code\n    kind: deliver.code_pass\n    status: PASS\n"
                "      delegated: {agent: idev-coder}\n",
                encoding="utf-8",
            )
            drive_mode.set_mode(root, "auto", by="tester", kernel_state=root / "kstate")
            # Point product_repo at this tree via env for drive_mode.current().
            env_repo = root
            old = __import__("os").environ.get("IDEV_PRODUCT_REPO")
            __import__("os").environ["IDEV_PRODUCT_REPO"] = str(env_repo)
            try:
                # Ensure .idev exists so product_repo accepts it when used elsewhere.
                (root / ".idev").mkdir(exist_ok=True)
                block = workflow.agent_feedback_block(
                    {
                        "feature": "demo",
                        "steps": [{
                            "id": "code", "kind": "deliver.code_pass", "status": "PASS",
                            "delegated": {"agent": "idev-coder"},
                        }],
                    },
                    run_path,
                )
                self.assertIsNone(block)
                fb = wf / "agent-feedback.yaml"
                self.assertTrue(fb.is_file())
                text = fb.read_text(encoding="utf-8")
                self.assertIn("status: none", text)
                self.assertIn("auto:drive-mode", text)
            finally:
                if old is None:
                    __import__("os").environ.pop("IDEV_PRODUCT_REPO", None)
                else:
                    __import__("os").environ["IDEV_PRODUCT_REPO"] = old

    def test_assisted_still_stops_without_feedback(self):
        import workflow  # noqa: WPS433

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            wf = root / "workflow"
            wf.mkdir(parents=True)
            run_path = wf / "run.yaml"
            run_path.write_text("status: running\n", encoding="utf-8")
            drive_mode.set_mode(root, "assisted", kernel_state=root / "kstate")
            old = __import__("os").environ.get("IDEV_PRODUCT_REPO")
            __import__("os").environ["IDEV_PRODUCT_REPO"] = str(root)
            try:
                (root / ".idev").mkdir(exist_ok=True)
                block = workflow.agent_feedback_block(
                    {
                        "feature": "demo",
                        "steps": [{
                            "id": "code", "status": "PASS",
                            "delegated": {"agent": "idev-coder"},
                        }],
                    },
                    run_path,
                )
                self.assertIsNotNone(block)
                self.assertIn("STOP agent-feedback", block or "")
            finally:
                if old is None:
                    __import__("os").environ.pop("IDEV_PRODUCT_REPO", None)
                else:
                    __import__("os").environ["IDEV_PRODUCT_REPO"] = old


class DecideSourceAuto(unittest.TestCase):
    """workflow.py decide --source auto writes source and refuses bad pairs."""

    def setUp(self) -> None:
        import testenv  # noqa: WPS433
        import safeyaml  # noqa: WPS433
        from test_auto_gate import assemble, cli, FEATURE  # noqa: WPS433

        testenv.pin()
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()
        self.ticket = assemble(self.repo)
        self.cli = cli
        self.feature = FEATURE
        self.safeyaml = safeyaml
        for args in (
            ("start", "dev-logic", "--feature", FEATURE),
            ("record", "plan", "PASS", "--evidence", "verify/plan.yaml", "--feature", FEATURE),
        ):
            done = cli(self.repo, "workflow.py", *args)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        records = Path(cli(self.repo, "delegation.py", "dir", "--feature", FEATURE).stdout.strip())
        records.mkdir(parents=True, exist_ok=True)
        (records / "plan-1.yaml").write_text(safeyaml.dump({
            "step": "plan", "attempt": 1, "kind": "verify.plan", "agent": "idev-verifier",
            "signals": ["[承重] 回放库开跑前是空的"],
            "report": {"raw": "STATUS: PASS\nASSUMED: [承重] 回放库开跑前是空的\n"},
        }), encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_auto_decide_records_source(self) -> None:
        done = self.cli(
            self.repo, "workflow.py", "decide", "plan",
            "--signal", "[承重] 回放库开跑前是空的",
            "--question", "回放库开跑前是空的吗",
            "--recommend", "1",
            "--source", "auto",
            "--feature", self.feature,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("DRIVE source=auto", done.stdout)
        import yaml  # noqa: WPS433

        data = yaml.safe_load((self.ticket / "decisions.yaml").read_text(encoding="utf-8"))
        entry = data["decisions"][0]
        self.assertEqual(entry["source"], "auto")
        self.assertEqual(entry["answer"], "1")
        self.assertEqual(entry["quote"], "auto:recommend")
        self.assertIs(entry["overturned"], False)

    def test_auto_decide_refuses_answer_mismatch(self) -> None:
        done = self.cli(
            self.repo, "workflow.py", "decide", "plan",
            "--signal", "[承重] 回放库开跑前是空的",
            "--question", "回放库开跑前是空的吗",
            "--recommend", "1",
            "--answer", "2",
            "--quote", "auto:recommend",
            "--source", "auto",
            "--feature", self.feature,
        )
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("answer must equal", done.stdout + done.stderr)

    def test_all_open_decides_every_signal(self) -> None:
        records = Path(self.cli(self.repo, "delegation.py", "dir", "--feature", self.feature).stdout.strip())
        (records / "plan-1.yaml").write_text(self.safeyaml.dump({
            "step": "plan", "attempt": 1, "kind": "verify.plan", "agent": "idev-verifier",
            "signals": ["[承重] a", "[承重] b"],
            "report": {"raw": "STATUS: PASS\nASSUMED: [承重] a\nASSUMED: [承重] b\n"},
        }), encoding="utf-8")
        done = self.cli(
            self.repo, "workflow.py", "decide", "plan",
            "--all-open", "--source", "auto", "--recommend", "1",
            "--feature", self.feature,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("DRIVE_AUTO decided=2", done.stdout)
        self.assertIn("SIGNALS none left", done.stdout)

    def test_auto_decide_helper_from_stamped_recommend(self) -> None:
        import workflow  # noqa: WPS433

        run_path = self.ticket / "workflow" / "run.yaml"
        asked = workflow.unanswered(run_path, "plan")
        self.assertEqual(asked, ["[承重] 回放库开跑前是空的"])
        n = workflow._auto_decide_open_signals(
            run_path, "plan", asked, "1", quote="auto:default-accept",
        )
        self.assertEqual(n, 1)
        self.assertEqual(workflow.unanswered(run_path, "plan"), [])

    def test_auto_decide_allows_chengzhong_with_hard_hold_words(self) -> None:
        import workflow  # noqa: WPS433

        self.assertFalse(workflow.hard_held_signals(["[承重] 生产库是空的"]))
        self.assertTrue(workflow.hard_held_signals(["请确认生产写入"]))

    def test_auto_decide_skips_hard_hold_in_mixed_batch(self) -> None:
        import workflow  # noqa: WPS433

        run_path = self.ticket / "workflow" / "run.yaml"
        records = Path(self.cli(self.repo, "delegation.py", "dir", "--feature", self.feature).stdout.strip())
        (records / "plan-1.yaml").write_text(self.safeyaml.dump({
            "step": "plan", "attempt": 1, "kind": "verify.plan", "agent": "idev-verifier",
            "signals": ["[承重] 回放库开跑前是空的", "请确认生产写入"],
            "report": {
                "raw": (
                    "STATUS: PASS\nASSUMED: [承重] 回放库开跑前是空的\n"
                    "RECOMMEND: 1\n"
                ),
            },
        }), encoding="utf-8")
        n = workflow._auto_decide_open_signals(
            run_path,
            "plan",
            ["[承重] 回放库开跑前是空的", "请确认生产写入"],
            "1",
            quote="auto:recommend",
        )
        self.assertEqual(n, 1)
        left = workflow.unanswered(run_path, "plan")
        self.assertEqual(left, ["请确认生产写入"])

    def test_next_settles_stamped_recommend(self) -> None:
        import drive_mode  # noqa: WPS433

        records = Path(self.cli(self.repo, "delegation.py", "dir", "--feature", self.feature).stdout.strip())
        (records / "plan-1.yaml").write_text(self.safeyaml.dump({
            "step": "plan", "attempt": 1, "kind": "verify.plan", "agent": "idev-verifier",
            "signals": ["[承重] 回放库开跑前是空的"],
            "report": {
                "raw": (
                    "STATUS: PASS\nASSUMED: [承重] 回放库开跑前是空的\n"
                    "RECOMMEND: 1\n"
                ),
            },
        }), encoding="utf-8")
        drive_mode.set_mode(self.repo, "auto", by="tester", kernel_state=self.repo / "kstate")
        old = __import__("os").environ.get("IDEV_PRODUCT_REPO")
        __import__("os").environ["IDEV_PRODUCT_REPO"] = str(self.repo)
        try:
            done = self.cli(self.repo, "workflow.py", "next", "--feature", self.feature)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("DRIVE_AUTO decided=1", done.stdout)
        finally:
            if old is None:
                __import__("os").environ.pop("IDEV_PRODUCT_REPO", None)
            else:
                __import__("os").environ["IDEV_PRODUCT_REPO"] = old

    def test_next_settles_chengzhong_default_without_stamp(self) -> None:
        import drive_mode  # noqa: WPS433

        records = Path(self.cli(self.repo, "delegation.py", "dir", "--feature", self.feature).stdout.strip())
        (records / "plan-1.yaml").write_text(self.safeyaml.dump({
            "step": "plan", "attempt": 1, "kind": "verify.plan", "agent": "idev-verifier",
            "signals": ["[承重] 生产库是空的"],
            "report": {
                "raw": "STATUS: PASS\nASSUMED: [承重] 生产库是空的\n",
            },
        }), encoding="utf-8")
        drive_mode.set_mode(self.repo, "auto", by="tester", kernel_state=self.repo / "kstate")
        old = __import__("os").environ.get("IDEV_PRODUCT_REPO")
        __import__("os").environ["IDEV_PRODUCT_REPO"] = str(self.repo)
        try:
            done = self.cli(self.repo, "workflow.py", "next", "--feature", self.feature)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("DRIVE_AUTO decided=1", done.stdout)
        finally:
            if old is None:
                __import__("os").environ.pop("IDEV_PRODUCT_REPO", None)
            else:
                __import__("os").environ["IDEV_PRODUCT_REPO"] = old


class StaffingNoteAuto(unittest.TestCase):
    def test_auto_note_does_not_ask_once(self):
        import staffing  # noqa: WPS433

        staff = staffing.Staffing(
            "unassigned", "product-people", ["alice", "bob"], {}, "", "assign",
        )
        note = staffing.note_line(staff, drive="auto")
        self.assertIn("drive=auto", note)
        self.assertNotIn("只问一次", note)
        assisted = staffing.note_line(staff, drive="assisted")
        self.assertIn("只问一次", assisted)


class AskSlotHint(unittest.TestCase):
    def test_auto_ask_slot_prints_param_hint(self):
        import workflow  # noqa: WPS433

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".idev").mkdir()
            drive_mode.set_mode(root, "auto", kernel_state=root / "kstate")
            old = __import__("os").environ.get("IDEV_PRODUCT_REPO")
            __import__("os").environ["IDEV_PRODUCT_REPO"] = str(root)
            try:
                lines = workflow._ask_lines(
                    {"id": "look", "kind": "route.s4"}, ["scope"],
                )
                self.assertIn("ASK slot scope", lines)
                self.assertTrue(any(line.startswith("DRIVE_HINT") for line in lines))
                self.assertIn("param", "\n".join(lines))
            finally:
                if old is None:
                    __import__("os").environ.pop("IDEV_PRODUCT_REPO", None)
                else:
                    __import__("os").environ["IDEV_PRODUCT_REPO"] = old


if __name__ == "__main__":
    unittest.main()
