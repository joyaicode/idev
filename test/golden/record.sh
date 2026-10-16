#!/usr/bin/env bash
# Record (or verify) the output of the pre-Go commands, as golden .txtar files.
#
# These are the safety net for the whole migration: P2 replays the same
# scenarios against `idev workflow …` and `idev delegation write …` and
# compares byte for byte. Without them "the Go port behaves the same" is an
# opinion.
#
#   bash test/golden/record.sh            # write test/golden/legacy/*.txtar
#   bash test/golden/record.sh --verify   # compare, exit 1 on any difference
#
# Scenarios that P0 deliberately changed are recorded too, under
# legacy/fixed/, each with a header saying what the old output was and why it
# is no longer that. A golden file that silently encodes a bug is worse than
# no golden file.
set -uo pipefail

IDEV="$(cd "$(dirname "$0")/../.." && pwd -P)"
OUT="${IDEV}/test/golden/legacy"
FIXED="${OUT}/fixed"
FIXTURE="${IDEV}/test/fixtures/tickets/demo"
NORM="${IDEV}/test/golden/normalize.py"
FEATURE=demo

VERIFY=0
[ "${1:-}" = "--verify" ] && VERIFY=1

WORK="$(mktemp -d "${TMPDIR:-/tmp}/idev-golden.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
# macOS hands back /var/folders/... but every path the tools print has been
# through resolve(), which yields /private/var/folders/... Normalising against
# the unresolved form would leave the scratch path in the golden file and make
# every recording machine-specific.
WORK="$(cd "$WORK" && pwd -P)"

# A product checkout: product_repo() walks up for .git, and doc_home puts the
# ticket under .idev/task/<feature>.
mkdir -p "$WORK/.git" "$WORK/.idev/task/${FEATURE}/workflow" "$WORK/.idev/task/${FEATURE}/verify"
cp "$FIXTURE/deliver.yaml" "$WORK/.idev/task/${FEATURE}/deliver.yaml"
: > "$WORK/.idev/task/${FEATURE}/review.md"

pass=0; diff_count=0; wrote=0

# record <name> <dir> <description> -- <cmd...>
record() {
  local name="$1" dir="$2" desc="$3"; shift 4
  local raw rc clean dest cmd
  raw="$("$@" 2>&1)"; rc=$?
  clean="$(printf '%s\n' "$raw" | python3 "$NORM" --work "$WORK" --idev "$IDEV")"
  # The command line goes through the same substitutions: it carries fixture
  # paths too, and a golden file that records the scratch dir anywhere in it
  # cannot be compared on another machine.
  cmd="$(printf '%s\n' "$*" | python3 "$NORM" --work "$WORK" --idev "$IDEV")"

  dest="${dir}/${name}.txtar"
  local body
  body="$(printf '%s\n' \
    "# ${desc}" \
    "# cmd: ${cmd}" \
    "" \
    "-- exit --" \
    "${rc}" \
    "-- output --" \
    "${clean}")"

  if [ "$VERIFY" = 1 ]; then
    if [ ! -f "$dest" ]; then
      echo "MISSING ${dest##*/golden/}"; diff_count=$((diff_count + 1)); return
    fi
    if [ "$body" = "$(cat "$dest")" ]; then
      pass=$((pass + 1))
    else
      echo "DIFF    ${dest##*/golden/}"
      diff <(printf '%s\n' "$body") "$dest" | sed 's/^/        /' | head -20
      diff_count=$((diff_count + 1))
    fi
  else
    mkdir -p "$dir"
    printf '%s\n' "$body" > "$dest"
    wrote=$((wrote + 1))
  fi
}

W() { python3 "${IDEV}/scripts/workflow.py" --repo "$WORK" "$@"; }
D() { python3 "${IDEV}/scripts/delegation.py" --repo "$WORK" "$@"; }

# --- workflow: start, read, record ----------------------------------------
record start-lite-change "$OUT" "start a 7-step recipe on a fresh ticket" -- \
  W start lite-change --feature "$FEATURE"
record next-after-start "$OUT" "NEXT/OPEN/DELEGATE for the first step" -- \
  W next --feature "$FEATURE"
record status-after-start "$OUT" "the whole run as a table" -- \
  W status --feature "$FEATURE"
record start-twice "$OUT" "a second start while a run is live is refused" -- \
  W start lite-change --feature "$FEATURE"

record record-pass "$OUT" "record the first step PASS with evidence" -- \
  W record preflight PASS --evidence "docs/x.md" --feature "$FEATURE"
record record-out-of-order "$OUT" "recording a later step before the current one" -- \
  W record run PASS --feature "$FEATURE"
record record-again-no-note "$OUT" "changing a recorded step needs --note" -- \
  W record preflight FAIL --feature "$FEATURE"
record record-again-with-note "$OUT" "changing it with --note is allowed" -- \
  W record preflight PASS --note "re-ran it" --feature "$FEATURE"
