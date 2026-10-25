#!/usr/bin/env python3
"""The Java plugin flags the three shapes it owns, and ignores the lookalikes."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "plugin"))
import java_inspect  # noqa: E402


def repo_with(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    subprocess.check_call(["git", "init", "-q"], cwd=root)
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body))
    return root


def titles(root: Path) -> list[str]:
    hits, _scope = java_inspect.inspect_repo(root)
    return [title for _rel, _line, title in hits]


class PluginTest(unittest.TestCase):
    def test_arm_assignment_is_a_finding(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    void run() throws Exception {
                        java.io.FileOutputStream out = new java.io.FileOutputStream("a");
                        out.close();
                    }
                }
                """,
        })
        self.assertTrue(any("try-with-resources" in title for title in titles(root)))

    def test_arm_already_in_try_is_quiet(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    void run() throws Exception {
                        try (java.io.FileOutputStream out = new java.io.FileOutputStream("a")) {
                            out.write(1);
                        }
                    }
                }
                """,
        })
        self.assertFalse(any("try-with-resources" in title for title in titles(root)))

    def test_second_resource_in_try_is_quiet(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    void run() throws Exception {
                        try (java.io.FileInputStream in = new java.io.FileInputStream("a");
                             java.io.FileOutputStream out = new java.io.FileOutputStream("b")) {
                            out.write(in.read());
                        }
                    }
                }
                """,
        })
        self.assertFalse(any("try-with-resources" in title for title in titles(root)))

    def test_multiline_try_resource_is_quiet(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    void run() throws Exception {
                        try (
                            java.io.FileInputStream in = new java.io.FileInputStream("a");
                            java.io.FileOutputStream out = new java.io.FileOutputStream("b")
                        ) {
                            out.write(1);
                        }
                    }
                }
                """,
        })
        self.assertFalse(any("try-with-resources" in title for title in titles(root)))

    def test_stream_in_try_block_is_still_a_finding(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    void run() throws Exception {
                        try {
                            java.io.FileOutputStream out = new java.io.FileOutputStream("a");
                            out.close();
                        } catch (Exception ignored) {
                        }
                    }
                }
                """,
        })
        self.assertTrue(any("try-with-resources" in title for title in titles(root)))

    def test_returned_stream_is_quiet(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    java.io.FileInputStream open() throws Exception {
                        return new java.io.FileInputStream("a");
                    }
                }
                """,
        })
        self.assertEqual(titles(root), [])

    def test_stream_inside_a_string_is_quiet(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    String sample() {
                        return "new java.io.FileOutputStream(\\"a\\")";
                    }
                }
                """,
        })
        self.assertEqual(titles(root), [])

    def test_unused_private_method(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    private void gone() {}
                    void run() {}
                }
                """,
        })
        self.assertTrue(any("没有调用" in title for title in titles(root)))

    def test_used_private_method_is_quiet(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    private void kept() {}
                    void run() { kept(); }
                }
                """,
        })
        self.assertEqual(titles(root), [])

    def test_public_method_is_not_an_unused_finding(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    public void directory() {}
                }
                """,
        })
        self.assertEqual(titles(root), [])

    def test_same_literal_on_every_call(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    private void put(String state) {}
                    void run() { put("NONE"); put("NONE"); }
                }
                """,
        })
        found = titles(root)
        self.assertTrue(any("state" in title and "NONE" in title for title in found))

    def test_mixed_arguments_are_quiet(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    private void put(String state) {}
                    void run(String state) { put("NONE"); put(state); }
                }
                """,
        })
        self.assertFalse(any("形参" in title for title in titles(root)))

    def test_one_call_is_not_enough(self) -> None:
        root = repo_with({
            "src/A.java": """\
                class A {
                    private void put(String state) {}
                    void run() { put("NONE"); }
                }
                """,
        })
        self.assertFalse(any("形参" in title for title in titles(root)))


if __name__ == "__main__":
    unittest.main()
