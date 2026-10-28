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

# Goldens must be byte-for-byte reproducible on any machine. Under the
# $(cmd 2>&1) capture below, Python's stdout is block-buffered while stderr
# is not, so a command that prints stdout lines *before* stderr lines
# (delegation write: OK/HINT then FAIL/STOP) interleaves them differently
# depending on whether the invoking shell exported PYTHONUNBUFFERED. Pin the
# unbuffered order — the program's logical order — so recording and --verify
# agree in every environment.
export PYTHONUNBUFFERED=1
# E2.5 python golden lane: byte-stable txtar for the Python driver only.
# Go default-engine walks live in test/e2e and cmd/idev (run start/apply);
# do not point this script at the Go writer or the txtar bytes will drift.
export IDEV_ENGINE=python
export IDEV_AGENT_FEEDBACK=off
# E1.3 only fires when an idev binary is visible. Keep this lane on pure
# Python so txtar bytes stay stable: switch the binary off (the kernel's own
# bin/idev included) and hide any PATH idev.
export IDEV_BIN=off
export PATH="/usr/bin:/bin:/usr/sbin:/sbin"

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
# delegation write copies timing from the newest subagent stop in the store;
# the person's ~/.idev would leak into the bytes.
export IDEV_DATA="$WORK/idev-data"

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
C() { python3 "${IDEV}/scripts/check-feature.py" "$@"; }
G() { python3 "${IDEV}/scripts/stage-gate.py" "$@"; }
T() { python3 "${IDEV}/scripts/trace.py" "$@"; }

# --- workflow: start, read, record ----------------------------------------
record start-lite-change "$OUT" "start an 11-step recipe on a fresh ticket" -- \
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
record code-pass-unverified "$OUT" "a verifier kind PASS with no independent verification" -- \
  W record code-pass PASS --evidence "docs/x.md" --feature "$FEATURE"
mkdir -p "$WORK/.idev/task/${FEATURE}/docs"
printf 'reviewed\n' > "$WORK/.idev/task/${FEATURE}/docs/x.md"
record code-pass-no-verifier-record "$OUT" "independent verification named, but the reviewer never recorded a report" -- \
  W record code-pass PASS --evidence "docs/x.md" --verified-by idev-reviewer --verify-evidence "docs/x.md" --feature "$FEATURE"
# The reviewer's report goes through delegation.py, so it lands wherever the
# writer puts this run's records and the guard has to find it there.
cat > "$WORK/rec-verifier.yaml" <<YAML
step: review
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
    FACTS: 源码 docs/x.md:1
    DOC_DRIFT: 无
    CHANGED: review.md
    ASSUMED: 无
    EVIDENCE: docs/x.md
    CONCLUSION: golden
YAML
D write --feature "$FEATURE" --file "$WORK/rec-verifier.yaml" >/dev/null || [ $? -eq 1 ] \
  || { echo "the reviewer's record was refused"; exit 1; }
record code-pass-verified "$OUT" "the reviewer's own record cites the evidence" -- \
  W record code-pass PASS --evidence "docs/x.md" --verified-by idev-reviewer --verify-evidence "docs/x.md" --feature "$FEATURE"
# The report only has to exist at record time. Leaving it would show up in
# the later timeline, which is a different scenario.
rm -f "$(D dir --feature "$FEATURE")/review-1.yaml"
record parallel-next "$OUT" "after code-pass the check group is open together" -- \
  W next --feature "$FEATURE"
record delegate-open "$OUT" "one command delegates every open agent step" -- \
  W delegate --open --feature "$FEATURE"

# A grouped step with a delegation must declare CHANGED, and only inside writes.
cat > "$WORK/rec-outside.yaml" <<YAML
step: review
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
    FACTS: 源码 review.md:1
    DOC_DRIFT: 无
    CHANGED: verify/plan.yaml
    ASSUMED: 无
    EVIDENCE: review.md
    CONCLUSION: golden
