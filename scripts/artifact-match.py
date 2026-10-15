#!/usr/bin/env python3
"""Does the source I am reading match the artifact that is actually running?

    artifact-match.py --artifact PATH [--repo DIR]
    artifact-match.py --artifact PATH --symbol com.x.Y#method

conventions/evidence.md requires naming the artifact before drawing a
conclusion — 「先认环境/产物」, and the reject-list for ops is explicit:
未确认环境/产物就写结论. But the only thing the agents could actually read
was the source tree. So "认产物" was a declaration, not a check: an agent
could name a jar and then reason entirely from a working copy three commits
ahead of it.

That is the failure this closes. It extracts the build identity the artifact
carries about itself and compares it with the checkout:

    git.properties           spring-boot git-commit-id-plugin — the best case,
                             it names the exact commit
    META-INF/MANIFEST.MF     Implementation-Version, Build-Jdk, Build-Time
    class file timestamps    entry mtimes, when nothing better is present

Verdict is one of:

    MATCH      the artifact names a commit, and it is this checkout's HEAD
    AHEAD      the checkout moved past the artifact — reading源码 here
               describes code that is NOT running
    UNKNOWN    the artifact carries no usable identity

**UNKNOWN is not a pass.** It means this check cannot answer, so the
reasoning has to stay inside what the artifact itself shows. Saying
"probably the same" is exactly the 假想臆断 the reject-list forbids.

Supported today: jar / war / zip-shaped artifacts (JVM), and plain
directories. Other shapes report UNKNOWN with the reason, rather than
pretending.

Exit: 0 MATCH, 1 AHEAD or a mismatch worth stopping for, 2 cannot read.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ZIP_SUFFIXES = (".jar", ".war", ".ear", ".zip", ".nar")
# Paths that cannot be the reason a built artifact behaves differently.
# Ticket files and docs change constantly; leaving them in the suspect list
# buries the one file that actually shipped.
NOT_SHIPPED = re.compile(
    # Ticket and tooling directories: these are never inside a build.
    r"(?:^|/)(?:\.idev|\.github|\.vscode|\.idea|\.git)/"
    # Top-level docs directories and the usual root documents.
    r"|^docs?/|(?:^|/)(?:README|CHANGELOG|LICENSE|CONTRIBUTING)[^/]*$"
    # Test trees. A test change cannot alter what the shipped code does.
    r"|(?:^|/)(?:e2e|src/test|tests?)/"
    # Lock files record how the build resolved, not what it does.
    r"|(?:^|/)[\w.-]*lock(?:\.\w+)?$")
# Deliberately NOT filtered by suffix: src/main/resources/messages.txt and
# src/config.json DO get packaged. Filtering by extension would hide the
# real culprit, which is worse than the noise it removes — so only
# locations that cannot be in a build are dropped.(?:e2e|test|tests|spec)/")
GIT_PROPS = ("git.properties", "BOOT-INF/classes/git.properties", "WEB-INF/classes/git.properties")
COMMIT_KEYS = ("git.commit.id.full", "git.commit.id", "git.commit.id.abbrev")


def run(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=30,
                           cwd=str(cwd) if cwd else None)
        return p.returncode, (p.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def read_props(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def read_manifest(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


class Identity:
    """What the artifact says about its own build."""

    def __init__(self) -> None:
        self.commit = ""
        self.branch = ""
        self.build_time = ""
        self.version = ""
        self.source = ""
        self.newest_entry: dt.datetime | None = None
        self.notes: list[str] = []


def identify_zip(path: Path) -> Identity:
    ident = Identity()
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        ident.notes.append(f"打不开:{exc}")
        return ident

    with zf:
        names = set(zf.namelist())

        for cand in GIT_PROPS:
            if cand in names:
                props = read_props(zf.read(cand).decode("utf-8", "replace"))
                for key in COMMIT_KEYS:
                    if props.get(key):
                        ident.commit = props[key]
                        break
                ident.branch = props.get("git.branch", "")
                ident.build_time = props.get("git.build.time", "")
                ident.source = cand
                break

        if "META-INF/MANIFEST.MF" in names:
            mf = read_manifest(zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace"))
            ident.version = mf.get("Implementation-Version") or mf.get("Bundle-Version") or ""
            if not ident.build_time:
                ident.build_time = mf.get("Build-Time") or mf.get("Built-Date") or ""
            if not ident.commit:
                # Some builds stamp the commit into the manifest instead.
                for k in ("Git-Commit", "SCM-Revision", "Implementation-Build"):
                    if mf.get(k):
                        ident.commit = mf[k]
                        ident.source = f"MANIFEST.MF:{k}"
                        break
            if not ident.source:
                ident.source = "META-INF/MANIFEST.MF"

        # Newest class timestamp — a floor on when this was built.
        newest = None
        for info in zf.infolist():
            if info.filename.endswith((".class", ".js", ".so")):
                ts = dt.datetime(*info.date_time)
                if newest is None or ts > newest:
                    newest = ts
        ident.newest_entry = newest
    return ident


def identify(path: Path) -> Identity:
    if path.is_dir():
        ident = Identity()
        for cand in ("git.properties", "classes/git.properties"):
            f = path / cand
            if f.is_file():
                props = read_props(f.read_text(encoding="utf-8", errors="replace"))
                for key in COMMIT_KEYS:
                    if props.get(key):
                        ident.commit = props[key]
                        break
                ident.branch = props.get("git.branch", "")
                ident.source = str(f)
                break
        if not ident.source:
            ident.notes.append("目录里没有 git.properties")
        return ident
    if path.suffix.lower() in ZIP_SUFFIXES:
        return identify_zip(path)
    ident = Identity()
    ident.notes.append(f"不支持的产物形态 {path.suffix or '(无后缀)'};"
                       "目前支持 jar/war/ear/zip/nar 与目录")
    return ident


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--artifact", required=True, type=Path, help="the running artifact")
    parser.add_argument("--repo", type=Path, help="source checkout (default: cwd)")
    parser.add_argument("--symbol", help="also show this symbol's recent history")
    args = parser.parse_args()

    art = args.artifact.expanduser()
    if not art.exists():
        print(f"BLOCKED no such artifact: {art}", file=sys.stderr)
        return 2
    repo = (args.repo or Path(os.environ.get("IDEV_PRODUCT_REPO") or Path.cwd())).resolve()

    ident = identify(art)
    rc, head = run(["git", "rev-parse", "HEAD"], repo)
    head = head if rc == 0 else ""
    _, dirty_raw = run(["git", "status", "--porcelain"], repo)
    # Exclude the artifact itself and untracked files: a jar sitting in the
    # tree is not a source change, and counting it would turn a真 MATCH into
    # a false AHEAD. Only tracked modifications mean "源码 != that commit".
    dirty_lines = []
    for line in dirty_raw.splitlines():
        if line.startswith("??"):
            continue
        name = line[3:].strip()
        try:
            if (repo / name).resolve() == art.resolve():
                continue
        except OSError:
            pass
        dirty_lines.append(line)
    dirty = "\n".join(dirty_lines)

    print(f"# artifact-match")
    print(f"产物: {art}")
    print(f"源码: {repo}")
    print()
    print("## 产物自述")
    if ident.commit:
        print(f"  commit      {ident.commit}   (来自 {ident.source})")
    if ident.branch:
        print(f"  branch      {ident.branch}")
    if ident.version:
        print(f"  version     {ident.version}")
    if ident.build_time:
        print(f"  build time  {ident.build_time}")
    if ident.newest_entry:
        print(f"  最新 class  {ident.newest_entry.isoformat(sep=' ')}  (构建时间下界)")
    for n in ident.notes:
        print(f"  note        {n}")
    if not (ident.commit or ident.version or ident.build_time or ident.newest_entry):
        print("  (产物没有携带任何可用的构建身份)")
    print()

    print("## 源码侧")
    print(f"  HEAD        {head or 'n/a (不是 git checkout?)'}")
    if dirty:
        print(f"  工作区      有未提交改动({len(dirty.splitlines())} 个文件)")
    print()

    verdict = "UNKNOWN"
    detail: list[str] = []

    if ident.commit and head:
        short = ident.commit[:7]
        if head.startswith(ident.commit) or ident.commit.startswith(head[:7]):
            verdict = "MATCH"
            detail.append("产物点名的 commit 就是当前 HEAD")
        else:
            rc_m, _ = run(["git", "merge-base", "--is-ancestor", ident.commit, head], repo)
            rc_known, _ = run(["git", "cat-file", "-e", f"{ident.commit}^{{commit}}"], repo)
            if rc_known != 0:
                verdict = "UNKNOWN"
                detail.append(f"产物点名的 {short} 在这个 checkout 里找不到 —— "
                              "不是同一个仓,或该提交没 fetch 下来")
            elif rc_m == 0:
                verdict = "AHEAD"
                rc_c, count = run(["git", "rev-list", "--count", f"{ident.commit}..{head}"], repo)
                n = count if rc_c == 0 else "?"
                detail.append(f"源码比产物新 {n} 个提交 —— "
                              f"**你在这里读到的代码不一定是线上跑的那一份**")
                rc_f, files = run(
                    ["git", "diff", "--name-only", f"{ident.commit}..{head}"], repo)
                if rc_f == 0 and files:
                    changed = files.splitlines()
                    # Only what could actually be inside the artifact. A
                    # ticket file changing between two builds explains
                    # nothing about how the running code behaves.
                    shipped = [f for f in changed if not NOT_SHIPPED.search(f)]
                    skipped = len(changed) - len(shipped)
                    if shipped:
                        detail.append(
                            f"这期间动过 {len(shipped)} 个会进产物的文件;排查时优先怀疑它们:")
                        for f in shipped[:12]:
                            detail.append(f"    {f}")
                        if len(shipped) > 12:
                            detail.append(f"    … 另 {len(shipped) - 12} 个")
                    else:
                        detail.append(
                            f"这期间 {len(changed)} 个文件改动都不进产物(票据 / 文档 / 测试)—— "
                            "产物行为的差异不在源码这一侧,查构建或部署")
                    if skipped:
                        detail.append(f"    (另有 {skipped} 个票据 / 文档 / 测试改动,已略去)")
            else:
                verdict = "AHEAD"
                detail.append(f"产物的 {short} 不在当前分支的历史里 —— "
                              "产物可能来自另一个分支")
    elif ident.newest_entry and head:
        rc_t, ts = run(["git", "log", "-1", "--format=%cI", head], repo)
        if rc_t == 0 and ts:
            try:
                head_time = dt.datetime.fromisoformat(ts).replace(tzinfo=None)
                if head_time > ident.newest_entry:
                    verdict = "AHEAD"
                    detail.append(
                        f"HEAD 的提交时间({head_time.date()})晚于产物里最新的 class"
                        f"({ident.newest_entry.date()})—— 源码大概率比产物新")
                else:
                    detail.append("时间戳上源码不比产物新,但这不是 commit 级的证据")
            except ValueError:
                pass
        detail.append("产物没有 git.properties,只能用时间戳 —— "
                      "建议构建时加 git-commit-id-plugin,让产物自己说清它是哪个 commit")
    else:
        detail.append("无法比对:产物没有可用身份,或源码不是 git checkout")

    if dirty and verdict == "MATCH":
        verdict = "AHEAD"
        detail.append("工作区有未提交改动 —— 你读到的源码已经不等于那个 commit")

    print(f"## 判定: {verdict}")
    print()
    for d in detail:
        print(f"  {d}")
    print()

    if args.symbol and head:
        print(f"## {args.symbol} 的近期改动")
        pat = args.symbol.split("#")[0].replace(".", "/")
        rc_s, out = run(["git", "log", "-5", "--format=%h %cs %s", "--", f"*{pat}*"], repo)
        print("  " + ("\n  ".join(out.splitlines()) if rc_s == 0 and out else "(没找到相关提交)"))
        print()

    if verdict == "MATCH":
        print("源码与产物同源:读源码得到的逻辑就是运行时的逻辑。")
        print("(仍要用例证明它是用户那条现象的根因 —— evidence.md 的闭环没变。)")
        return 0

    if verdict == "AHEAD":
        print("**源码与产物不同源。** 继续排查前选一条:")
        if ident.commit:
            print("  1. 把 checkout 切到产物那个 commit,再读代码")
            print(f"     git -C {repo} checkout {ident.commit[:12]}")
        else:
            # Telling someone to check out "<the artifact's commit>" when the
            # artifact never carried one is not an option, it is a shrug.
            print("  1. 找到构建这份产物的那次提交,再读代码。产物没带 commit,")
            print("     只能靠构建记录 / CI 日志 / 制品库的构建号去反查:")
            when = ident.newest_entry.date().isoformat() if ident.newest_entry else "构建日"
            print(f"     git -C {repo} log --before='{when} 23:59' -5 --format='%h %cs %s'")
        print("  2. 换一份与源码同源的产物,重新部署后复现")
        print("  3. 两者都不动,但结论只能基于产物自身的可观察行为(日志 / 响应 / 抓包)")
        print()
        print("不要用当前源码的逻辑解释线上现象 —— 那是 evidence.md 禁的")
        print("「未确认用户看的是哪份产物就下结论」。")
        return 1

    print("**无法确认同源。** 这不是放行:")
    print("  - 不要假设「应该是同一份」—— 那是假想臆断")
    print("  - 要么让产物携带 commit(构建时加 git-commit-id-plugin),")
    print("    要么把结论限制在产物自身的可观察行为之内")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
