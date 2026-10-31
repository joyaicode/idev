#!/usr/bin/env python3
"""doc_home.layout_for: code-review stays out of engineering docs.

A repo that already publishes docs/task/ still sends product features
there. The whole-repo code-review process is not one of those features.
Even when docs/task/code-review/ already holds a plan, the home is
.idev/task/code-review/.

    python3 scripts/lib/test_doc_home.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doc_home  # noqa: E402


class CodeReviewHome(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="idev-doc-home-")
        self.repo = Path(self._tmp.name)
        tracker = self.repo / "docs" / "agents" / "issue-tracker.md"
        tracker.parent.mkdir(parents=True)
        tracker.write_text(
            "Issues live in docs/task/.\n\ngrilling\n",
            encoding="utf-8",
        )
        product = self.repo / "docs" / "task" / "code-review" / "verify"
        product.mkdir(parents=True)
        (product / "plan.yaml").write_text("cases: []\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_code_review_is_native_even_when_docs_already_hold_it(self) -> None:
        self.assertEqual(doc_home.layout_for(self.repo, "code-review"), "native")
        task = doc_home.homes(self.repo, "code-review")["task"]
        self.assertEqual(task, self.repo / ".idev" / "task" / "code-review")
        self.assertEqual(doc_home.homes(self.repo, "code-review")["work"], task)
        self.assertNotIn("docs", task.parts)

    def test_product_feature_keeps_deliverables_and_parks_intermediates(self) -> None:
        self.assertEqual(doc_home.layout_for(self.repo, "widget"), "product")
        found = doc_home.homes(self.repo, "widget")
        self.assertEqual(found["task"], self.repo / "docs" / "task" / "widget")
        self.assertEqual(found["work"], self.repo / ".idev" / "task" / "widget")
        self.assertEqual(found["spec"], self.repo / "docs" / "spec" / "widget.md")
        self.assertEqual(
            doc_home.intermediate(self.repo, "widget", "review.md"),
            self.repo / ".idev" / "task" / "widget" / "review.md",
        )

    def test_existing_intermediate_stays_readable_until_moved(self) -> None:
        legacy = self.repo / "docs" / "task" / "widget" / "review.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("old\n", encoding="utf-8")
        self.assertEqual(doc_home.intermediate(self.repo, "widget", "review.md"), legacy)


if __name__ == "__main__":
    unittest.main(verbosity=2)