YAML
D write --feature "$FEATURE" --file "$WORK/rec-outside.yaml" >/dev/null
record writes-outside "$OUT" "a grouped step may not record a file outside its writes" -- \
  W record review PASS --evidence "review.md" --feature "$FEATURE"
rm -f "$(D dir --feature "$FEATURE")/review-1.yaml"

# --- signals: a load-bearing assumption stops PASS until a person decides ---
# `run` is one member of the open group, so it can be recorded before plan.
cat > "$WORK/rec-signal.yaml" <<YAML
step: run
kind: verify.run
agent: idev-verifier
attempt: 1
brief:
  ticket_home: $WORK/.idev/task/${FEATURE}
  repo: $WORK
  stage: test
  risk_tier: P1
  must_read: verify/SKILL.md
  idev_root: ${IDEV}
report:
  raw: |
    STATUS: PASS
    FACTS: 源码 scripts/workflow.py:1
    DOC_DRIFT: 无
    ASSUMED: [承重] 测试库开跑前是空的
    CHANGED: verify/selftest.md
    EVIDENCE: $WORK/.idev/task/${FEATURE}/review.md
    CONCLUSION: golden
YAML
record delegation-signal "$OUT" "a delegation with a load-bearing assumption raises a signal" -- \
  D write --feature "$FEATURE" --file "$WORK/rec-signal.yaml"
record signal-blocks-pass "$OUT" "PASS is refused while a signal has no decision" -- \
  W record run PASS --evidence "docs/x.md" --feature "$FEATURE"
record decide-non-answer "$OUT" "继续 is not an answer to the question" -- \
  W decide run --signal "[承重] 测试库开跑前是空的" --question "测试库开跑前是空的吗" \
    --answer "是" --quote "继续" --feature "$FEATURE"
record decide-wrong-signal "$OUT" "a decision for a signal the record never raised" -- \
  W decide run --signal "[承重] 别的事" --question "q" --answer "a" --quote "1" --feature "$FEATURE"
record decide-ok "$OUT" "the person answers the question" -- \
  W decide run --signal "[承重] 测试库开跑前是空的" --question "测试库开跑前是空的吗" \
    --options "1 是 / 2 不是,先清库" --recommend "1" --answer "是,每次 CI 新建" --quote "1" --feature "$FEATURE"
second="$(W decide run --signal "[承重] 测试库开跑前是空的" --question "测试库开跑前是空的吗" \
  --answer "不是" --quote "2" --feature "$FEATURE" 2>&1)" && { echo "second decision accepted: $second"; exit 1; }
printf '%s\n' "$second" | grep -q 'already decided (D1)' || { echo "second decision: $second"; exit 1; }
record signal-answered-pass "$OUT" "PASS once every signal has a decision" -- \
  W record run PASS --evidence "docs/x.md" --feature "$FEATURE"

# The rest of the group closes before the plan gate becomes current.
W record plan PASS --evidence "verify/plan.yaml" --feature "$FEATURE" >/dev/null 2>&1
W record review PASS --evidence "review.md" --feature "$FEATURE" >/dev/null 2>&1
W record accept PASS --evidence "verify/accept.md" --feature "$FEATURE" >/dev/null 2>&1

# --- the human gate -------------------------------------------------------
record gate-unlisted-name "$OUT" "a plausible name that no people list has" -- \
  W record gate-plan PASS --by tester --quote "确认" --feature "$FEATURE"
# tester signs below. The kernel's config/people.yaml lists real people only,
# so the product checkout lists its own for this section.
printf 'people:\n  - tester\n' > "$WORK/.idev/people.yaml"
export IDEV_PRODUCT_REPO="$WORK"
record gate-skip-no-evidence "$OUT" "skipping a gate without evidence" -- \
  W record gate-plan SKIPPED --feature "$FEATURE"

