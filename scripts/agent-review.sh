#!/usr/bin/env bash
# Periodic review of the delegation layer. Drafts only — never lands.
#
#   agent-review.sh [--repo <product checkout>] [--days N] [--dry-run] [--out DIR]
#
# Mirrors the kernel's evolve-review.sh, deliberately:
#   - reads only: delegation records, metrics, existing proposals
#   - writes a DRAFT proposal when there is a hard signal, a receipt when not
#   - writes signal= to a status file so a scheduled job can stay quiet
#   - NEVER edits a definition, the registry, or state/ledger.yaml
#
# This closes the last gap in the self-evolution loop: agent-metrics knows
# when a signal exists, but nothing was turning that into the proposal the
# kernel's propose -> grill -> confirm -> land path expects.
#
# Hard signal (same two rules as references/agents-evolve.md section 6):
#   - one agent accumulated check_fail >= 2
#   - one kind accumulated retried + rejected >= 2
#   - any no-signoff-write failure (an agent claimed it signed)
#
# What it does NOT decide: what to change. That is for the person and the
# grill. The draft carries evidence and an empty decision section on purpose.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TARGET="$PWD"
DAYS=7
DRY=0
OUT="${REPO}/state"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) TARGET="$2"; shift 2 ;;
    --days) DAYS="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "FAIL unknown flag: $1" >&2; exit 1 ;;
  esac
done

if [ ! -d "$TARGET" ]; then
  echo "FAIL no such checkout: $TARGET" >&2
  exit 2
fi

# --out exists so a test run can land its drafts somewhere disposable.
# Without it, smoke would write proposals into the real state/proposals.
REVIEWS="${OUT}/reviews"
PROPOSALS="${OUT}/proposals"
LATEST="${REVIEWS}/agent-review-latest.md"
STATUS="${REVIEWS}/agent-review-status.env"
STAMP="$(date +%Y%m%d)"
NOW="$(date +%Y-%m-%dT%H:%M:%S%z)"

# Do NOT swallow a metrics failure. With `|| true` a broken script reports
# signal=no, which reads as "all clear" — the one wrong answer a review loop
# must never give. A tool failure is a failure, not quiet.
if ! metrics="$(python3 "${REPO}/scripts/agent-metrics.py" --repo "$TARGET" --days "$DAYS" 2>&1)"; then
  echo "FAIL agent-metrics failed; refusing to report a verdict" >&2
  printf '%s\n' "$metrics" >&2
  exit 2
fi
if ! signal_out="$(python3 "${REPO}/scripts/agent-metrics.py" --repo "$TARGET" --days "$DAYS" --signal 2>&1)"; then
  echo "FAIL agent-metrics --signal failed; refusing to report a verdict" >&2
  printf '%s\n' "$signal_out" >&2
  exit 2
fi

if printf '%s' "$signal_out" | grep -q '^signal=yes'; then
  SIGNAL=yes
elif printf '%s' "$signal_out" | grep -q '^signal=no'; then
  SIGNAL=no
else
  # No verdict line at all means the output shape changed under us.
  echo "FAIL agent-metrics --signal printed no signal= line" >&2
  printf '%s\n' "$signal_out" >&2
  exit 2
fi

hits="$(printf '%s\n' "$signal_out" | grep '^HIT ' || true)"

# Stale drafts count as a signal too, same as the kernel does: a proposal
# that never gets grilled is its own problem.
stale=""
if [ -d "$PROPOSALS" ]; then
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    if grep -qi '^status:[[:space:]]*draft' "$p" 2>/dev/null; then
      stale="${stale}\n- $(basename "$p")"
    fi
  done <<EOF
$(find "$PROPOSALS" -name '*.md' -mtime +14 2>/dev/null || true)
EOF
fi
if [ -n "$stale" ]; then
  SIGNAL=yes
fi

report="$(cat <<EOF
# agent-review  ${NOW}

产品仓: ${TARGET}
窗口: 近 ${DAYS} 天
signal=${SIGNAL}

## 信号

$( [ -n "$hits" ] && printf '%s\n' "$hits" || printf '(无 nudge 命中)\n' )
$( [ -n "$stale" ] && printf '\n超龄未 grill 的草稿:%b\n' "$stale" || true )

## 指标

\`\`\`
${metrics}
\`\`\`

---
本页只读产出。不改定义、不改登记表、不改 ledger,也不 land 任何提案。
EOF
)"

if [ "$DRY" -eq 1 ]; then
  printf '%s\n' "$report"
  printf '\n(dry-run:未写入 %s)\n' "$REVIEWS"
  exit 0
fi

mkdir -p "$REVIEWS"
printf '%s\n' "$report" > "$LATEST"
{
  printf 'signal=%s\n' "$SIGNAL"
  printf 'at=%s\n' "$NOW"
  printf 'days=%s\n' "$DAYS"
  printf 'repo=%s\n' "$TARGET"
} > "$STATUS"
echo "OK   $LATEST"
echo "OK   $STATUS"

if [ "$SIGNAL" != "yes" ]; then
  echo "agent-review PASS (no signal; 保持安静,不起草)"
  exit 0
fi

# Next proposal number.
# Written as `if` rather than `[ cond ] && assign`: under `set -e` a false
# condition makes the whole statement return non-zero and kills the script,
# which would happen on the first proposal numbered below the running count.
mkdir -p "$PROPOSALS"
n=1
while IFS= read -r p; do
  [ -n "$p" ] || continue
  base="$(basename "$p")"
  num="${base%%-*}"
  case "$num" in
    ''|*[!0-9]*) continue ;;
    *)
      if [ "$((10#$num))" -ge "$n" ]; then
        n=$((10#$num + 1))
      fi
      ;;
  esac
done <<EOF
$(ls -1 "$PROPOSALS"/*.md 2>/dev/null || true)
EOF
NN="$(printf '%02d' "$n")"
DRAFT="${PROPOSALS}/${NN}-agent-${STAMP}.md"

cat > "$DRAFT" <<EOF
---
status: draft
at: ${NOW}
source: scripts/agent-review.sh
repo: ${TARGET}
window_days: ${DAYS}
---

# 委派层提案草稿 ${NN}

**这是草稿,不是决定。** 按 references/agents-evolve.md 第八节:propose → grill →
**人确认用语** → land。AI 不得把本文件标 \`landed\`。

## 信号(脚本填)

$( [ -n "$hits" ] && printf '%s\n' "$hits" || printf '(无 nudge 命中)\n' )
$( [ -n "$stale" ] && printf '\n超龄未 grill 的草稿:%b\n' "$stale" || true )

## 证据(脚本填)

\`\`\`
${metrics}
\`\`\`

## 要改什么(人填)

<!-- 按改动面从小到大选:委派包格式 > kind 登记表一行 > 某个 agent 定义 -->

## 不改什么(人填)

<!-- 明确排除,避免 grill 时范围漂移 -->

## 依据哪些留痕(人填)

<!-- <票目录>/workflow/delegations/<step>-<n>.yaml,逐条列 -->

## 是否动 kind_agents.py 登记表(人填)

<!-- 动了就要同步 references/agents.md 的登记表,否则 agents-check 会红 -->

## 落地后(人填)

<!-- state/ledger.yaml 的 agent_layer_revision + 1,由人改;本文件标 landed,由人标 -->
EOF

echo "OK   $DRAFT"
echo "agent-review PASS (signal=yes;已起草,未 land)"
echo "HINT 下一步是拷问这份草稿,不是直接改定义:"
echo "     读 ~/.cursor/skills/grilling/SKILL.md,只拷问该提案的分叉"
exit 0
