#!/usr/bin/env bash
# Mine traces / inbox / reviews. Product sessions write under <repo>/.idev/.
# Conductor sessions with no current product write under state/.
# Never modifies SKILL.md / schema / ledger.phase.
# Usage: evolve-review.sh [--dry-run] [--window N] [--review-days N]
# Signal = HARD>0 or inbox hot tags only; reviews are soft (≤ review-days, default 7).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SINK=(python3 "$ROOT/scripts/lib/product_sink.py")
PROPOSALS="${IDEV_PROPOSALS_DIR:-$("${SINK[@]}" proposals --mkdir)}"
INBOX="${IDEV_INBOX_DIR:-$("${SINK[@]}" inbox)}"
REVIEWS="${IDEV_REVIEWS_DIR:-$("${SINK[@]}" reviews --mkdir)}"
WINDOW=50
REVIEW_DAYS="${IDEV_EVOLVE_REVIEW_DAYS:-7}"
DRY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --window) shift_next=window ;;
    --review-days) shift_next=review_days ;;
    --help|-h)
      echo "usage: $0 [--dry-run] [--window N] [--review-days N]"
      exit 0
      ;;
    *)
      if [[ "${shift_next:-}" == "window" ]]; then
        WINDOW="$arg"; shift_next=
      elif [[ "${shift_next:-}" == "review_days" ]]; then
        REVIEW_DAYS="$arg"; shift_next=
      elif [[ "$arg" =~ ^[0-9]+$ ]]; then
        WINDOW="$arg"
      else
        echo "unknown: $arg" >&2
        exit 2
      fi
      ;;
  esac
done

mkdir -p "$PROPOSALS"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DRAFT="$PROPOSALS/${STAMP}-evolve-review.md"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# 1) audit-traces
AUDIT_OUT="$TMP/audit.txt"
if bash "$ROOT/scripts/audit-traces.sh" "$WINDOW" >"$AUDIT_OUT" 2>&1; then
  :
else
  # non-strict: capture anyway
  true
fi
HARD="$(sed -n 's/^HARD_COUNT=//p' "$AUDIT_OUT" | tail -1)"
HARD="${HARD:-0}"

# 2) inbox tag histogram (exclude ok)
python3 - "$INBOX" "$TMP/inbox.json" <<'PY'
import json, os, sys, glob
inbox = sys.argv[1]
out = sys.argv[2]
counts = {}
items = []
for path in sorted(glob.glob(os.path.join(inbox, "*.yaml")) + glob.glob(os.path.join(inbox, "*.yml"))):
    tags = []
    note = ""
    feature = ""
    status = ""
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        continue
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("feature:"):
            feature = s.split(":", 1)[1].strip().strip('"')
        elif s.startswith("status:"):
            status = s.split(":", 1)[1].strip()
        elif s.startswith("note:"):
            note = s.split(":", 1)[1].strip().strip('"')
        elif s.startswith("- "):
            tag = s[2:].strip().strip('"')
            if tag and not tag.startswith("#"):
                tags.append(tag)
    # only count when we saw a tags: block — crude: any - lines after tags:
    if "tags:" not in text:
        tags = []
    # consumed / archived inbox must not re-heat evolve-review
    if status.lower() in ("consumed", "archived", "resolved"):
        continue
    for t in tags:
        if t == "ok":
            continue
        counts[t] = counts.get(t, 0) + 1
    if tags and any(t != "ok" for t in tags):
        items.append({"path": path, "feature": feature, "tags": tags, "note": note, "status": status})
payload = {"counts": counts, "items": items, "hot": [t for t, c in sorted(counts.items(), key=lambda x: -x[1]) if c >= 2]}
open(out, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=2))
print(f"inbox_non_ok={sum(counts.values())} hot_tags={payload['hot']}")
PY

# 3) recent reviews mentioning gaps (mtime within REVIEW_DAYS; soft only)
python3 - "$REVIEWS" "$TMP/reviews.txt" "$REVIEW_DAYS" <<'PY'
import os, sys, re, time
reviews = sys.argv[1]
out = sys.argv[2]
days = int(sys.argv[3])
cutoff = time.time() - days * 86400
pat = re.compile(r"缺口|缺陷|FAIL|假绿|skill-unclear|missed-impact|schema-gap|未对齐", re.I)
skip = re.compile(r"evolve-review-receipt|self-evolution|evolve-landed|skill-unclear-evolve", re.I)
rows = []
if os.path.isdir(reviews):
    files = []
    for name in os.listdir(reviews):
        if not name.endswith(".md") or skip.search(name):
            continue
        p = os.path.join(reviews, name)
        try:
            mtime = os.path.getmtime(p)
        except OSError:
            continue
        if mtime < cutoff:
            continue
        files.append((mtime, p, name))
    files.sort(reverse=True)
    for _, p, name in files[:20]:
        try:
            text = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if pat.search(text):
            hit = next((ln.strip() for ln in text.splitlines() if pat.search(ln)), name)
            rows.append(f"- `{name}`: {hit[:160]}")
