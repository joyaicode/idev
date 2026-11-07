#!/usr/bin/env python3
"""Each detector gets a positive and a negative case, written before it ships.

`references/failure-modes.md` 三 records why: a regex that is only tried
against the case it was written for passes both directions wrongly. The
negative cases here are the point — a detector that fires on ordinary code
would be worse than the gap it closes, because the plugins are advisory and
a noisy warning teaches people to skip the whole report.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "plugin"))
import canon_smells as cs  # noqa: E402
import python_inspect  # noqa: E402

DECL_JAVA = __import__("re").compile(
    r"(?:public|private|protected|static|final|\s)+[\w.<>\[\]]+\s+(?P<name>\w+)\s*\("
)
DECL_PY = __import__("re").compile(r"(?m)^[ \t]*def[ \t]+(?P<name>\w+)[ \t]*\(")


class Mask(unittest.TestCase):
    def test_offsets_survive(self):
        text = 'int a = 1; // getX().getY().doIt()\nint b = 2;'
        masked = cs.mask(text, [(11, len(text.split("\n")[0]))])
        self.assertEqual(len(masked), len(text))
        self.assertEqual(masked.count("\n"), text.count("\n"))

    def test_comment_chain_not_reported(self):
        text = "// a.getB().getC().doIt()\nint x = 1;"
        masked = cs.mask(text, [(0, 25)])
        self.assertEqual(cs.chain_hits(masked, "A.java"), [])


class C22Chain(unittest.TestCase):
    def test_getter_chain_reported(self):
        src = "String c = order.getCustomer().getAddress().getCity();"
        self.assertEqual(len(cs.chain_hits(src, "A.java")), 1)

    def test_stream_api_not_reported(self):
        src = "list.stream().filter(x -> x > 1).map(f).collect(toList());"
        self.assertEqual(cs.chain_hits(src, "A.java"), [])

    def test_single_hop_not_reported(self):
        src = "String n = order.getCustomer().getName();"
        self.assertEqual(cs.chain_hits(src, "A.java"), [])


class C12Naming(unittest.TestCase):
    def test_vague_name_reported(self):
        src = "public String buildDataHelper(int a) {}"
        hits = cs.naming_hits(src, "A.java", DECL_JAVA)
        self.assertTrue(hits, "expected a C12 hit")

    def test_concrete_name_not_reported(self):
        src = "public String renderInvoiceHeader(int a) {}"
        self.assertEqual(cs.naming_hits(src, "A.java", DECL_JAVA), [])

    def test_python_def(self):
        self.assertTrue(cs.naming_hits("def tmp_path(x):\n    pass\n", "a.py", DECL_PY))
        self.assertEqual(cs.naming_hits("def resolve_ticket(x):\n    pass\n", "a.py", DECL_PY), [])


class C9Nesting(unittest.TestCase):
    def test_three_levels_reported(self):
        src = "void f() { if (a) { if (b) { if (c) { g(); } } } }"
        self.assertEqual(len(cs.nesting_hits(src, "A.java")), 1)

    def test_two_levels_not_reported(self):
        src = "void f() { if (a) { if (b) { g(); } } }"
        self.assertEqual(cs.nesting_hits(src, "A.java"), [])

    def test_sibling_ifs_not_reported(self):
        src = "void f() { if (a) { g(); } if (b) { h(); } if (c) { i(); } }"
        self.assertEqual(cs.nesting_hits(src, "A.java"), [])

    def test_call_in_condition_still_detected(self):
        src = "void f() { if (p.get(k)) { if (q.get(k)) { if (r) { g(); } } } }"
        self.assertEqual(len(cs.nesting_hits(src, "A.java")), 1)

    def test_indent_three_levels(self):
        src = "def f():\n    if a:\n        if b:\n            if c:\n                g()\n"
        self.assertEqual(len(cs.nesting_hits_indent(src, "a.py")), 1)

    def test_indent_two_levels_not_reported(self):
        src = "def f():\n    if a:\n        if b:\n            g()\n"
        self.assertEqual(cs.nesting_hits_indent(src, "a.py"), [])

    def test_python_statement_lines_filter_ternary(self):
        src = (
            "def f(a):\n"
            "    if a:\n"
            "        out = (\n"
            "            \"x\" if a else \"y\"\n"
            "        )\n"
            "        return out\n"
        )
        statement_lines = {2}
        self.assertEqual(
            cs.nesting_hits_indent(src, "a.py", statement_lines=statement_lines), []
        )

    def test_python_plugin_reports_real_statement_not_ternary(self):
        ternary = (
            "def f(a):\n"
            "    if a:\n"
            "        out = (\n"
            "            \"x\" if a else \"y\"\n"
            "        )\n"
            "        return out\n"
        )
        self.assertEqual(python_inspect.inspect_text(ternary, "a.py"), [])

        nested = "def f(a, b, c):\n    if a:\n        if b:\n            if c:\n                return 1\n    return 0\n"
        self.assertEqual(len(python_inspect.inspect_text(nested, "a.py")), 1)

    def test_go_braceless_if_reported(self):
        src = "func f() {\n\tif a != nil {\n\t\tif b != nil {\n\t\t\tif c {\n\t\t\t\tg()\n\t\t\t}\n\t\t}\n\t}\n}"
        self.assertEqual(len(cs.nesting_hits(src, "a.go")), 1)

    def test_go_two_levels_not_reported(self):
        src = "func f() {\n\tif a != nil {\n\t\tif b != nil {\n\t\t\tg()\n\t\t}\n\t}\n}"
        self.assertEqual(cs.nesting_hits(src, "a.go"), [])

    def test_else_if_is_not_a_new_level(self):
        src = "func f() {\n\tif a {\n\t\tg()\n\t} else if b {\n\t\th()\n\t} else if c {\n\t\ti()\n\t}\n}"
        self.assertEqual(cs.nesting_hits(src, "a.go"), [])


class GoChain(unittest.TestCase):
    def test_exported_getter_chain_reported(self):
        src = "city := order.GetCustomer().GetAddress().Format()"
        self.assertEqual(len(cs.chain_hits(src, "a.go")), 1)

    def test_go_builder_not_reported(self):
        src = "b.Set(1).Add(2).Build()"
        self.assertEqual(cs.chain_hits(src, "a.go"), [])


class C7Swallow(unittest.TestCase):
    def test_empty_catch_reported(self):
        self.assertEqual(len(cs.swallow_hits("try { f(); } catch (Exception e) { }", "A.java")), 1)

    def test_return_false_catch_reported(self):
        src = "try { f(); } catch (Exception e) { return false; }"
        self.assertEqual(len(cs.swallow_hits(src, "A.java")), 1)

    def test_handled_catch_not_reported(self):
        src = 'try { f(); } catch (Exception e) { log.warn("f failed", e); throw e; }'
        self.assertEqual(cs.swallow_hits(src, "A.java"), [])

    def test_python_pass_reported(self):
        src = "try:\n    f()\nexcept ValueError:\n    pass\n"
        self.assertEqual(len(cs.swallow_hits(src, "a.py", python=True)), 1)

    def test_python_handled_not_reported(self):
        src = "try:\n    f()\nexcept ValueError as e:\n    raise Failed(e)\n"
        self.assertEqual(cs.swallow_hits(src, "a.py", python=True), [])

    def test_return_none_is_not_a_smell(self):
        """C7 names [] / {} / false. "not found" is a result, not a swallow."""
        src = "try:\n    f()\nexcept OSError:\n    return None\n"
        self.assertEqual(cs.swallow_hits(src, "a.py", python=True), [])

    def test_return_empty_list_reported(self):
        src = "try:\n    f()\nexcept OSError:\n    return []\n"
        self.assertEqual(len(cs.swallow_hits(src, "a.py", python=True)), 1)

    def test_java_return_null_is_not_a_smell(self):
        src = "try { f(); } catch (Exception e) { return null; }"
        self.assertEqual(cs.swallow_hits(src, "A.java"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
