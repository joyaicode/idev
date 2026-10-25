#!/usr/bin/env bash
# Enhanced coding-standards scan planner for idev code stage.
# Detects stack, points at installed review Skills, and lists local tool commands.
# Does NOT invent P/C codes — Agent maps findings back to conventions/coding.md.
set -euo pipefail

REPO="${1:-.}"
REPO="$(cd "$REPO" && pwd)"
SKILLS_AGENTS="${HOME}/.agents/skills"
SKILLS_CURSOR="${HOME}/.cursor/skills"
skill() {
  local name="$1"
  if [ -d "${SKILLS_CURSOR}/${name}" ]; then echo "${SKILLS_CURSOR}/${name}"
  elif [ -d "${SKILLS_AGENTS}/${name}" ]; then echo "${SKILLS_AGENTS}/${name}"
  else echo ""
  fi
}

echo "=== idev coding-scan ==="
echo "repo: $REPO"

has_java=0 has_vue=0 has_go=0 has_ts=0
[ -f "$REPO/pom.xml" ] || [ -f "$REPO/build.gradle" ] || [ -f "$REPO/build.gradle.kts" ] && has_java=1
# monorepo modules
# node_modules 属依赖产物：里面的构建/包文件不作栈证据；prune 同时避免 find|head 触发 SIGPIPE(141)。
find "$REPO" -maxdepth 3 \( -name node_modules -prune \) -o \( -name pom.xml -o -name build.gradle -o -name build.gradle.kts \) -print 2>/dev/null | head -1 | grep -q . && has_java=1
find "$REPO" -maxdepth 6 \( -name node_modules -prune \) -o \( -name 'package.json' \) -print 2>/dev/null | while read -r pj; do
  if grep -qE '"vue"|"@vue/' "$pj" 2>/dev/null; then echo VUE; fi
  if grep -qE '"typescript"' "$pj" 2>/dev/null; then echo TS; fi
done | sort -u > /tmp/idev-coding-scan-stacks.$$
grep -q VUE /tmp/idev-coding-scan-stacks.$$ 2>/dev/null && has_vue=1
grep -q TS /tmp/idev-coding-scan-stacks.$$ 2>/dev/null && has_ts=1
rm -f /tmp/idev-coding-scan-stacks.$$
find "$REPO" -maxdepth 3 \( -name node_modules -prune \) -o \( -name go.mod \) -print 2>/dev/null | head -1 | grep -q . && has_go=1

# Java language level hint
java_level="unknown"
if [ "$has_java" = 1 ]; then
  if grep -RqsE 'maven.compiler.(source|target|release)>?\s*8|java.version>\s*1\.8|compiler.source>\s*8' \
      "$REPO/pom.xml" "$REPO"/*/pom.xml 2>/dev/null; then
    java_level="8"
  elif grep -RqsE 'maven.compiler.(source|target|release)>?\s*17|java.version>\s*17' \
      "$REPO/pom.xml" "$REPO"/*/pom.xml 2>/dev/null; then
    java_level="17"
  elif [ -f "$REPO/qodana.yaml" ] && grep -q 'projectJDK:.*"17"' "$REPO/qodana.yaml" 2>/dev/null; then
    # tooling only — compiler 优先；Boot 2.6/2.7 且未写 compiler 时按 8
    if grep -qs 'spring-boot-starter-parent' "$REPO/pom.xml" 2>/dev/null; then
      if grep -qsE '2\.7\.|2\.6\.' "$REPO/pom.xml"; then java_level="8"; fi
    fi
  fi
fi

echo "stacks: java=$has_java(level=$java_level) vue=$has_vue go=$has_go ts=$has_ts"

CR="$(skill code-review-skill)"
CQ="$(skill code-review-and-quality)"
CS="$(skill code-simplification)"
SEC="$(skill security-and-hardening)"
echo "skills:"
echo "  code-review-skill: ${CR:-MISSING}"
echo "  code-review-and-quality: ${CQ:-MISSING}"
echo "  code-simplification: ${CS:-MISSING}"
echo "  security-and-hardening: ${SEC:-MISSING}"

echo "=== product code pages ==="
ROOT="$(cd "$(dirname "$0")" && pwd)"
# The guide paths below are printed for a person or an agent to open, so they
# have to be the paths that actually exist on this machine rather than the
# conventional alias — which may not be installed in a fresh checkout.
IDEV="$(python3 "${ROOT}/lib/roots.py")"
ctx=(python3 "$ROOT/session-context.py" --repo "$REPO" --stage code)
if [ -n "${IDEV_PRODUCT:-}" ]; then
  ctx+=(--product "$IDEV_PRODUCT")
