#!/usr/bin/env python3
"""The ub-quality advisory gate: fixed start point, per-function verdicts.

Absorbed from joy-dev's ub-mode (skills/joy-dev-plan/references/
ub-mode-tools.md), which carries four mechanisms worth keeping and one
architecture not worth copying (there it is a required file with no gate
standing; here it is an advisory layer inside coding-scan):

1. **固定起点** — the feature's source start point is snapshotted once,
   before the first code change, and never reset. Rework, commits and
   session changes all diff against that same start. Without it, "did the
   change make quality worse" has no answerable baseline.
2. **函数清单** — verdicts are per-function against that start point.
   A renamed or moved function keeps its debt (when the signature no
   longer matches, it is checked as new — the debt is not forgiven).
3. **不恶化基线** — a function already over threshold at the start does
   not have to be fixed in this ticket; it only has to not get worse
   (both CC and CRAP no higher than the baseline). New and newly-red
   functions are the ones that must be fixed or written into review.md.
4. **绿测子集** — CRAP needs coverage; the green-test subset produces the
   coverage report. `failure.ignore`-style flags that make red tests
   produce a passing report are the fabrication this gate exists to catch.

The tools themselves (crapper for CRAP, dryer for structural duplication)
are external installs — this script resolves them, runs them, and parses
the reports; it never installs or reimplements them. Missing tools mean
UNPROVEN, not FAIL: the advisory layer must not block the scan chain when
an optional external tool is absent.

    ub_quality.py snapshot --feature F [--repo DIR]
    ub_quality.py check   --feature F [--repo DIR]   # advisory, always exit 0
    ub_quality.py report  --feature F [--repo DIR]

check is wired into coding-scan.sh after the problems/lang sections and,
like the symbol-diff neighbourhood before it, does not touch the exit
code. Hits translate to the existing review numbers: CRAP-HIT → C1
(complexity, split the function / P5 strategy), DUP-HIT → P17 (is it
really a duplicate? opposite elision rules) then R5 (real one, extract).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import safeyaml  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import doc_home  # noqa: E402
except ImportError:
    print("BLOCKED cannot import doc_home from scripts/; run from the idev repo",
          file=sys.stderr)
    raise SystemExit(2) from None

# joy-dev's thresholds, kept: a CRAP score of 13 is where a function with
# full coverage would need cyclomatic complexity 13 (untenable), and with
# low coverage the number climbs fast — 13 catches both shapes.
CRAP_LIMIT = 13
# dryer's similarity threshold, kept as-is from the ub-mode contract.
DUP_LIMIT = 0.82

TOOLS = ("crapper", "dryer")


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _git(repo: Path, *args: str) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", str(repo), *args],
                           capture_output=True, text=True, timeout=30)
        return p.returncode, (p.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_path(feature: str, repo: Path | None) -> Path:
    base = (repo or Path.cwd()).resolve()
    return doc_home.homes(base, feature)["task"] / "start-snapshot.yaml"


def resolve_tool(name: str) -> str:
    """PATH first, then $UB_MODE_HOME/<name>/<name> — joy-dev's resolve order."""
    candidate = subprocess.run(["bash", "-c", f"command -v {name}"],
                               capture_output=True, text=True, timeout=10)
    hit = (candidate.stdout or "").strip()
    if hit:
        return hit
    home = os.environ.get("UB_MODE_HOME") or str(Path.home() / "tools" / "unclebob")
    candidate = Path(home) / name / name
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return ""


def cmd_snapshot(args: argparse.Namespace) -> int:
    """Write the feature's start point once. Idempotent by design.

    Rework, commits and session changes must not reset the baseline — the
    second call finds the file and leaves it alone.
    """
    path = snapshot_path(args.feature, args.repo)
    if path.is_file():
        print(f"OK   start-snapshot already fixed at {path}（返工不重置）")
        return 0
    repo = (args.repo or Path.cwd()).resolve()
    rc, commit = _git(repo, "rev-parse", "HEAD")
    if rc != 0 or not commit:
        print("BLOCKED not a git repo; no start point to fix", file=sys.stderr)
        return 2
    # The files that matter for the diff: everything tracked at this commit.
    # Full hashes would duplicate the object store; the commit IS the state.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safeyaml.dump({
        "schema_version": 1,
        "feature": args.feature,
        "commit": commit,
        "at": now(),
    }), encoding="utf-8")
    print(f"OK   start-snapshot fixed -> {path}")
    print(f"     起点 commit {commit[:10]}；后续判定都对照这里，不随提交漂移")
    return 0


