#!/usr/bin/env python3
"""Root-cause probes go through runsc and nowhere else.

    python3 scripts/test_runsc_probe.py
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repl = load("idev_repl_runsc", HERE / "repl.py")
hypothesis = load("idev_hypothesis_runsc", HERE / "hypothesis.py")
runsc_probe = load("idev_runsc_probe", HERE / "lib" / "runsc_probe.py")


def ticket(repo: Path, feature: str = "feat") -> Path:
    home = repo / ".idev" / "task" / feature
    home.mkdir(parents=True)
    return home


_FAKE_RUNSC = """
import os
import sys
import time

log = os.environ["IDEV_FAKE_RUNSC_LOG"]
with open(log, "a", encoding="utf-8") as handle:
    handle.write("\\n".join(sys.argv[1:]) + "\\n")
args = sys.argv[1:]
if "delete" in args:
    delay = os.environ.get("IDEV_FAKE_DELETE_SLEEP", "")
    if delay:
        time.sleep(float(delay))
    code = int(os.environ.get("IDEV_FAKE_DELETE_RC", "0"))
    if code != 0:
        print("delete-boom", file=sys.stderr)
    raise SystemExit(code)
delay = os.environ.get("IDEV_FAKE_RUN_SLEEP", "")
if delay:
    time.sleep(float(delay))