fi
"${ctx[@]}"
lint="$(python3 "$ROOT/session-context.py" --repo "$REPO" --print lint || true)"
if [ -n "$lint" ]; then
  echo "lint: $lint"
else
  echo "lint: ask — set .idev/workflow-defaults.yaml commands.lint_fix"
fi

echo "=== open these guides (then map hits to P#/C#/R#) ==="
echo "1) ALWAYS: ${IDEV}/conventions/coding.md  (§0)"
echo "   tables: ${IDEV}/conventions/coding-tables.md  (§1/§2/§3)"
[ -n "$CQ" ] && echo "2) five-axis: $CQ/SKILL.md"
[ -n "$CR" ] && echo "3) checklist: $CR/assets/review-checklist.md"
[ -n "$SEC" ] && echo "4) security: $SEC/SKILL.md"
[ -n "$CS" ] && echo "5) simplify (after green): $CS/SKILL.md"

if [ "$has_java" = 1 ]; then
  echo "=== Java stack ==="
  echo "  idev: ${IDEV}/conventions/java.md"
  if [ -n "$CR" ]; then
    if [ "$java_level" = "8" ] || [ "$java_level" = "unknown" ]; then
      echo "  guide: $CR/reference/java8.md"
    else
      echo "  guide: $CR/reference/java.md"
    fi
    echo "  bugs:   $CR/reference/common-bugs-checklist.md"
    echo "  secure: $CR/reference/security-review-guide.md"
  fi
  echo "  plinth: 124-java-secure-coding, 123-java-design-patterns (optional depth)"
  echo "  tools:  problems-scan.sh（插件 scripts/plugin/java_inspect.py，不安装 IntelliJ，不安装 JDK）"
  echo "  hygiene: ${ROOT}/lib/java_hygiene.py  (正则子集，先于总则；0 不是 Problems 已空)"
  python3 "${ROOT}/lib/java_hygiene.py" --repo "$REPO"
  echo "  problems: ${ROOT}/problems-scan.sh"
  [ -f "$REPO/qodana.yaml" ] && echo "  found qodana.yaml"
  # 收进变量再判空：grep -l|head 管道在多匹配时会因 pipefail 的 SIGPIPE(141) 令 if 恒假。
  pom_tools="$(find "$REPO" -maxdepth 3 -name pom.xml -exec grep -l 'checkstyle\|spotbugs\|pmd\|spotless' {} + 2>/dev/null | head -1 || true)"
  if [ -n "$pom_tools" ]; then
    echo "  found checkstyle/pmd/spotbugs/spotless in a pom — run those too"
  fi
fi

if [ "$has_vue" = 1 ] || [ "$has_ts" = 1 ]; then
  echo "=== Frontend ==="
  echo "  idev: ${IDEV}/conventions/coding.md"
  [ -n "$CR" ] && echo "  guide: $CR/reference/vue.md"
  [ -n "$CR" ] && [ "$has_ts" = 1 ] && echo "  guide: $CR/reference/typescript.md"
  echo "  tools: lang-scan.sh (scripts/plugin/js_inspect.py；不安装 eslint，不安装 Node，不下载)"
fi

if [ "$has_go" = 1 ]; then
  echo "=== Go ==="
  [ -n "$CR" ] && echo "  guide: $CR/reference/go.md"
  echo "  tools: lang-scan.sh (scripts/plugin 里的 python/go/shell/js 插件；不安装工具链，不下载)"
fi

echo "=== 架构范式 ==="
echo "  idev: ${IDEV}/conventions/canon.md  (T1-T12 念头表 / A1-A8 出门)"
echo "  涉及加层/拆分/缓存/队列/重写 → 按 canon §1 协议扫 §2 信号，review.md 按 §7 模板记 T#"

echo "=== size (coding-tables §2.4) ==="
if git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "  diff:"
  git -C "$REPO" diff --stat HEAD -- . \
    ':(exclude)node_modules' ':(exclude)target' ':(exclude)dist' || true
  echo "  longest tracked source files:"
  REPO="$REPO" git -C "$REPO" ls-files -z -- '*.java' '*.go' '*.vue' '*.ts' '*.tsx' '*.py' '*.js' \
    | REPO="$REPO" python3 -c '
import os, sys
repo = os.environ["REPO"]
rows = []
for raw in sys.stdin.buffer.read().split(b"\0"):
    if not raw:
        continue
    rel = raw.decode()
    path = os.path.join(repo, rel)
    try:
        with open(path, "rb") as fh:
            n = sum(1 for _ in fh)
    except OSError:
        continue
    rows.append((n, rel))
rows.sort(reverse=True)
if not rows:
    print("  (none)")