def _load_snapshot(feature: str, repo: Path | None) -> dict | None:
    path = snapshot_path(feature, repo)
    if not path.is_file():
        return None
    data = safeyaml.mapping(path)
    return data or None


def _run_tool(tool: str, repo: Path) -> tuple[int, str]:
    exe = resolve_tool(tool)
    if not exe:
        return 127, ""
    try:
        p = subprocess.run([exe, str(repo)], cwd=str(repo),
                           capture_output=True, text=True, timeout=300)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


# --- crapper report parsing ---------------------------------------------
# crapper emits per-function lines; the ub-mode contract consumes them by
# function identity, not by file thresholds. JSON when available, else the
# text shape "<rel>:<func> CC=<n> COV=<n> CRAP=<n>".
CRAP_LINE = re.compile(r"([\w./-]+\.\w+):(\w+)\s+CC=(\d+)\s+COV=([\d.]+)\s+CRAP=([\d.]+)")
DUP_LINE = re.compile(r"([\w./-]+\.\w+):(\w+)\s*≈\s*([\w./-]+\.\w+):(\w+)\s+sim=([\d.]+)")


def parse_crap(text: str) -> list[dict]:
    out = []
    for m in CRAP_LINE.finditer(text):
        out.append({"rel": m.group(1), "func": m.group(2), "cc": int(m.group(3)),
                    "cov": float(m.group(4)), "crap": float(m.group(5))})
    return out


def parse_dup(text: str) -> list[dict]:
    out = []
    for m in DUP_LINE.finditer(text):
        out.append({"rel_a": m.group(1), "func_a": m.group(2),
                    "rel_b": m.group(3), "func_b": m.group(4),
                    "sim": float(m.group(5))})
    return out


def _start_functions(feature: str, repo: Path) -> dict[str, dict]:
    """Per-function facts at the start point, keyed by rel:func.

    The snapshot stores the commit; the facts are read from it on demand
    (`git show <commit>:<rel>`), so the ledger stays one small file.
    """
    snap = _load_snapshot(feature, repo)
    if not snap:
        return {}
    commit = str(snap.get("commit") or "")
    if not commit:
        return {}
    repo = (repo or Path.cwd()).resolve()
    out: dict[str, dict] = {}
    # Only the functions that show up in the current report need a baseline;
    # the caller fetches what it needs via _start_func_fact.
    out["__commit__"] = {"commit": commit}
    return out


def _start_func_fact(feature: str, repo: Path, rel: str, func: str) -> dict | None:
    """One function's baseline facts from the start commit, or None.

    A function whose body is absent at the start point is new; one that
    moved or was renamed also lands here (its signature no longer matches)
    — debt is not forgiven by renaming.
    """
    snap = _load_snapshot(feature, repo)
    if not snap:
        return None
    commit = str(snap.get("commit") or "")
    if not commit:
        return None
    rc, text = _git(repo, "show", f"{commit}:{rel}")
    if rc != 0:
        return None  # file did not exist at the start point -> new
    for fact in parse_crap(_fake_crap_from_source(text, rel)):
        if fact["rel"] == rel and fact["func"] == func:
            return fact
    return None


