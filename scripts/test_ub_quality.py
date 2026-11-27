#!/usr/bin/env python3
"""The ub-quality advisory gate: fixed start point, per-function verdicts.

Absorbed from joy-dev's ub-mode. These tests lock the three verdict shapes
the gate promises — new/misnamed functions are checked as new (renaming
does not forgive debt), a green function turned red is the worst finding,
and a function already over threshold at the start only has to not get
worse. The advisory layer must never fail the scan chain: missing tools
mean UNPROVEN, exit 0.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "ub_quality.py"

JAVA = """public class A {
    public int simple() { return 1; }
    public int complex(int x) {
        if (x > 1) { x = x + 1; }
        if (x > 2) { x = x + 2; }
        if (x > 3) { x = x + 3; }
        return x;
    }
}
"""


def fake_tool(home: Path, name: str, lines: list[str]) -> None:
    d = home / name
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("#!/usr/bin/env bash\n" + "\n".join(lines) + "\n",
                          encoding="utf-8")
    (d / name).chmod(0o755)


class UBQuality(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve() / "one"
        (self.repo / ".idev" / "task" / "demo" / "src").mkdir(parents=True)
        (self.repo / "src").mkdir()
        (self.repo / "src" / "A.java").write_text(JAVA, encoding="utf-8")
        for args in (["init", "-q"], ["config", "user.email", "t@t"],
                     ["config", "user.name", "t"]):
            subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=self.repo,
                       check=True, capture_output=True)
        self.home = Path(tmp.name) / "tools"
        self.env_no_tools = dict(_clean_env(), UB_MODE_HOME=str(self.home / "missing"))

    def run_cmd(self, *extra: str, env=None) -> tuple[int, str]:
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *extra],
            capture_output=True, text=True, timeout=60,
            env=env or self.env_no_tools,
        )
        return done.returncode, done.stdout + done.stderr

    def snapshot(self) -> None:
        rc, out = self.run_cmd("snapshot", "--feature", "demo")
        self.assertEqual(rc, 0, out)

    # --- snapshot: fixed once, never reset --------------------------------

    def test_snapshot_is_idempotent_across_new_commits(self) -> None:
        self.snapshot()
        first = (self.repo / ".idev" / "task" / "demo" / "start-snapshot.yaml").read_text()
        (self.repo / "src" / "A.java").write_text(JAVA + "// more\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "rework"], cwd=self.repo,
                       check=True, capture_output=True)
        rc, out = self.run_cmd("snapshot", "--feature", "demo")
        self.assertEqual(rc, 0)
        self.assertIn("返工不重置", out)
        second = (self.repo / ".idev" / "task" / "demo" / "start-snapshot.yaml").read_text()
        self.assertEqual(first, second)

    # --- advisory: missing tools are UNPROVEN, never FAIL -----------------

    def test_missing_tools_is_unproven_exit_zero(self) -> None:
        self.snapshot()
        rc, out = self.run_cmd("check", "--feature", "demo")
        self.assertEqual(rc, 0)
        self.assertIn("UNPROVEN", out)
        self.assertIn("crapper", out)

    # --- the three verdicts -----------------------------------------------

    def test_a_new_function_over_threshold_is_a_hit(self) -> None:
        self.snapshot()
        fake_tool(self.home, "crapper",
                  ["echo 'src/A.java:brandnew CC=5 COV=0.5 CRAP=30'"])
        fake_tool(self.home, "dryer", ["exit 0"])
        rc, out = self.run_cmd("check", "--feature", "demo",
                               env=dict(self.env_no_tools, UB_MODE_HOME=str(self.home)))
        self.assertEqual(rc, 0)
        self.assertIn("CRAP-HIT src/A.java:brandnew CRAP=30", out)
        self.assertIn("新增或改名", out)  # renaming does not forgive debt

    def test_a_green_function_turned_red_is_the_worst_hit(self) -> None:
        self.snapshot()
        fake_tool(self.home, "crapper",
                  ["echo 'src/A.java:simple CC=6 COV=0.4 CRAP=66'"])
        fake_tool(self.home, "dryer", ["exit 0"])
        rc, out = self.run_cmd("check", "--feature", "demo",
                               env=dict(self.env_no_tools, UB_MODE_HOME=str(self.home)))
        self.assertEqual(rc, 0)
        self.assertIn("把绿函数改红了", out)

    def test_existing_debt_not_worse_is_ok_worse_is_flagged(self) -> None:
        self.snapshot()
        # complex is already over threshold at the start (CC=4).
        fake_tool(self.home, "crapper",
                  ["echo 'src/A.java:complex CC=4 COV=0.5 CRAP=20'"])
        fake_tool(self.home, "dryer", ["exit 0"])
        rc, out = self.run_cmd("check", "--feature", "demo",
                               env=dict(self.env_no_tools, UB_MODE_HOME=str(self.home)))
        self.assertEqual(rc, 0)
        self.assertIn("DEBT-OK", out)
        self.assertIn("不恶化条件满足", out)

        fake_tool(self.home, "crapper",
                  ["echo 'src/A.java:complex CC=5 COV=0.5 CRAP=45'"])
        rc, out = self.run_cmd("check", "--feature", "demo",
                               env=dict(self.env_no_tools, UB_MODE_HOME=str(self.home)))
        self.assertEqual(rc, 0)
        self.assertIn("DEBT-WORSE", out)
        self.assertIn("必写", out)

    def test_a_duplication_pair_over_threshold_is_a_hit(self) -> None:
        self.snapshot()
        fake_tool(self.home, "crapper", ["exit 0"])
        fake_tool(self.home, "dryer",
                  ["echo 'src/A.java:complex ≈ src/A.java:simple sim=0.91'"])
        rc, out = self.run_cmd("check", "--feature", "demo",
                               env=dict(self.env_no_tools, UB_MODE_HOME=str(self.home)))
        self.assertEqual(rc, 0)
        self.assertIn("DUP-HIT", out)
        self.assertIn("P17", out)  # is it really a duplicate — check elision rules first

    def test_check_fixes_a_snapshot_when_none_exists(self) -> None:
        rc, out = self.run_cmd("check", "--feature", "demo")
        self.assertEqual(rc, 0)
        self.assertTrue((self.repo / ".idev" / "task" / "demo" / "start-snapshot.yaml").is_file())


def _clean_env() -> dict:
    env = dict(__import__("os").environ)
    env.pop("UB_MODE_HOME", None)
    return env


if __name__ == "__main__":
    unittest.main()
