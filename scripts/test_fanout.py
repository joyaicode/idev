#!/usr/bin/env python3
"""fanout assess/merge: split only when the writes do not overlap."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import fanout
import safeyaml
from delegation import record_dir, record_name


def _ticket(root: Path) -> Path:
    task = root / ".idev" / "task" / "feat"
    task.mkdir(parents=True)
    (task / "deliver.yaml").write_text("stage: code\n", encoding="utf-8")
    return task


def _plan(task: Path, mode: str, cases: list[dict]) -> None:
    path = task / "verify" / "plan.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safeyaml.dump({
        "schema_version": 1,
        "feature": "feat",
        "mode": mode,
        "accepted": True,
        "cases": cases,
    }), encoding="utf-8")


def _case(cid: str, kind: str, **runner) -> dict:
    body = {"kind": kind}
    body.update(runner)
    return {
        "id": cid,
        "dimension": "correctness",
        "accepted": True,
        "runner": body,
        "status": "UNPROVEN",
        "evidence": "not run",
    }


class Assess(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.task = _ticket(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_plan_splits_uncovered_intents(self) -> None:
        (self.task / "arch.yaml").write_text(safeyaml.dump({
            "case_intents": [
                {"id": "keep", "slice_id": "s1", "baseline_item_id": "B1", "dimension": "correctness"},
                {"id": "drop", "slice_id": "s2", "baseline_item_id": "B2", "dimension": "compat"},
            ],
        }), encoding="utf-8")
        result = fanout.assess("feat", "plan", self.root)
        self.assertEqual(result["decision"], "FANOUT")
        self.assertEqual([s["id"] for s in result["shards"]], ["keep", "drop"])
        writes = [w for s in result["shards"] for w in s["writes"]]
        self.assertEqual(len(writes), len(set(writes)))
        self.assertTrue(all(w.startswith("verify/shards/plan-") for w in writes))

    def test_signed_findings_split_a_fresh_plan(self) -> None:
        (self.task / "review.md").write_text(
            "### I1 已签收\n\n### I2 待签收\n\n### I3 已签收\n",
            encoding="utf-8",
        )
        result = fanout.assess("feat", "plan", self.root)
        self.assertEqual(result["decision"], "FANOUT")
        self.assertEqual([s["id"] for s in result["shards"]], ["I1", "I3"])
        self.assertIn("verify/checks/I1/", result["shards"][0]["writes"])
        self.assertIn("LEASE", fanout.render(result, "feat"))

    def test_one_signed_finding_stays_serial(self) -> None:
        (self.task / "review.md").write_text("### I1 已签收\n", encoding="utf-8")
        result = fanout.assess("feat", "plan", self.root)
        self.assertEqual(result["decision"], "SERIAL")
        self.assertIn("case_intents", result["reason"])

    def test_report_splits_changed_modules(self) -> None:
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        for name in ("mod-a", "mod-b"):
            directory = self.root / name
            directory.mkdir()
            (directory / "A.java").write_text("class A {}\n", encoding="utf-8")
        result = fanout.assess("feat", "report", self.root)
        self.assertEqual(result["decision"], "FANOUT")
        self.assertEqual(sorted(s["id"] for s in result["shards"]), ["mod-a", "mod-b"])
        self.assertTrue(any("coding-scan.sh" in line for line in result["prep"]))

    def test_report_keeps_finished_shards_and_asks_to_merge(self) -> None:
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        for name in ("mod-a", "mod-b", "mod-c"):
            directory = self.root / name
            directory.mkdir()
            (directory / "A.java").write_text("class A {}\n", encoding="utf-8")
        odd = self.root / "not a module"
        odd.mkdir()
        (odd / "A.java").write_text("class A {}\n", encoding="utf-8")
        first = fanout.assess("feat", "report", self.root)
        self.assertEqual([s["id"] for s in first["shards"]], ["mod-a", "mod-b", "mod-c"])
        for shard in first["shards"]:
            if shard["id"] == "mod-c":
                continue
            path = self.task / shard["writes"][0]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("### FINDING\n\n位置: x\n", encoding="utf-8")
        mid = fanout.assess("feat", "report", self.root)
        self.assertEqual([s["id"] for s in mid["shards"]], ["mod-a", "mod-b", "mod-c"])
        rendered = fanout.render(mid, "feat")
        self.assertIn("SHARD mod-c ", rendered)
        self.assertNotIn("SHARD mod-a ", rendered)
        missing = self.task / "review" / "shards" / "mod-c.md"
        missing.write_text("### UNPROVEN\n\nnot opened\n", encoding="utf-8")
        done = fanout.assess("feat", "report", self.root)
        self.assertEqual(done.get("resume"), "merge")
        text = fanout.render(done, "feat")
        self.assertTrue(text.startswith("MERGE report"))
        self.assertNotIn("\nSHARD ", "\n" + text)
        fanout.write_manifest("feat", done, self.root)
        self.assertEqual(fanout.merge("feat", "report", self.root), 0)
        review = (self.task / "review.md").read_text(encoding="utf-8")
        self.assertIn("### I1 待签收", review)
        self.assertIn("位置: x", review)

    def test_report_does_not_merge_over_a_signed_ledger(self) -> None:
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        for name in ("mod-a", "mod-b"):
            directory = self.root / name
            directory.mkdir()
            (directory / "A.java").write_text("class A {}\n", encoding="utf-8")
        (self.task / "review.md").write_text("### I1 已签收\n", encoding="utf-8")
        fresh = fanout.assess("feat", "report", self.root)
        self.assertEqual(fresh["decision"], "FANOUT")
        for shard in fresh["shards"]:
            path = self.task / shard["writes"][0]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("### FINDING\n\n位置: x\n", encoding="utf-8")
        signed = fanout.assess("feat", "report", self.root)
        self.assertEqual(signed["decision"], "SERIAL")
        self.assertIn("already signed", signed["reason"])

    def test_plan_resume_merges_finished_finding_shards(self) -> None:
        (self.task / "review.md").write_text("### I1 已签收\n\n### I2 已签收\n", encoding="utf-8")
        first = fanout.assess("feat", "plan", self.root)
        self.assertEqual([s["id"] for s in first["shards"]], ["I1", "I2"])
        body = {
            "I1": {"cases": [{"id": "case-i1", "finding": "I1", "dimension": "correctness"}]},
            "I2": {"cases": [{"id": "case-i2", "finding": "I2", "dimension": "correctness"}]},
        }
        for shard in first["shards"]:
            path = self.task / shard["writes"][0]
            path.parent.mkdir(parents=True, exist_ok=True)
            if shard["id"] == "I1":
                path.write_text(safeyaml.dump(body["I1"]), encoding="utf-8")
        mid = fanout.assess("feat", "plan", self.root)
        self.assertEqual([s["id"] for s in mid["shards"]], ["I1", "I2"])
        rendered = fanout.render(mid, "feat")
        self.assertIn("SHARD I2 ", rendered)
        self.assertNotIn("SHARD I1 ", rendered)
        second = next(s for s in mid["shards"] if s["id"] == "I2")
        (self.task / second["writes"][0]).write_text(safeyaml.dump(body["I2"]), encoding="utf-8")
        done = fanout.assess("feat", "plan", self.root)
        self.assertEqual(done.get("resume"), "merge")
        self.assertTrue(fanout.render(done, "feat").startswith("MERGE plan"))
        fanout.write_manifest("feat", done, self.root)
        self.assertEqual(fanout.merge("feat", "plan", self.root), 0)
        plan = safeyaml.mapping(self.task / "verify" / "plan.yaml")
        self.assertEqual([c["id"] for c in plan["cases"]], ["case-i1", "case-i2"])
        again = fanout.assess("feat", "plan", self.root)
        self.assertEqual(again["decision"], "SERIAL")
        self.assertIn("record the step", again["reason"])

    def test_one_changed_module_stays_serial(self) -> None:
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        directory = self.root / "mod-a"
        directory.mkdir()
        (directory / "A.java").write_text("class A {}\n", encoding="utf-8")
        result = fanout.assess("feat", "report", self.root)
        self.assertEqual(result["decision"], "SERIAL")

    def test_lease_glob_keeps_a_directory_inside_the_ticket(self) -> None:
        globs = fanout.lease_globs("docs/task/feat", ["verify/shards/plan-I1.yaml", "verify/checks/I1/"])
        self.assertEqual(globs, [
            "docs/task/feat/verify/shards/plan-I1.yaml",
            "docs/task/feat/verify/checks/I1/**",
        ])

    def test_record_dir_follows_the_run(self) -> None:
        workflow = self.task / "workflow"
        workflow.mkdir()
        (workflow / "run.yaml").write_text("run_id: RUN1\n", encoding="utf-8")
        self.assertEqual(
            record_dir("feat", self.root).resolve(),
            (workflow / "delegations" / "RUN1").resolve(),
        )

    def test_plan_stays_serial_when_one_intent_remains(self) -> None:
        (self.task / "arch.yaml").write_text(safeyaml.dump({
            "case_intents": [
                {"id": "keep", "slice_id": "s1", "baseline_item_id": "B1", "dimension": "correctness"},
                {"id": "drop", "slice_id": "s2", "baseline_item_id": "B2", "dimension": "compat"},
            ],
        }), encoding="utf-8")
        _plan(self.task, "selftest", [{
            "id": "keep", "slice_id": "s1", "baseline_item_id": "B1", "dimension": "correctness",
        }])
        result = fanout.assess("feat", "plan", self.root)
        self.assertEqual(result["decision"], "SERIAL")

    def test_same_maven_module_stays_one_shard(self) -> None:
        _plan(self.task, "selftest", [
            _case("a", "maven-surefire", module="svc", selector="ATest"),
            _case("b", "maven-surefire", module="svc", selector="BTest"),
        ])
        result = fanout.assess("feat", "selftest", self.root)
        self.assertEqual(result["decision"], "SERIAL")
        self.assertIn("runner.parallel", result["hint"])

    def test_parallel_flag_splits_a_module_and_names_prep(self) -> None:
        _plan(self.task, "selftest", [
            _case("a", "maven-surefire", module="svc", selector="ATest", parallel=True),
            _case("b", "maven-surefire", module="svc", selector="BTest", parallel=True),
        ])
        result = fanout.assess("feat", "selftest", self.root)
        self.assertEqual(result["decision"], "FANOUT")
        self.assertEqual(result["prep"], ["svc mvn -pl svc -am -Pex test-compile"])
        self.assertIn("verify/evidence/a/", result["shards"][0]["writes"])

    def test_different_modules_fan_out(self) -> None:
        _plan(self.task, "test", [
            _case("a", "maven-surefire", module="svc-a", selector="ATest"),
            _case("b", "maven-surefire", module="svc-b", selector="BTest"),
        ])
        result = fanout.assess("feat", "run", self.root)
        self.assertEqual(result["decision"], "FANOUT")
        self.assertEqual(result["prep"], [])

    def test_shell_cases_fan_out_and_cap_queues_the_rest(self) -> None:
        _plan(self.task, "test", [
            _case("a", "shell", command="echo a"),
            _case("b", "shell", command="echo b"),
            _case("c", "shell", command="echo c"),
        ])
        result = fanout.assess("feat", "run", self.root, cap=2)
        self.assertEqual([s["id"] for s in result["shards"]], ["a", "b"])
        self.assertEqual([s["id"] for s in result["queued"]], ["c"])

    def test_cap_stops_at_eight(self) -> None:
        _plan(self.task, "test", [_case(f"c{i}", "shell", command=f"echo {i}") for i in range(9)])
        result = fanout.assess("feat", "run", self.root, cap=100)
        self.assertEqual(len(result["shards"]), 8)
        self.assertEqual(len(result["queued"]), 1)

    def test_same_http_env_stays_together(self) -> None:
        _plan(self.task, "test", [
            _case("a", "frontend-http", env="local"),
            _case("b", "frontend-http", env="local"),
        ])
        result = fanout.assess("feat", "run", self.root)
        self.assertEqual(result["decision"], "SERIAL")

    def test_selftest_refuses_another_mode(self) -> None:
        _plan(self.task, "test", [
            _case("a", "shell", command="echo a"),
            _case("b", "shell", command="echo b"),
        ])
        result = fanout.assess("feat", "selftest", self.root)
        self.assertEqual(result["decision"], "SERIAL")
        self.assertIn("not selftest", result["reason"])

    def test_rootcause_splits_open_hypotheses(self) -> None:
        (self.task / "hypotheses.yaml").write_text(safeyaml.dump({
            "items": [
                {"id": "H1", "status": "open", "claim": "a"},
                {"id": "H2", "status": "open", "claim": "b"},
                {"id": "H3", "status": "disproven", "claim": "c"},
            ],
        }), encoding="utf-8")
        result = fanout.assess("feat", "rootcause", self.root)
        self.assertEqual([s["id"] for s in result["shards"]], ["H1", "H2"])
        self.assertTrue(all(s["agent"] == "idev-ops" for s in result["shards"]))

    def test_one_hypothesis_stays_serial(self) -> None:
        (self.task / "hypotheses.yaml").write_text(safeyaml.dump({
            "items": [{"id": "H1", "status": "open"}],
        }), encoding="utf-8")
        result = fanout.assess("feat", "rootcause", self.root)
        self.assertEqual(result["decision"], "SERIAL")


class Merge(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.task = _ticket(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _manifest(self, activity: str, shards: list[dict], guards: dict) -> None:
        path = fanout.manifest_path(self.task, activity)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(safeyaml.dump({
            "decision": "FANOUT",
            "activity": activity,
            "shards": shards,
            "guards": guards,
        }), encoding="utf-8")

    def test_merge_plan_appends_and_refuses_a_touched_plan(self) -> None:
        (self.task / "arch.yaml").write_text("case_intents: []\n", encoding="utf-8")
        fanout.write_manifest("feat", fanout.assess("feat", "plan", self.root), self.root)
        (self.task / "arch.yaml").write_text(safeyaml.dump({
            "case_intents": [
                {"id": "keep", "slice_id": "s1", "baseline_item_id": "B1", "dimension": "correctness"},
                {"id": "drop", "slice_id": "s2", "baseline_item_id": "B2", "dimension": "compat"},
            ],
        }), encoding="utf-8")
        result = fanout.assess("feat", "plan", self.root)
        fanout.write_manifest("feat", result, self.root)
        for shard in result["shards"]:
            intent = shard["intent"]
            body = {"cases": [{**intent, "accepted": True, "runner": {"kind": "shell", "command": "true"}}]}
            path = self.task / shard["writes"][0]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(safeyaml.dump(body), encoding="utf-8")
        self.assertEqual(fanout.merge("feat", "plan", self.root), 0)
        plan = safeyaml.mapping(self.task / "verify" / "plan.yaml")
        self.assertEqual([c["id"] for c in plan["cases"]], ["keep", "drop"])
        self.assertTrue(all(c["accepted"] is False for c in plan["cases"]))
        (self.task / "verify" / "plan.yaml").write_text("accepted: true\n", encoding="utf-8")
        self.assertEqual(fanout.merge("feat", "plan", self.root), 2)

    def test_merge_findings_appends_every_case_and_includes_paths(self) -> None:
        (self.task / "review.md").write_text("### I1 已签收\n\n### I2 已签收\n", encoding="utf-8")
        result = fanout.assess("feat", "plan", self.root)
        fanout.write_manifest("feat", result, self.root)
        bodies = {
            "I1": {
                "paths": ["mod/A.java"],
                "cases": [
                    {"id": "selftest-i1-query", "finding": "I1", "dimension": "correctness", "accepted": True},
                    {"id": "selftest-i1-branch", "finding": "I1", "dimension": "compat", "accepted": True},
                ],
            },
            "I2": {
                "paths": ["mod/B.java"],
                "cases": [
                    {"id": "selftest-i2-window", "finding": "I2", "dimension": "correctness", "accepted": True},
                ],
            },
        }
        for shard in result["shards"]:
            path = self.task / shard["writes"][0]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(safeyaml.dump(bodies[shard["id"]]), encoding="utf-8")
        self.assertEqual(fanout.merge("feat", "plan", self.root), 0)
        plan = safeyaml.mapping(self.task / "verify" / "plan.yaml")
        self.assertEqual(
            [c["id"] for c in plan["cases"]],
            ["selftest-i1-query", "selftest-i1-branch", "selftest-i2-window"],
        )
        self.assertTrue(all(c["accepted"] is False for c in plan["cases"]))
        arch = safeyaml.mapping(self.task / "arch.yaml")
        included = [row["path"] for row in arch["impact_candidates"] if row.get("include") is True]
        self.assertEqual(included, ["mod/A.java", "mod/B.java"])

    def test_merge_report_numbers_findings(self) -> None:
        shards = [
            {"id": "mod-a", "writes": ["review/shards/mod-a.md"]},
            {"id": "mod-b", "writes": ["review/shards/mod-b.md"]},
        ]
        self._manifest("report", shards, {"review.md": ""})
        for shard, body in (
            ("mod-a", "### FINDING\n- 位置: A.java query\n- 根据: C1\n"),
            ("mod-b", "### UNPROVEN\n- B 未打开\n"),
        ):
            path = self.task / "review" / "shards" / f"{shard}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        self.assertEqual(fanout.merge("feat", "report", self.root), 0)
        text = (self.task / "review.md").read_text(encoding="utf-8")
        self.assertIn("### I1 待签收", text)
        self.assertIn("A.java query", text)
        self.assertIn("### mod-b", text)
        self.assertNotIn("### I2", text)

    def test_merge_run_updates_status_only(self) -> None:
        _plan(self.task, "test", [
            _case("a", "shell", command="echo a"),
            _case("b", "shell", command="echo b"),
        ])
        result = fanout.assess("feat", "run", self.root)
        fanout.write_manifest("feat", result, self.root)
        for shard in result["shards"]:
            cid = shard["units"][0]
            evidence = self.task / "verify" / "evidence" / cid / "out.txt"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("ok\n", encoding="utf-8")
            body = {"cases": [{"id": cid, "status": "PASS", "evidence": f"verify/evidence/{cid}/out.txt"}]}
            path = self.task / shard["writes"][0]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(safeyaml.dump(body), encoding="utf-8")
        self.assertEqual(fanout.merge("feat", "run", self.root), 0)
        plan = safeyaml.mapping(self.task / "verify" / "plan.yaml")
        self.assertEqual({c["id"]: c["status"] for c in plan["cases"]}, {"a": "PASS", "b": "PASS"})
        self.assertTrue(plan["accepted"])

    def test_merge_rootcause_keeps_the_other_hypothesis(self) -> None:
        (self.task / "hypotheses.yaml").write_text(safeyaml.dump({
            "schema_version": 1,
            "feature": "feat",
            "items": [
                {"id": "H1", "status": "open", "evidence": [], "claim": "a"},
                {"id": "H2", "status": "open", "evidence": [], "claim": "b"},
            ],
        }), encoding="utf-8")
        result = fanout.assess("feat", "rootcause", self.root)
        fanout.write_manifest("feat", result, self.root)
        for shard, status, note in (
            (result["shards"][0], "disproven", "ruled out by the log"),
            (result["shards"][1], "proven", ""),
        ):
            path = self.task / shard["writes"][0]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(safeyaml.dump({
                "shard": shard["id"],
                "status": status,
                "note": note,
                "evidence": [f"{shard['id']}.log"],
                "repro": "yes",
            }), encoding="utf-8")
        self.assertEqual(fanout.merge("feat", "rootcause", self.root), 0)
        data = safeyaml.mapping(self.task / "hypotheses.yaml")
        by_id = {item["id"]: item for item in data["items"]}
        self.assertEqual(by_id["H1"]["status"], "disproven")
        self.assertEqual(by_id["H1"]["claim"], "a")
        self.assertEqual(by_id["H2"]["status"], "proven")
        self.assertEqual(by_id["H2"]["evidence"], ["H2.log"])

    def test_record_name_keeps_shards_apart(self) -> None:
        self.assertEqual(record_name("run", 1, ""), "run-1.yaml")
        self.assertEqual(record_name("run", 1, "H1"), "run-H1-1.yaml")
        with self.assertRaises(ValueError):
            record_name("run", 1, "../x")


if __name__ == "__main__":
    unittest.main()