# Behaviour P0 changed on purpose.
record gate-agent-signs "$FIXED" \
  "an agent name in --by. BEFORE P0: exit 0, the gate passed and run.yaml recorded signoff.by=idev-coder — is_human() only blacklisted agent/ai/cursor/assistant. AFTER: BLOCKED. Review §3.1." -- \
  W record gate-plan PASS --by idev-coder --quote "确认" --feature "$FEATURE"
# AUTO: the plan gate lists every tier, and record AUTO runs check-feature
# verify-plan itself. The demo ticket has no baseline or design, so the check
# fails at P0 as at any other tier, and a saved file that says 0 FAIL changes
# nothing: AUTO overwrites it with the check it ran.
DT="$WORK/.idev/task/${FEATURE}"
sed 's/^risk_tier: P1$/risk_tier: P0/' "$FIXTURE/deliver.yaml" > "$DT/deliver.yaml"
record gate-auto-p0 "$OUT" "AUTO on a P0 plan gate runs the plan check, which this ticket fails" -- \
  W record gate-plan AUTO --feature "$FEATURE"
cp "$FIXTURE/deliver.yaml" "$DT/deliver.yaml"
record gate-auto-evidence-elsewhere "$OUT" "AUTO naming a file other than the log it writes" -- \
  W record gate-plan AUTO --evidence "review.md" --feature "$FEATURE"
printf '%s\n' "---" "0 FAIL" > "$DT/verify/plan-check.log"
record gate-auto-forged "$OUT" "a saved file that says 0 FAIL does not stand in for the check" -- \
  W record gate-plan AUTO --evidence "verify/plan-check.log" --feature "$FEATURE"

record gate-ok "$OUT" "a person records the gate; the sentence is a note" -- \
  W record gate-plan PASS --by tester --quote "确认" --feature "$FEATURE"
unset IDEV_PRODUCT_REPO

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

# The three exit codes of `delegation write` (design §20.4): 0 clean, 1 the
# record landed but a check failed (conductor must read the report), 2 the
# write itself was refused. The 0 and 2 paths above cover clean, twice,
# retry-without-prior and the signoff STOP; these two close the set with the
# conductor-owned kind, the wrong agent for the kind, and the check-FAIL
# exit that still wrote the record.
cat > "$WORK/rec-conductor.yaml" <<YAML
step: preflight
kind: preflight.inputs
agent: idev-coder
attempt: 1
report:
  raw: |
    STATUS: PASS
YAML
record delegation-kind-kept "$OUT" "a record for a kind the conductor keeps" -- \
  D write --feature "$FEATURE" --file "$WORK/rec-conductor.yaml"

cat > "$WORK/rec-mismatch.yaml" <<YAML
step: report
kind: review.report
agent: idev-coder
attempt: 1
report:
  raw: |
    STATUS: PASS
YAML
record delegation-agent-mismatch "$OUT" "the right kind delegated to the wrong agent" -- \
  D write --feature "$FEATURE" --file "$WORK/rec-mismatch.yaml"

cat > "$WORK/rec-checks-fail.yaml" <<YAML
step: plan
kind: verify.plan
agent: idev-verifier
attempt: 1
report:
  raw: |
    STATUS: PASS
    EVIDENCE: $WORK/.idev/task/${FEATURE}/review.md
YAML
record delegation-checks-fail "$OUT" "a record that lands (exit 1) with a brief the conductor owes" -- \
  D write --feature "$FEATURE" --file "$WORK/rec-checks-fail.yaml"

# --- check-feature: all six stages on one example ticket --------------------
# The skill's own example fixtures assemble into a ticket that passes every
# stage — the same set selfcheck.sh drives, but recorded once so the Go port
# can replay byte-for-byte what each stage prints on the way through.
EX="$WORK/.idev/task/example-change"
mkdir -p "$EX/verify" "$WORK/.idev/docs/spec"
python3 - "$IDEV" "$EX" "$WORK" <<'PY'
import shutil, sys
from pathlib import Path