raise SystemExit(0)
"""


def fake_runsc(directory: Path) -> Path:
    log = directory / "argv.log"
    tool = directory / "runsc"
    # Absolute interpreter: the test replaces PATH with this directory alone.
    tool.write_text("#!%s\n%s" % (sys.executable, _FAKE_RUNSC.lstrip("\n")), encoding="utf-8")
    tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    os.environ["IDEV_FAKE_RUNSC_LOG"] = str(log)
    return log


def temp_parents() -> set[Path]:
    return set(Path(tempfile.gettempdir()).glob("idev-runsc-*"))


def mount_of(line: str) -> dict | None:
    prefix = "mount: destination="
    if not line.startswith(prefix):
        return None
    body = line[len(prefix):]
    mode = ""
    if body.endswith(" rw"):
        mode = "rw"
        body = body[:-3]
    elif body.endswith(" ro"):
        mode = "ro"
        body = body[:-3]
    dest, source = body.split(" source=", 1)
    return {"destination": dest, "source": source, "mode": mode}


def mounts_of(receipt: str) -> list[dict]:
    return [item for item in (mount_of(line) for line in receipt.splitlines()) if item]


def snippet_file(repo: Path) -> Path:
    path = repo / "probe.py"
    path.write_text("print('ok')\n", encoding="utf-8")
    return path


class RunscProbeTest(unittest.TestCase):
    def setUp(self):
        self._path = os.environ.get("PATH", "")
        self._timeout = repl.runsc_probe.TIMEOUT_S
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._restore_path)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        ticket(self.repo)

    def _restore_path(self):
        os.environ["PATH"] = self._path
        repl.runsc_probe.TIMEOUT_S = self._timeout
        for key in (
            "IDEV_FAKE_RUNSC_LOG",
            "IDEV_FAKE_RUN_SLEEP",
            "IDEV_FAKE_DELETE_RC",
            "IDEV_FAKE_DELETE_SLEEP",
        ):
            os.environ.pop(key, None)

    def _arm_runsc(self) -> Path:
        bindir = Path(self.tmp.name) / "bin"
        bindir.mkdir(exist_ok=True)
        log = fake_runsc(bindir)
        os.environ["PATH"] = str(bindir)
        return log

    def _run(self, step: str, code: str) -> int:
        ns = argparse.Namespace(
            feature="feat", repo=self.repo, step=step, code=None, note=None,
        )
        # cmd_run reads stdin when code is None. Feed the snippet that way.
        old = sys.stdin
        sys.stdin = __import__("io").StringIO(code)
        try:
            return repl.cmd_run(ns)
        finally:
            sys.stdin = old

    def test_rootcause_invokes_runsc_and_does_not_write_the_repo(self):
        log = self._arm_runsc()
        before = temp_parents()
        marker = self.repo / "marker-from-probe"
        rc = self._run("rootcause", "from pathlib import Path\nPath('marker-from-probe').write_text('x')\n")
        self.assertEqual(rc, 0)
        self.assertFalse(marker.exists())
        self.assertEqual(temp_parents(), before)
        receipt = (self.repo / ".idev/task/feat/repl/rootcause-1.receipt").read_text(encoding="utf-8")
        self.assertIn(repl.runsc_probe.RUNTIME_MARK, receipt)
        self.assertIn("network: none", receipt)
        self.assertNotIn("bundle:", receipt)
        self.assertIn("--network=none", log.read_text(encoding="utf-8"))
        mounts = mounts_of(receipt)
        sources = [item["source"] for item in mounts]
        self.assertNotIn(str(Path.home()), sources)
        repo_mount = next(item for item in mounts if item["destination"] == "/repo")
        self.assertEqual(repo_mount["mode"], "ro")
        self.assertEqual(repo_mount["source"], str(self.repo.resolve()))
        body = (self.repo / ".idev/task/feat/repl/rootcause-1.py").read_text(encoding="utf-8")
        self.assertIn("REPO = Path('/repo')", body)
        self.assertNotEqual(repl.kind_agents.kernel_root().resolve(), self.repo.resolve())
        idev_mount = next(item for item in mounts if item["destination"] == "/idev")
        self.assertEqual(idev_mount["mode"], "ro")

    def test_missing_runsc_does_not_run_on_the_host(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        os.environ["PATH"] = str(empty)
        marker = self.repo / "marker-from-probe"
        rc = self._run("rootcause", "from pathlib import Path\nPath('marker-from-probe').write_text('x')\n")
        self.assertNotEqual(rc, 0)
        self.assertFalse(marker.exists())
        self.assertFalse((self.repo / ".idev/task/feat/repl/rootcause-1.receipt").exists())

    def test_other_steps_stay_on_the_host(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        os.environ["PATH"] = str(empty)
        rc = self._run("arch", "print('host-ok')\n")
        self.assertEqual(rc, 0)
        outs = list((self.repo / ".idev/task/feat/repl").glob("*.out"))
        self.assertEqual(len(outs), 1)
        text = outs[0].read_text(encoding="utf-8")
        self.assertIn("host-ok", text)
        self.assertNotIn(repl.runsc_probe.RUNTIME_MARK, text)
        self.assertFalse(list((self.repo / ".idev/task/feat/repl").glob("*.receipt")))

    def test_check_rejects_a_transcript_without_a_receipt(self):
        repl_dir = self.repo / ".idev/task/feat/repl"
        repl_dir.mkdir()
        bare = repl_dir / "rootcause-9.out"
        bare.write_text("# repl\n", encoding="utf-8")
        data = {"items": [{"id": "H1", "status": "open", "evidence": [str(bare)]}]}
        self.assertEqual(hypothesis.check(data, verbose=False), 1)
        code_only = {"items": [{"id": "H1", "status": "open", "evidence": ["scripts/repl.py:147"]}]}
        self.assertEqual(hypothesis.check(code_only, verbose=False), 0)
        bare.with_suffix(".receipt").write_text(repl.runsc_probe.RUNTIME_MARK + "\n", encoding="utf-8")
        self.assertEqual(hypothesis.check(data, verbose=False), 0)

    def test_run_timeout_drops_the_parent(self):
        self._arm_runsc()
        os.environ["IDEV_FAKE_RUN_SLEEP"] = "5"
        repl.runsc_probe.TIMEOUT_S = 1
        before = temp_parents()
        result = repl.runsc_probe.execute(snippet_file(self.repo), self.repo, self.repo)
        self.assertEqual(result.exit_code, 124)
        self.assertIn("timed out", result.stderr)
        self.assertNotIn("delete failed", result.stderr)
        self.assertNotIn("delete timed out", result.stderr)
        self.assertEqual(temp_parents(), before)

    def test_delete_failure_keeps_the_probe_exit_code(self):
        self._arm_runsc()
        os.environ["IDEV_FAKE_DELETE_RC"] = "9"
        before = temp_parents()
        result = repl.runsc_probe.execute(snippet_file(self.repo), self.repo, self.repo)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("delete failed (9)", result.stderr)
        self.assertTrue(result.launched)
        self.assertEqual(temp_parents(), before)

    def test_delete_timeout_keeps_the_probe_exit_code(self):
        self._arm_runsc()
        os.environ["IDEV_FAKE_DELETE_SLEEP"] = "5"
        repl.runsc_probe.TIMEOUT_S = 1
        before = temp_parents()
        result = repl.runsc_probe.execute(snippet_file(self.repo), self.repo, self.repo)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("delete timed out", result.stderr)
        self.assertEqual(temp_parents(), before)

    def test_bundle_does_not_mount_the_home_directory(self):
        spec = runsc_probe.bundle_spec(
            self.repo, self.repo, Path(self.tmp.name) / "scratch",
            "/repo/snippet.py", sys.executable,
        )
        sources = [m.get("source") for m in spec["mounts"]]
        self.assertNotIn(str(Path.home()), sources)
        self.assertTrue(all("/.ssh" not in str(s) for s in sources))


if __name__ == "__main__":
    unittest.main()