record record-bad-status "$OUT" "an unknown status" -- \
  W record scope-guard MAYBE --feature "$FEATURE"

W record scope-guard PASS --evidence "docs/x.md" --feature "$FEATURE" >/dev/null 2>&1
W record code-pass PASS --evidence "docs/x.md" --feature "$FEATURE" >/dev/null 2>&1
W record plan PASS --evidence "verify/plan.yaml" --feature "$FEATURE" >/dev/null 2>&1

# --- the human gate -------------------------------------------------------
record gate-no-by "$OUT" "a gate PASS with no --by" -- \
  W record gate-plan PASS --feature "$FEATURE"
record gate-no-quote "$OUT" "a gate PASS with a person but no quote" -- \
  W record gate-plan PASS --by tester --feature "$FEATURE"
record gate-skip-no-evidence "$OUT" "skipping a gate without evidence" -- \
  W record gate-plan SKIPPED --feature "$FEATURE"

# Behaviour P0 changed on purpose.
record gate-agent-signs "$FIXED" \
  "an agent name in --by. BEFORE P0: exit 0, the gate passed and run.yaml recorded signoff.by=idev-coder — is_human() only blacklisted agent/ai/cursor/assistant. AFTER: BLOCKED. Review §3.1." -- \
  W record gate-plan PASS --by idev-coder --quote "确认" --feature "$FEATURE"
record gate-question-quote "$FIXED" \
  "a question as the confirmation. BEFORE P0: exit 0 — is_confirm() was a prefix test, so 同意吗 started with 同意 and counted. AFTER: BLOCKED, reason=question. Review §3.1." -- \
  W record gate-plan PASS --by tester --quote "同意吗" --feature "$FEATURE"
record gate-refusal-quote "$FIXED" \
  "a refusal as the confirmation. BEFORE P0: exit 0 — 确认不了 starts with 确认. AFTER: BLOCKED, reason=unparsed-tail. Review §3.1." -- \
  W record gate-plan PASS --by tester --quote "确认不了" --feature "$FEATURE"

record gate-ok "$OUT" "a person with a real confirmation" -- \
  W record gate-plan PASS --by tester --quote "确认" --feature "$FEATURE"

# --- delegation records ---------------------------------------------------
cat > "$WORK/rec.yaml" <<YAML
step: code-pass
kind: review.report
agent: idev-reviewer
attempt: 1
brief:
  ticket_home: $WORK/.idev/task/${FEATURE}
  repo: $WORK
  stage: code
  risk_tier: P1
  must_read: conventions/coding.md
  idev_root: ${IDEV}
report:
  raw: |
    STATUS: PASS
    FACTS: codegraph_context + 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    ASSUMED: 无
    EVIDENCE: $WORK/.idev/task/${FEATURE}/review.md
    CONCLUSION: golden
YAML
record delegation-write-clean "$OUT" "a clean delegation record" -- \
  D write --feature "$FEATURE" --file "$WORK/rec.yaml"

record delegation-write-twice "$FIXED" \
  "the same step and attempt written twice. BEFORE P0: exit 0 and the first record was replaced — the failure that caused the retry vanished, with both calls reporting OK. AFTER: exit 2, the first record is intact. Review §3.2." -- \
  D write --feature "$FEATURE" --file "$WORK/rec.yaml"

sed 's/^attempt: 1$/attempt: 2/' "$WORK/rec.yaml" > "$WORK/rec2.yaml"
record delegation-retry-no-prior "$OUT" "attempt 2 with no brief.prior_failure" -- \
  D write --feature "$FEATURE" --file "$WORK/rec2.yaml"

cat > "$WORK/rec-signoff.yaml" <<YAML
step: sign-claim
kind: review.report
agent: idev-reviewer
attempt: 1
brief:
  ticket_home: $WORK/.idev/task/${FEATURE}
  repo: $WORK
  stage: code
  risk_tier: P1
  must_read: conventions/coding.md
  idev_root: ${IDEV}
report:
  raw: |
    STATUS: PASS
    FACTS: 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    ASSUMED: 无
    EVIDENCE: $WORK/.idev/task/${FEATURE}/review.md
    CHANGED: deliver.yaml
    CONCLUSION: 我已写入 sealed: true
YAML
record delegation-signoff-claim "$OUT" "an agent claiming it wrote a signoff field" -- \
  D write --feature "$FEATURE" --file "$WORK/rec-signoff.yaml"

record delegation-timeline "$OUT" "the attempt timeline" -- \
  D timeline --feature "$FEATURE"

# --- summary --------------------------------------------------------------
echo
if [ "$VERIFY" = 1 ]; then
  echo "golden verify: ${pass} same, ${diff_count} different"
  [ "$diff_count" -eq 0 ] || { echo "golden FAIL"; exit 1; }
  echo "golden PASS"
else
  echo "golden record: wrote ${wrote} cases under test/golden/legacy/"
fi