for n, rel in rows[:5]:
    print("  %6d %s" % (n, rel))
'
else
  echo "  git: none"
fi
run_configured_scanner() {
  local wf flags name ran=0
  wf="$(grep -Rls 'super-linter' "$REPO/.github" 2>/dev/null | head -1 || true)"
  if [ -z "$wf" ]; then
    echo "  scanner: no super-linter config — run the stack tools above if the repo already has them"
    return
  fi
  echo "  scanner: super-linter config ${wf#"$REPO"/}"
  SL="$(skill super-linter)"
  if [ -n "$SL" ]; then
    echo "  skill: $SL/SKILL.md"
  else
    echo "  skill: MISSING ~/.cursor/skills/super-linter (install companion)"
  fi
  flags="$(WF="$wf" python3 - <<'PY'
import os, re
text = open(os.environ["WF"], encoding="utf-8", errors="replace").read()
for match in re.finditer(r"(?m)^[ \t#-]*(VALIDATE_[A-Z0-9_]+)[ \t]*:[ \t]*[\"']?true\b", text):
    print(match.group(1))
PY
)"
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    case "$name" in
      VALIDATE_PYTHON|VALIDATE_PYTHON_RUFF|VALIDATE_PYTHON_PYLINT|VALIDATE_PYTHON_FLAKE8|VALIDATE_PYTHON_ISORT|VALIDATE_PYTHON_BLACK)
        echo "  scanner run: python3 compile ($name)"
        if ! python3 -m compileall -q -x 'node_modules|target|dist|.git' "$REPO"; then
          echo "  scanner result: python compile failed"
        fi
        ran=1
        ;;
      VALIDATE_GO|VALIDATE_GO_MODULES)
        if command -v golangci-lint >/dev/null 2>&1; then
          echo "  scanner run: golangci-lint ($name)"
          if ! (cd "$REPO" && golangci-lint run --timeout 2m); then
            echo "  scanner result: golangci-lint failed"
          fi
          ran=1
        else
          echo "  scanner skip: golangci-lint is not installed ($name); not downloading super-linter"
        fi
        ;;
      VALIDATE_JAVASCRIPT_ES|VALIDATE_TYPESCRIPT_ES|VALIDATE_JAVASCRIPT_STANDARD)
        if command -v eslint >/dev/null 2>&1; then
          echo "  scanner run: eslint ($name)"
          if ! (cd "$REPO" && eslint .); then
            echo "  scanner result: eslint failed"
          fi
          ran=1
        else
          echo "  scanner skip: eslint is not installed ($name); not downloading super-linter"
        fi
        ;;
    esac
  done <<< "$flags"
  if [ "$ran" = 0 ]; then
    echo "  scanner: config present; no matching local tool ran; not downloading super-linter"
  fi
}
run_configured_scanner

problems_ran=0
problems_rc=0
if [ "$has_java" = 1 ]; then
  echo "=== problems ==="
  set +e
  bash "${ROOT}/problems-scan.sh" "$REPO"
  problems_rc=$?
  set -e
  problems_ran=1
fi

echo "=== lang ==="
lang_rc=0
set +e
bash "${ROOT}/lang-scan.sh" "$REPO"
lang_rc=$?
set -e

echo "=== review.md must record ==="
echo "  - 审查者: idev-reviewer"
echo "  - 文件与行数: 触及 N 个文件，新增 M，最长 L 行"
echo "  - 场景命中 / 气味命中 / 纠正 (P# C#)"
echo "  - 五轴: 正确性/可读性/架构/安全/性能 — 各写 过 或 命中摘要"
echo "  - 栈指南: java8|java|vue|go|… （本轮打开的 guide 名）"
echo "  - 增强扫描: coding-scan + guides 已跑 / 未跑"
echo "  - 扫描: 仓内已有规范扫描 — 干净 / 本仓无规范扫描器"
echo "  - problems: 插件规范项 0 / 仍有发现 / UNPROVEN（插件文件不在）"
echo "  - lang: python/go/shell/js 插件 convention 0 / 仍有发现 / UNPROVEN（插件文件不在）"
echo "=== done ==="
final=0
if [ "$problems_ran" = 1 ] && [ "$problems_rc" -eq 1 ]; then
  final=1
fi
if [ "$lang_rc" -eq 1 ]; then
  final=1
fi
if [ "$final" -ne 1 ]; then
  if [ "$problems_ran" = 1 ] && [ "$problems_rc" -eq 2 ]; then
    final=2
  fi
  if [ "$lang_rc" -eq 2 ]; then
    final=2
  fi
fi
if [ "$final" -ne 0 ]; then
  exit "$final"
fi