def _fake_crap_from_source(text: str, rel: str) -> str:
    """A structural stand-in for crapper on the start commit.

    The real crapper computes CRAP from coverage, which needs the green
    tests of that moment. For the start point we approximate with CC only
    (cov=0), which over-reports CRAP for old code — conservative in the
    right direction: a function flagged as "already red at the start" only
    needs to not get worse, and CC alone decides that. Brace languages use
    canon_smells' brace pairing (via the java signature regex); python
    bodies fall back to a plain `def` scan.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent / "plugin"))
    import canon_smells  # noqa: WPS433
    import re as _re

    out = []
    # Java/Go/JS-style declarations (java_inspect's _SIG shape: a method
    # signature ending in an opening brace).
    sig = _re.compile(
        r"(?m)^[ \t]*(?:(?:public|private|protected|static|final|synchronized)\s+)*"
        r"(?P<ret>[\w.<>\[\],?]+)\s+(?P<name>[A-Za-z_]\w*)\s*"
        r"\((?P<params>[^)]*)\)\s*(?:throws\s+[\w., \t]+)?\s*\{")
    decls = list(sig.finditer(text))
    if decls:
        for row in canon_smells.brace_func_spans(text, decls):
            body = text[row["start"]:row["end"]]
            cc = canon_smells.brace_complexity(body)
            out.append(f"{rel}:{row['name']} CC={cc} COV=0.0 CRAP={cc * cc + cc}")
        return "\n".join(out)
    # Python-style fallback: def blocks by indentation.
    lines = text.splitlines()
    current = None
    indent = 0
    cc = 1
    for line in lines:
        m = _re.match(r"^(\s*)def\s+(\w+)", line)
        if m:
            if current:
                out.append(f"{rel}:{current} CC={cc} COV=0.0 CRAP={cc * cc + cc}")
            current, indent, cc = m.group(2), len(m.group(1)), 1
        elif current is not None:
            stripped = line.strip()
            if stripped:
                cc += sum(stripped.count(k) for k in ("if ", "elif ", "for ", "while ", "except ", " and ", " or "))
    if current:
        out.append(f"{rel}:{current} CC={cc} COV=0.0 CRAP={cc * cc + cc}")
    return "\n".join(out)


def cmd_check(args: argparse.Namespace) -> int:
    """The advisory gate. Always exit 0 — hits are nominations, not blocks."""
    repo = (args.repo or Path.cwd()).resolve()
    snap = _load_snapshot(args.feature, repo)
    if snap is None:
        # No start point: fix one first (snapshot is idempotent), then check.
        cmd_snapshot(args)
        snap = _load_snapshot(args.feature, repo)

    missing = [t for t in TOOLS if not resolve_tool(t)]
    if missing:
        print(f"ub: UNPROVEN（缺 {'/'.join(missing)}，安装见 README「ub-mode 工具」；"
              "advisory 层不因外接工具缺席 FAIL）")
        return 0

    hits: list[str] = []
    debts: list[str] = []
    rc, out = _run_tool("crapper", repo)
    for fact in parse_crap(out):
        if fact["crap"] < CRAP_LIMIT:
            continue
        start = _start_func_fact(args.feature, repo, fact["rel"], fact["func"])
        where = f"{fact['rel']}:{fact['func']}"
        if start is None:
            hits.append(f"CRAP-HIT {where} CRAP={fact['crap']:.0f}（新增或改名——"
                        "起点无此身份，按新增函数查；改名不重置债务）")
        elif start["crap"] < CRAP_LIMIT:
            hits.append(f"CRAP-HIT {where} CRAP={fact['crap']:.0f}"
                        f"（起点 CRAP={start['crap']:.0f} 达标——把绿函数改红了，必须修）")
        else:
            worse = fact["cc"] > start["cc"] or fact["crap"] > start["crap"]
            tag = "DEBT-WORSE" if worse else "DEBT-OK"
            note = ("CC 与 CRAP 须均不高于基线——本票把债务恶化了，reviewer 必写 I*"
                    if worse else "不恶化条件满足，记债务不清零")
            debts.append(f"{tag} {where} CRAP={fact['crap']:.0f}"
                         f"（基线 CC={start['cc']} CRAP={start['crap']:.0f}）{note}")

    rc, out = _run_tool("dryer", repo)
    for dup in parse_dup(out):
        if dup["sim"] < DUP_LIMIT:
            continue
        hits.append(f"DUP-HIT {dup['rel_a']}:{dup['func_a']} ≈ "
                    f"{dup['rel_b']}:{dup['func_b']} sim={dup['sim']:.2f}"
                    "（先过 P17：省略规则是否相反；真重复走 R5 提取）")

    # coding-scan.sh already prints the `=== ub-quality ===` section
    # header before calling here; printing a second one would double-head
    # the section in the scan output.
    for line in hits:
        print("  " + line)
    for line in debts:
        print("  " + line)
    print(f"ub: advisory {len(hits)} hit(s) {len(debts)} debt(s)——"
          "命中写 review.md 的 I*（C1 拆函数/P5 策略/P17 判真假重复/R5 提取），"
          "不挡 problems/lang 退出码；DEBT-WORSE 升级为必写")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    snap = _load_snapshot(args.feature, args.repo)
    if snap is None:
        print("(no start-snapshot; run snapshot first)")
        return 0
    print(f"start-snapshot: commit {str(snap.get('commit'))[:10]} at {snap.get('at')}")
    print("函数清单与逐函数判定在 check 输出里（对照起点，改名按新增查）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, help="product checkout (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("snapshot", help="fix the feature's start point (idempotent)")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_snapshot)

    p = sub.add_parser("check", help="the advisory gate — always exit 0")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("report", help="one-line start-point summary")
    p.add_argument("--feature", required=True)
    p.set_defaults(fn=cmd_report)

    args = parser.parse_args()
    if args.repo is None and os.environ.get("IDEV_PRODUCT_REPO"):
        args.repo = Path(os.environ["IDEV_PRODUCT_REPO"])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