idev, ex, work = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
base = idev / "deliver" / "references"
ver = idev / "verify" / "references"
ops = idev / "ops" / "references"
b = (base / "baseline.example.yaml").read_text()
(ex / "baseline.yaml").write_text(b.replace("sealed: false", "sealed: true"))
for src, dst in (
    ("req.example.yaml", "req.yaml"),
    ("arch.example.yaml", "arch.yaml"),
    ("deliver.example.yaml", "deliver.yaml"),
    ("review.example.md", "review.md"),
    ("deliver-eval.example.md", "deliver-eval.md"),
):
    shutil.copy(base / src, ex / dst)
shutil.copy(base / "design.example.md", ex / "design.md")
(ex / "grill.md").write_text(
    "convention: grilling\n"
    "frontier: empty\n"
    "shared_understanding: true\n"
    "arch_frontier: empty\n"
    "arch_shared_understanding: true\n"
    "\n"
    "❓ **Q1** - **scope**: settled in the example baseline\n"
    "➡️ keep the sealed baseline\n"
    "\n"
    "## arch\n"
    "\n"
    "❓ **Q1** - **rollback**: how does the design back out\n"
    "➡️ the approval.enabled switch\n"
)
shutil.copy(ver / "plan.example.yaml", ex / "verify" / "plan.yaml")
shutil.copy(ver / "unproven.example.md", ex / "unproven.md")
shutil.copy(ops / "ops.example.yaml", ex / "ops.yaml")
(work / ".idev" / "docs" / "spec" / "example-change.md").write_text(
    "restates the sealed baseline\n"
)
PY

for s in req-review req arch code verify-plan; do
  record "check-feature-$s" "$OUT" "check-feature $s on the assembled example ticket" -- \
    C --repo "$WORK" --feature example-change --stage "$s"
done

# The test stage demands plan.mode: test and the unproven surfaces; the
# swap is the one the selfcheck performs too.
sed 's/^mode: selftest$/mode: test/' "$EX/verify/plan.yaml" > "$EX/verify/plan.test.yaml"
mv "$EX/verify/plan.test.yaml" "$EX/verify/plan.yaml"
record check-feature-test "$OUT" "check-feature test with mode: test and unproven.md in place" -- \
  C --repo "$WORK" --feature example-change --stage test
record check-feature-ops "$OUT" "check-feature ops on the example ops ticket" -- \
  C --repo "$WORK" --feature example-change --stage ops

# --- trace: append into an isolated sink, then read it back -----------------
# IDEV_TRACE_DIR points the sink away from the repo's real traces; the date
# names normalise to <DATE>-<NNN>.yaml, and the second append proves the
# O_EXCL reservation gave the next round a fresh name.
export IDEV_TRACE_DIR="$WORK/traces"
record trace-append "$OUT" "trace append writes the next reserved name and renders it" -- \
  T append "$IDEV/references/trace.example.yaml"
record trace-append-again "$OUT" "a second append gets the next name (O_EXCL reservation)" -- \
  T append "$IDEV/references/trace.example.yaml"
record trace-list "$OUT" "trace list over the two appended rounds" -- \
  T list
record trace-last "$OUT" "trace last renders the newest round" -- \
  T last
record trace-check-example "$OUT" "trace check on the example trace" -- \
  T check "$IDEV/references/trace.example.yaml"