open(out, "w", encoding="utf-8").write("\n".join(rows) if rows else "(none)")
print(f"review_hits={len(rows)} review_days={days}")
PY

# 4) open proposals (+ stale/draft age as hard signal)
STALE_DAYS="${IDEV_PROPOSAL_STALE_DAYS:-14}"
python3 - "$PROPOSALS" "$TMP/open.txt" "$TMP/stale_n.txt" "$STALE_DAYS" <<'PY'
import os, sys, re, time
prop, out, stale_out, stale_days = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
rows = []
stale_n = 0
cutoff = time.time() - stale_days * 86400
closed = {"landed", "archived", "rejected", "ga"}
for name in sorted(os.listdir(prop)) if os.path.isdir(prop) else []:
    if not name.endswith(".md"):
        continue
    p = os.path.join(prop, name)
    try:
        text = open(p, encoding="utf-8", errors="replace").read(4000)
        mtime = os.path.getmtime(p)
    except OSError:
        continue
    m = re.search(r"^status:\s*(\S+)", text, re.M)
    status = (m.group(1) if m else "unknown").strip().strip('"').lower()
    if status in closed:
        continue
    age = int((time.time() - mtime) / 86400)
    mark = ""
    if status == "stale" or (mtime < cutoff and status in ("draft", "unknown", "open", "partial")):
        stale_n += 1
        mark = " STALE_SIGNAL"
    rows.append(f"- `{name}` status={status} age={age}d{mark}")
open(out, "w", encoding="utf-8").write("\n".join(rows) if rows else "(none)")
open(stale_out, "w", encoding="utf-8").write(str(stale_n))
print(f"open_proposals={len(rows)} stale_proposals={stale_n} stale_days={stale_days}")
PY

HOT="$(python3 -c "import json; d=json.load(open('$TMP/inbox.json')); print(','.join(d.get('hot') or []) or '(none)')")"
INBOX_N="$(python3 -c "import json; d=json.load(open('$TMP/inbox.json')); print(sum((d.get('counts') or {}).values()))")"
REVIEW_BODY="$(cat "$TMP/reviews.txt")"
OPEN_BODY="$(cat "$TMP/open.txt")"
STALE_N="$(cat "$TMP/stale_n.txt")"
AUDIT_SNIP="$(grep -E 'HARD|ALERT|multi-exec|seal-write|WARN|FAIL' "$AUDIT_OUT" | head -40 || true)"

SIGNAL=0
[[ "$HARD" != "0" ]] && SIGNAL=1
[[ "$HOT" != "(none)" ]] && SIGNAL=1
[[ "$STALE_N" != "0" ]] && SIGNAL=1
# reviews are soft: never raise signal alone (debounce historical 缺口 mentions)

