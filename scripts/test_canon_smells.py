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


class Section24Thresholds(unittest.TestCase):
    """§2.4 function-level thresholds — one positive and one negative each.

    The negatives are the point: a detector that fires on ordinary code
    would drown the advisory report (failure-modes.md 三).
    """

    def test_length_over_reported(self):
        funcs = [{"name": "f", "line": 3, "lines": 21, "params": 1, "complexity": 2}]
        self.assertEqual(len(cs.func_length_hits(funcs, "A.py")), 1)

    def test_length_at_limit_not_reported(self):
        funcs = [{"name": "f", "line": 3, "lines": 20, "params": 1, "complexity": 2}]
        self.assertEqual(cs.func_length_hits(funcs, "A.py"), [])

    def test_params_over_reported(self):
        funcs = [{"name": "f", "line": 3, "lines": 5, "params": 4, "complexity": 2}]
        self.assertEqual(len(cs.param_count_hits(funcs, "A.py")), 1)

    def test_params_at_limit_not_reported(self):
        funcs = [{"name": "f", "line": 3, "lines": 5, "params": 3, "complexity": 2}]
        self.assertEqual(cs.param_count_hits(funcs, "A.py"), [])

    def test_complexity_over_reported(self):
        funcs = [{"name": "f", "line": 3, "lines": 5, "params": 1, "complexity": 11}]
        self.assertEqual(len(cs.complexity_hits(funcs, "A.py")), 1)

    def test_complexity_at_limit_not_reported(self):
        funcs = [{"name": "f", "line": 3, "lines": 5, "params": 1, "complexity": 10}]
        self.assertEqual(cs.complexity_hits(funcs, "A.py"), [])

    def test_brace_complexity_counts_keywords_and_ops(self):
        body = "if (a) { x(); } else if (b && c) { y(); } try { z(); } catch (E e) { w(); }"
        # if ×2, && ×1, catch ×1 → 1 + 4 = 5
        self.assertEqual(cs.brace_complexity(body), 5)

    def test_brace_complexity_ignores_string_if(self):
        # a masked body: strings are blanked upstream, but a bare word check
        # still guards against keyword-in-identifier misfires
        body = "notifyCustomer(x); wifiCheck(y); catchAll(z);"
        self.assertEqual(cs.brace_complexity(body), 1)

    def test_brace_func_spans_reports_function_body(self):
        src = "class A {\n    void f(int a) {\n        g();\n    }\n}\n"
        spans = cs.brace_func_spans(src, [__import__("re").search(r"\bvoid\s+(?P<name>f)\s*\((?P<params>[^()]*)\)\s*\{", src)])
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["name"], "f")
        self.assertEqual(spans[0]["lines"], 3)
        self.assertEqual(spans[0]["params"], 1)

    def test_brace_func_spans_skips_bodyless_declaration(self):
        src = "interface I {\n    int compute(int a, int b);\n}\n"
        m = __import__("re").search(r"\bint\s+(?P<name>compute)\s*\((?P<params>[^()]*)\)", src)
        self.assertEqual(cs.brace_func_spans(src, [m]), [])


class Section24Python(unittest.TestCase):
    """The Python AST path — nested functions report under their own def."""

    def test_long_function_reported(self):
        body = "\n".join("    x%d = %d" % (i, i) for i in range(20))
        src = "def f(a, b, c):\n" + body + "\n    return c\n"
        hits = python_inspect.inspect_text(src, "t.py")
        self.assertTrue(any("长达" in h[2] for h in hits), hits)

    def test_ok_function_not_reported(self):
        src = "def ok(a, b, c):\n    if a:\n        return b\n    return c\n"
        self.assertEqual(python_inspect.inspect_text(src, "t.py"), [])

    def test_complexity_reported(self):
        body = "\n".join("    if x%s:\n        pass" % i for i in range(11))
        src = "def cx(a):\n" + body + "\n    return a\n"
        hits = python_inspect.inspect_text(src, "t.py")
        self.assertTrue(any("圈复杂度" in h[2] for h in hits), hits)

    def test_params_reported(self):
        src = "def many(a, b, c, d, e):\n    return a\n"
        hits = python_inspect.inspect_text(src, "t.py")
        self.assertTrue(any("参数" in h[2] for h in hits), hits)

    def test_string_branch_words_not_reported(self):
        src = 'def s(a):\n    """if x and y or z"""\n    return a\n'
        self.assertEqual(python_inspect.inspect_text(src, "t.py"), [])


class Section24Go(unittest.TestCase):
    def test_go_params_reported(self):
        src = "package main\n\nfunc manyParams(a int, b string, c bool, d float64, e rune) error {\n\treturn nil\n}\n"
        import go_inspect
        hits = go_inspect.inspect_text(src, "t.go")
        self.assertTrue(any("参数" in h[2] for h in hits), hits)

    def test_go_receiver_not_a_param(self):
        src = "package main\n\nfunc (s *Server) handle(w io.Writer, r *Request) error {\n\treturn nil\n}\n"
        import go_inspect
        self.assertEqual(go_inspect.inspect_text(src, "t.go"), [])


class Section24Java(unittest.TestCase):
    def test_java_length_reported(self):
        import java_inspect
        lines = "\n".join("        int v%d = %d;" % (i, i) for i in range(20))
        src = "public class A {\n    public int longOne(int a, int b, int c) {\n%s\n        return a;\n    }\n}\n" % lines
        hits = java_inspect.inspect_text(src, "A.java")
        self.assertTrue(any("长达" in h[2] for h in hits), hits)

    def test_java_interface_method_not_reported(self):
        import java_inspect
        src = "public interface D {\n    int compute(int a, int b, int c, int d, int e);\n}\n"
        self.assertEqual(java_inspect.inspect_text(src, "D.java"), [])

    def test_java_test_annotation_excluded(self):
        import java_inspect
        src = ("import org.junit.Test;\n\npublic class E {\n    @Test\n    public void longTest() {\n"
               + "\n".join("        int v%d = %d;" % (i, i) for i in range(25)) + "\n    }\n}\n")
        self.assertEqual(java_inspect.inspect_text(src, "E.java"), [])


class Section24Js(unittest.TestCase):
    def test_js_function_decl_reported(self):
        import js_inspect
        src = "export function many(a, b, c, d, e) {\n  return a;\n}\n"
        hits = js_inspect.inspect_text(src, "a.js")
        self.assertTrue(any("参数" in h[2] for h in hits), hits)

    def test_js_arrow_function_not_reported(self):
        import js_inspect
        src = "const f = (a, b, c, d, e) => {\n  return a;\n};\n"
        self.assertEqual(js_inspect.inspect_text(src, "a.js"), [])


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