# --- the ticketless verify-plan path (needs_ticket: false) -----------------
# A recipe that does not build a baseline must not be gated on sealed —
# but only while the run really points at it. The same directory with a
# ticketed recipe in the run stays on the strict path (design §20.4's
# "behaviour P0 deliberately changed" spirit: the pair of goldens is the
# proof the waiver is narrow).
CR="$WORK/.idev/task/code-review"
mkdir -p "$CR/workflow" "$CR/verify"
cp "${IDEV}/workflows/code-review.yaml" "$WORK/code-review.yaml"
sed -e "s|^recipe: .*|recipe: ${WORK}/code-review.yaml|" > "$CR/workflow/run.yaml" <<'RUN'
schema_version: 1
run_id: 01GOLDEN0000000000000000000
workflow_id: code-review
recipe: replaced-above
feature: code-review
status: running
started_at: "2026-10-17T00:00:00+08:00"
params: {}
policy: {on_fail: stop, on_gate: stop}
steps:
  - {id: report, kind: review.report, status: PASS}
  - {id: gate-report, kind: human.gate, status: PASS}
  - {id: plan, kind: verify.plan, status: running}
revisions: []
feedback: {status: pending}
RUN
cat > "$CR/verify/plan.yaml" <<'PLAN'
schema_version: 1
mode: selftest
goal: 修掉已签收 I1
non_goal: []
cases:
  - id: self-i1
    dimension: correctness
    status: PASS
    evidence: review.md
    assert: 修复后 I1 对应场景返回 400
PLAN

record verify-plan-ticketless "$OUT" "verify-plan on a needs_ticket:false recipe (no baseline)" -- \
  C --repo "$WORK" --feature code-review --stage verify-plan
record stage-gate-test-ticketless "$OUT" "stage-gate test with cases that carry no baseline_item_id" -- \
  G --repo "$WORK" --feature code-review --stage test

# The control: same ticket, run now points at a ticketed recipe. The
# sealed demand must come back. (run.yaml is restored after, though the
# recording ends here anyway.)
cp "$CR/workflow/run.yaml" "$CR/workflow/run.ticketless.yaml"
sed -e "s|^recipe: .*|recipe: ${IDEV}/workflows/lite-change.yaml|" \
    -e "s|^workflow_id: .*|workflow_id: lite-change|" \
    "$CR/workflow/run.ticketless.yaml" > "$CR/workflow/run.yaml"
record verify-plan-ticketed-control "$OUT" "same ticket, ticketed recipe: sealed is demanded again" -- \
  C --repo "$WORK" --feature code-review --stage verify-plan
mv "$CR/workflow/run.ticketless.yaml" "$CR/workflow/run.yaml"

# --- AUTO on the example ticket --------------------------------------------
# dev-logic's plan gate may pass on machine checks at P1. The example ticket
# passes verify-plan, so AUTO passes on the check it ran; a case that can
# never run is a question for a person, and AUTO stops there first.
sed 's/^mode: test$/mode: selftest/' "$EX/verify/plan.yaml" > "$WORK/plan.selftest.yaml"
cp "$WORK/plan.selftest.yaml" "$EX/verify/plan.yaml"
W start dev-logic --feature example-change >/dev/null 2>&1
W record plan PASS --evidence "verify/plan.yaml" --feature example-change >/dev/null 2>&1
python3 - "$IDEV" "$EX/verify/plan.yaml" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "scripts" / "lib"))
import safeyaml
path = Path(sys.argv[2])
plan = safeyaml.mapping(path)
plan["cases"][1].pop("runner")
path.write_text(safeyaml.dump(plan), encoding="utf-8")
PY
record gate-auto-signal "$OUT" "AUTO when the plan check passes but leaves a case for a person" -- \
  W record gate-plan AUTO --feature example-change
cp "$WORK/plan.selftest.yaml" "$EX/verify/plan.yaml"
record gate-auto-pass "$OUT" "AUTO when the plan check the gate ran is clean" -- \
  W record gate-plan AUTO --feature example-change
echo
if [ "$VERIFY" = 1 ]; then
  echo "golden verify: ${pass} same, ${diff_count} different"
  [ "$diff_count" -eq 0 ] || { echo "golden FAIL"; exit 1; }
  echo "golden PASS"
else
  echo "golden record: wrote ${wrote} cases under test/golden/legacy/"
fi