TITLE_DATE="$(date +%Y%m%d)"
if [[ "$SIGNAL" -eq 0 ]]; then
  BODY=$(cat <<MD
# ${TITLE_DATE} evolve-review：无信号

status: archived
at: $(date -Iseconds)
source: evolve-review.sh
window: ${WINDOW}

## 结论

本窗未发现需进化的硬信号（HARD_COUNT=0，inbox 无 ≥2 同类非 ok 热标签，无超龄 draft/stale 提案）。reviews 缺口词仅作软提示，不单独抬 signal。

## 证据摘要

- HARD_COUNT=${HARD}
- inbox non-ok count=${INBOX_N}; hot_tags=${HOT}
- stale_proposals (≥${STALE_DAYS}d draft/stale)=${STALE_N}
- soft review hits (≤${REVIEW_DAYS}d, not a signal): ${REVIEW_BODY}
- open proposals:
${OPEN_BODY}

## 不改什么

- 不改 SKILL / schema / ledger.phase
- 本文件仅作收据；可保留或由 curator 归档
MD
)
else
  BODY=$(cat <<MD
# ${TITLE_DATE} evolve-review 草稿（待拷问）

status: draft
at: $(date -Iseconds)
source: evolve-review.sh
window: ${WINDOW}

## 信号

| 源 | 值 |
|----|----|
| HARD_COUNT | ${HARD} |
| inbox hot tags (≥2) | ${HOT} |
| inbox non-ok count | ${INBOX_N} |
| stale proposals (≥${STALE_DAYS}d) | ${STALE_N} |

## 要改什么（草稿 — 须 grill 后改）

> Agent/人根据下方证据填具体改动；本脚本**不**自动改 Skill。

1. （待填）针对 hot tags / HARD 的步骤澄清或硬规则
2. （待填）是否升 schema_version：默认不升

## 不改什么

- 不引入分数门禁 / LLM 自评盖章
- 不自动 land、不改 \`phase: ga\`
- 试点的中间态写在该仓 `.idev/`，不写进内核

## 依据

### audit-traces (window=${WINDOW})

\`\`\`
${AUDIT_SNIP:-"(no HARD/WARN lines)"}
\`\`\`

### inbox hot / items

\`\`\`json
$(python3 -c "import json; print(json.dumps(json.load(open('$TMP/inbox.json')), ensure_ascii=False, indent=2))" | head -80)
\`\`\`

### recent reviews (gap keywords)

${REVIEW_BODY}

### open proposals (not landed/archived)

${OPEN_BODY}

## schema_version

不升（除非 grill 认定契约字段变化）。

## 下一步

1. 人 / Agent 补全「要改什么」
2. 读 \`~/.cursor/skills/grilling/SKILL.md\` 拷问
3. 人说确认用语后再 land 真源 \`~/.cursor/skills/idev/\`
4. 入口台账 \`conductor_revision + 1\`，本提案标 \`landed\`
MD
)
fi

PILOT_TEXT="$(python3 - "$ROOT" "$WINDOW" <<'PY'
import json, os, subprocess, sys
root, window = sys.argv[1], sys.argv[2]
proc = subprocess.run(
    [sys.executable, os.path.join(root, "scripts/lib/product_marker.py"), "--from-install", "--depth", "2"],
    check=False,
    capture_output=True,
    text=True,
)
try:
    rows = json.loads(proc.stdout or "[]")
except json.JSONDecodeError:
    rows = []
if not isinstance(rows, list):
    rows = []
lines = []
for row in rows:
    if not isinstance(row, dict):
        continue
    repo = str(row.get("repo") or "")
    ident = str(row.get("id") or "")
    trace = os.path.join(repo, ".idev", "traces")
    hard = "0"
    if os.path.isdir(trace) and os.listdir(trace):
        env = os.environ.copy()
        env["IDEV_TRACE_DIR"] = trace
        audited = subprocess.run(
            ["bash", os.path.join(root, "scripts/audit-traces.sh"), window],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        for line in (audited.stdout or "").splitlines():
            if line.startswith("HARD_COUNT="):
                hard = line.split("=", 1)[1].strip() or "0"
    lines.append("- %s HARD=%s 中间态在 `%s/.idev/`" % (ident, hard, repo))
print("\n".join(lines) if lines else "(none)")
PY
)"
BODY="${BODY}

## 自净化发现的试点

这些仓写了 \`.idev/marker.yaml\` 且 \`marker: idev\`、\`evolve: pilot\`。内核先跑通用复盘；试点自己的 trace、提案、复盘留在该仓 \`.idev/\`，方便下次接着做。这里只记计数，不抄试点正文进内核。

${PILOT_TEXT}
"

echo "=== evolve-review ==="
echo "HARD_COUNT=${HARD}"
echo "hot_tags=${HOT}"
echo "signal=${SIGNAL}"
if [[ "$DRY" == "1" ]]; then
  echo "DRY-RUN: would write $OUT_DRAFT"
  printf '%s\n' "$BODY" | head -40
  echo "..."
  exit 0
fi
printf '%s\n' "$BODY" > "$OUT_DRAFT"
echo "wrote $OUT_DRAFT"
# also copy short receipt to reviews
RECEIPT="$REVIEWS/$(date +%Y%m%d)-evolve-review-receipt.md"
LATEST="$REVIEWS/evolve-review-latest.md"
mkdir -p "$REVIEWS"
cat > "$RECEIPT" << MD
# evolve-review receipt

at: $(date -Iseconds)
draft: \`${OUT_DRAFT}\`
HARD_COUNT: ${HARD}
hot_tags: ${HOT}
signal: ${SIGNAL}
MD
# stable pointer for LaunchAgent / Bot routine
cp "$RECEIPT" "$LATEST"
# also append one-line status for grepping
{
  echo "signal: ${SIGNAL}"
  echo "HARD_COUNT: ${HARD}"
  echo "hot_tags: ${HOT}"
  echo "draft: ${OUT_DRAFT}"
  echo "at: $(date -Iseconds)"
} > "$REVIEWS/evolve-review-status.env"
echo "receipt $RECEIPT"
echo "latest $LATEST"
# Fold product .idev residue after this generation. Dry-run returns above.
python3 - "$ROOT" <<'PY'
import json, subprocess, sys
root = sys.argv[1]
clean = [sys.executable, root + "/scripts/execution-clean.py", "--compact", "--apply", "--bump"]
marker = [sys.executable, root + "/scripts/lib/product_marker.py", "--from-install", "--depth", "2"]
sink = [sys.executable, root + "/scripts/lib/product_sink.py", "--print-repo"]
repos = []
session = subprocess.run(sink, check=False, capture_output=True, text=True)
session_repo = (session.stdout or "").strip()
if session_repo:
    repos.append(session_repo)
found = subprocess.run(marker, check=False, capture_output=True, text=True)
try:
    rows = json.loads(found.stdout or "[]")
except json.JSONDecodeError:
    rows = []
if isinstance(rows, list):
    for row in rows:
        if isinstance(row, dict) and row.get("repo"):
            repos.append(row["repo"])
seen = []
for repo in repos:
    if repo in seen:
        continue
    seen.append(repo)
    proc = subprocess.run(clean + ["--repo", repo], check=False)
    if proc.returncode != 0:
        sys.exit(proc.returncode)
PY
exit $?
