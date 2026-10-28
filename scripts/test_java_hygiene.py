#!/usr/bin/env python3
"""java.md yellow bars the review used to skip.

The fixture is the shape IntelliJ flags and a principle essay does not:
`new ArrayList<String>()` on a Java 8 tree. Diamond, a comment, a string,
and an anonymous class must not be reported at level 8.

    python3 scripts/test_java_hygiene.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import delegation  # noqa: E402
import java_hygiene  # noqa: E402

SAMPLE = textwrap.dedent(
    """\
    package demo;

    import java.util.*;

    public class Sample {
        // new ArrayList<String>() stays in the comment
        private final Map<String, String> kept = new HashMap<>();
        private final Map<String, List<String>> nested = new HashMap<String, List<String>>();
        String literal = "new ArrayList<String>()";

        List<String> plain() {
            return new ArrayList<String>();
        }

        List<String> inferred() {
            return Collections.<String>emptyList();
        }

        int boxed() {
            return Integer.valueOf(1);
        }

        Object anon() {
            return new Callable<String>() {
                public String call() { return ""; }
            };
        }

        List<String> factory() {
            return List.of("a");
        }
    }
    """
)


def rules(level: str) -> list[str]:
    return [hit.rule for hit in java_hygiene.hits_in(SAMPLE, "Sample.java", level)]


class Patterns(unittest.TestCase):
    def test_java8_flags_the_screenshot_shape_and_skips_anonymous(self) -> None:
        got = rules("8")
        self.assertEqual(
            got,
            [
                java_hygiene.RULE_DIAMOND,  # HashMap<String, List<String>>
                java_hygiene.RULE_DIAMOND,  # new ArrayList<String>()
                java_hygiene.RULE_INFER,
                java_hygiene.RULE_BOX,
                java_hygiene.RULE_OF,
            ],
        )

    def test_java17_diamonds_anonymous_and_allows_list_of(self) -> None:
        got = rules("17")
        self.assertIn(java_hygiene.RULE_DIAMOND, got)
        self.assertNotIn(java_hygiene.RULE_OF, got)
        # The anonymous Callable is legal to diamond from 9 on.
        anon = [
            hit
            for hit in java_hygiene.hits_in(SAMPLE, "Sample.java", "17")
            if "Callable" in hit.snippet
        ]
        self.assertEqual(len(anon), 1)
        self.assertEqual(anon[0].rule, java_hygiene.RULE_DIAMOND)

    def test_basename_line_counts_as_cited(self) -> None:
        hits = java_hygiene.hits_in(SAMPLE, "mod/Sample.java", "8")
        diamond = next(hit for hit in hits if "ArrayList" in hit.snippet)
        self.assertTrue(diamond.cited_in(f"见 {diamond.rel}:{diamond.line}"))
        self.assertTrue(diamond.cited_in(f"Sample.java:{diamond.line}"))
        self.assertFalse(diamond.cited_in("高内聚低耦合，设计模式已考虑"))

    def test_collections_factory_blocks_collectors_does_not(self) -> None:
        text = (
            "class A {\n"
            "  Map<String, String> a(Map<String, String> in) {\n"
            "    return in == null ? Collections.<String, String>emptyMap() : in;\n"
            "  }\n"
            "  Object b() { return Collectors.<String>toList(); }\n"
            "}\n"
        )
        hits = java_hygiene.hits_in(text, "A.java", "8")
        owed = java_hygiene.missing(hits, "")
        self.assertTrue(any(hit.rule == java_hygiene.RULE_INFER for hit in owed))
        self.assertTrue(any(hit.rule == java_hygiene.RULE_INFER_NOTE for hit in hits))
        self.assertFalse(any(hit.rule == java_hygiene.RULE_INFER_NOTE for hit in owed))

    def test_taskstore_panel_is_blocking(self) -> None:
        text = textwrap.dedent(
            """\
            class Store {
              void claim() {
                Collections.sort(due, Default::byWake);
                found.sort(Comparator.comparing(run -> run.runId));
              }
              void order() {
                Collections.sort(found, (left, right) -> left.runId.compareTo(right.runId));
              }
              void loop() {
                while (open.get()) {
                  for (int i = 0; i < 2; i++) {
                    Thread.sleep(tickMs);
                  }
                  TimeUnit.MILLISECONDS.sleep(tickMs);
                  log.warn("async worker cleared interrupt and continues");
                  log.warn("async worker cleared interrupt and continues");
                }
              }
            }
            """
        )
        hits = java_hygiene.hits_in(text, "TaskStore.java", "8")
        rules = {hit.rule for hit in hits}
        self.assertIn(java_hygiene.RULE_LIST_SORT, rules)
        self.assertIn(java_hygiene.RULE_COMPARING, rules)
        self.assertIn(java_hygiene.RULE_SLEEP, rules)
        self.assertIn(java_hygiene.RULE_SIMILAR_LOG, rules)
        self.assertEqual(sum(1 for hit in hits if hit.rule == java_hygiene.RULE_SLEEP), 1)
        self.assertFalse(any("TimeUnit" in hit.snippet for hit in hits))


class Accessors(unittest.TestCase):
    """The TaskExecutor shape: trivial getters, Lombok on the module, test-only calls."""

    def test_unused_and_lombok_split(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name)
        module = repo / "mod"
        main = module / "src" / "main" / "java" / "task"
        test = module / "src" / "test" / "java" / "task"
        main.mkdir(parents=True)
        test.mkdir(parents=True)
        (module / "pom.xml").write_text(
            "<project><dependencies><dependency><artifactId>lombok</artifactId></dependency></dependencies></project>\n",
            encoding="utf-8",
        )
        (main / "TaskExecutor.java").write_text(
            textwrap.dedent(
                """\
                package task;
                final class TaskWork {
                    private final String serviceCode;
                    private final String taskName;
                    private final String idempotencyKey;
                    public String getServiceCode() {
                        return serviceCode;
                    }
                    public String getTaskName() {
                        return taskName;
                    }
                    public String getIdempotencyKey() {
                        return idempotencyKey;
                    }
                }
                """
            ),
            encoding="utf-8",
        )
        (main / "Use.java").write_text(
            "package task;\nclass Use { String n(TaskWork work) { return work.getTaskName(); } }\n",
            encoding="utf-8",
        )
        (test / "UseTest.java").write_text(
            "package task;\nclass UseTest { String k(TaskWork work) { return work.getIdempotencyKey(); } }\n",
            encoding="utf-8",
        )
        rel = "mod/src/main/java/task/TaskExecutor.java"
        hits = java_hygiene.accessor_hits(repo, [rel])
        by_name = {}
        for hit in hits:
            by_name.setdefault(hit.snippet.split()[0], set()).add(hit.rule)
        self.assertEqual(by_name.get("getServiceCode"), {java_hygiene.RULE_UNUSED})
        self.assertEqual(by_name.get("getTaskName"), {java_hygiene.RULE_LOMBOK})
        self.assertEqual(by_name.get("getIdempotencyKey"), {java_hygiene.RULE_UNUSED})
        tmp.cleanup()

    def test_shard_only_owes_its_module(self) -> None:
        hits = java_hygiene.hits_in(SAMPLE, "mod/Sample.java", "8")
        self.assertEqual(java_hygiene.missing(hits, "", shard="other"), [])
        self.assertTrue(java_hygiene.missing(hits, "", shard="mod"))


class Delegation(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.check_call(["git", "init", "-q"], cwd=self.repo)
        path = self.repo / "src" / "Store.java"
        path.parent.mkdir()
        path.write_text(
            "class Store { List<String> a() { return new ArrayList<String>(); } }\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_coder_must_fix_a_changed_file(self) -> None:
        record = {
            "agent": "idev-coder",
            "kind": "deliver.code_pass",
            "report": {"raw": "CHANGED: src/Store.java:a\n", "status": "PASS"},
        }
        result = delegation.check_java_hygiene(record, self.repo)
        self.assertTrue(result["java-hygiene"].startswith("FAIL"), result)

    def test_coder_ignores_files_they_did_not_change(self) -> None:
        record = {
            "agent": "idev-coder",
            "kind": "deliver.code_pass",
            "report": {"raw": "CHANGED: 无\n", "status": "PASS"},
        }
        result = delegation.check_java_hygiene(record, self.repo)
        self.assertEqual(result["java-hygiene"], "PASS")

    def test_reviewer_must_cite_the_line(self) -> None:
        review = self.repo / "review.md"
        review.write_text("高内聚，低耦合，设计模式。\n", encoding="utf-8")
        bare = {
            "agent": "idev-reviewer",
            "kind": "review.report",
            "report": {"raw": "STATUS: PASS\n", "evidence": str(review), "status": "PASS"},
        }
        failed = delegation.check_java_hygiene(bare, self.repo)
        self.assertTrue(failed["java-hygiene"].startswith("FAIL"), failed)
        hits, _scope, _level = java_hygiene.scan(self.repo)
        review.write_text(f"I1 {hits[0].token()} 显式类型参数可被替换为<>\n", encoding="utf-8")
        ok = delegation.check_java_hygiene(bare, self.repo)
        self.assertEqual(ok["java-hygiene"], "PASS")


if __name__ == "__main__":
    unittest.main()
