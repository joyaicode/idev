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
find "$REPO" -maxdepth 3 \( -name pom.xml -o -name build.gradle -o -name build.gradle.kts \) 2>/dev/null | head -1 | grep -q . && has_java=1
find "$REPO" -maxdepth 6 \( -name 'package.json' \) 2>/dev/null | head -5 | while read -r pj; do
  if grep -qE '"vue"|"@vue/' "$pj" 2>/dev/null; then echo VUE; fi
  if grep -qE '"typescript"' "$pj" 2>/dev/null; then echo TS; fi
done | sort -u > /tmp/idev-coding-scan-stacks.$$
grep -q VUE /tmp/idev-coding-scan-stacks.$$ 2>/dev/null && has_vue=1
grep -q TS /tmp/idev-coding-scan-stacks.$$ 2>/dev/null && has_ts=1
rm -f /tmp/idev-coding-scan-stacks.$$
find "$REPO" -maxdepth 3 \( -name go.mod \) 2>/dev/null | head -1 | grep -q . && has_go=1

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
    if grep -Rqs 'spring-boot-starter-parent' "$REPO/pom.xml" 2>/dev/null | head -1 | grep -q .; then
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
  echo "  tools:  IDE Problems / qodana.starter"
  [ -f "$REPO/qodana.yaml" ] && echo "  found qodana.yaml"
  if find "$REPO" -maxdepth 3 -name pom.xml 2>/dev/null | xargs grep -l 'checkstyle\|spotbugs\|pmd\|spotless' 2>/dev/null | head -3 | grep -q .; then
    echo "  found checkstyle/pmd/spotbugs/spotless in a pom — run those too"
  fi
fi

if [ "$has_vue" = 1 ] || [ "$has_ts" = 1 ]; then
  echo "=== Frontend ==="
  echo "  idev: ${IDEV}/conventions/coding.md"
  [ -n "$CR" ] && echo "  guide: $CR/reference/vue.md"
  [ -n "$CR" ] && [ "$has_ts" = 1 ] && echo "  guide: $CR/reference/typescript.md"
fi

if [ "$has_go" = 1 ]; then
  echo "=== Go ==="
  [ -n "$CR" ] && echo "  guide: $CR/reference/go.md"
  echo "  tools: go test ./... ; golangci-lint run (if installed)"
fi

echo "=== 架构范式 ==="
echo "  idev: ${IDEV}/conventions/canon.md  (T1-T12 念头表 / A1-A8 出门)"
echo "  涉及加层/拆分/缓存/队列/重写 → 按 canon §1 协议扫 §2 信号，review.md 按 §7 模板记 T#"

echo "=== review.md must record ==="
echo "  - 场景命中 / 气味命中 / 纠正 (P# C#)"
echo "  - 五轴: 正确性/可读性/架构/安全/性能 — 各写 过 或 命中摘要"
echo "  - 栈指南: java8|java|vue|go|… （本轮打开的 guide 名）"
echo "  - 增强扫描: coding-scan + guides 已跑 / 未跑"
echo "  - 扫描: Problems/Qodana 或 lint-fix — 干净/未跑"
echo "=== done ==="
