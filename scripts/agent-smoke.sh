#!/usr/bin/env bash
# Smoke test for the agent layer. No real ticket, no product repo, no git.
#
#   bash scripts/smoke.sh
#
# It builds a throwaway checkout in a temp dir, then exercises every script
# twice: once on the happy path, and once on input that SHOULD be rejected.
# A checker that never fires is worse than no checker, so each negative case
# asserts the exact exit code and the expected finding.
#
# Covers: kind_agents · agents-check · delegation (write/check/replay/eval)
#         failure_signature (sig/append/check + tripwire) · hypothesis
#         (add/set/check + all three findings) · agent-metrics
#
# Not covered (needs a real kernel run or a real editor): workflow-agent.py
# driving an actual run.yaml, link-agents.sh, the two patches, and whether
# Claude Code / Cursor actually load the definitions.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
S="${REPO}/scripts"
FEATURE="smoke-change"
PASS=0
FAIL=0

TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

TICKET="${TMP}/.idev/task/${FEATURE}"
mkdir -p "${TICKET}/workflow"
: > "${TICKET}/review.md"

say() { printf '\n== %s\n' "$1"; }

ok() {
  PASS=$((PASS + 1))
  printf '  ok   %s\n' "$1"
}

bad() {
  FAIL=$((FAIL + 1))
  printf '  FAIL %s\n' "$1" >&2
}

# expect <wanted-exit> <label> -- <cmd...>
expect() {
  local want="$1" label="$2"
  shift 3
  local out rc
  out="$("$@" 2>&1)"
  rc=$?
  if [ "$rc" -eq "$want" ]; then
    ok "$label (exit $rc)"
  else
    bad "$label: wanted exit $want, got $rc"
    printf '%s\n' "$out" | sed 's/^/       | /' >&2
  fi
  LAST_OUT="$out"
}

# contains <needle> <label>  — checks LAST_OUT from the previous expect
contains() {
  if printf '%s' "$LAST_OUT" | grep -q -- "$1"; then
    ok "$2"
  else
    bad "$2: output has no '$1'"
    printf '%s\n' "$LAST_OUT" | sed 's/^/       | /' >&2
  fi
}

say "1 kind table and definitions"
expect 0 "kind_agents --check" -- python3 "${S}/lib/kind_agents.py" --check
expect 0 "agents-check" -- python3 "${S}/agents-check.py"
expect 0 "idev root is self-evident after the merge" -- python3 "${S}/lib/kind_agents.py" --kernel
contains "idev" "--kernel names this checkout"
expect 0 "delegate line: review.report" -- python3 "${S}/lib/kind_agents.py" --kind review.report
contains "DELEGATE idev-reviewer" "review.report -> idev-reviewer"
expect 0 "delegate line: human.gate" -- python3 "${S}/lib/kind_agents.py" --kind human.gate
contains "DELEGATE none" "human.gate stays with the conductor"
# The DELEGATE line is now native to the kernel driver (patch 0001 landed),
# so there is no wrapper left to test — workflow.py itself must carry it.
expect 0 "workflow.py imports kind_agents" -- python3 "${S}/workflow.py" --help
contains "workflow" "kernel CLI help still works with the patch applied"

say "2 delegation: happy path"
cat > "${TMP}/good.yaml" <<YAML
step: report
kind: review.report
agent: idev-reviewer
attempt: 1
started_at: 2026-10-12T22:26:55+08:00
finished_at: 2026-10-12T22:30:00+08:00
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: code
  risk_tier: P1
  must_read: conventions/coding.md
  idev_root: ~/.cursor/skills/idev
metrics:
  findings: 3
  blocking: 1
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    CONCLUSION: smoke
YAML
expect 0 "write a clean record" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/good.yaml"
contains "3m05s" "duration derived from started_at/finished_at (185s)"
expect 0 "check passes" -- python3 "${S}/delegation.py" --repo "$TMP" check --feature "$FEATURE"
expect 0 "replay prints the brief" -- \
  python3 "${S}/delegation.py" --repo "$TMP" replay --feature "$FEATURE" --step report
contains "ticket_home" "replay includes the brief"
expect 0 "eval prints counts" -- python3 "${S}/delegation.py" --repo "$TMP" eval --feature "$FEATURE"
contains "agent-eval" "eval has the agent-eval header"
contains "produced" "eval sums the metrics map"
contains "duration_s" "eval reports the duration distribution"
expect 0 "timeline renders" -- python3 "${S}/delegation.py" --repo "$TMP" timeline --feature "$FEATURE"
contains "idev-reviewer" "timeline names the executor"
contains "3m05s" "timeline shows the duration"
expect 0 "list works" -- python3 "${S}/delegation.py" --repo "$TMP" list --feature "$FEATURE"
contains "report" "list names the step"

say "3 delegation: input that must be rejected"
# wrong agent for the kind: review.report belongs to the reviewer
cat > "${TMP}/wrong.yaml" <<YAML
step: report
kind: review.report
agent: idev-coder
brief: {ticket_home: ${TICKET}, repo: ${TMP}, stage: code, must_read: x}
report: {raw: "STATUS: PASS\nEVIDENCE: ${TICKET}/review.md\n"}
YAML
expect 2 "refuse wrong agent for kind" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/wrong.yaml"

# a conductor-only kind must never be delegated
cat > "${TMP}/gate.yaml" <<YAML
step: gate-plan
kind: human.gate
agent: idev-deliver
brief: {ticket_home: ${TICKET}, repo: ${TMP}, stage: code, must_read: x}
report: {raw: "STATUS: PASS\n"}
YAML
expect 2 "refuse delegating human.gate" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/gate.yaml"

# attempt > 1 without prior_failure
cat > "${TMP}/retry.yaml" <<YAML
step: report
kind: review.report
agent: idev-reviewer
attempt: 2
brief: {ticket_home: ${TICKET}, repo: ${TMP}, stage: code, must_read: x}
report: {raw: "STATUS: PASS\nEVIDENCE: ${TICKET}/review.md\n"}
YAML
expect 2 "refuse attempt>1 with no prior_failure" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/retry.yaml"

# a boost agent without idev_root -> brief-complete FAIL (exit 1, recorded).
# The §0 fields are filled in so this case fails for one reason only.
cat > "${TMP}/noroot.yaml" <<YAML
step: code-pass
kind: deliver.code_pass
agent: idev-coder
brief: {ticket_home: ${TICKET}, repo: ${TMP}, stage: code, must_read: conventions/coding.md}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    CHANGE_KIND: 追加行为
    CANON_TRIGGER: 无
    TABLE_HIT: 零命中
YAML
expect 1 "flag missing idev_root for a boost agent" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/noroot.yaml"
contains "brief-complete" "names brief-complete"
contains "conductor" "blames the conductor, not the agent"

# PASS with no evidence -> evidence-present FAIL.
# idev_root is present on purpose: ops is a boost agent, and leaving it out
# would make this case fail two checks at once and prove neither.
cat > "${TMP}/noev.yaml" <<YAML
step: classify
kind: ops.classify
agent: idev-ops
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: ops
  must_read: ops/SKILL.md
  idev_root: ${REPO}
report: {raw: "STATUS: PASS\nCONCLUSION: no path given\n"}
YAML
expect 1 "flag PASS without evidence" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/noev.yaml"
contains "evidence-present" "names evidence-present"

# an agent claiming it wrote a signoff field -> hard stop (exit 2)
cat > "${TMP}/signoff.yaml" <<YAML
step: advance
kind: deliver.advance
agent: idev-deliver
brief: {ticket_home: ${TICKET}, repo: ${TMP}, stage: req, must_read: deliver/SKILL.md}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    CONCLUSION: 已写入 accepted: true
YAML
expect 2 "hard-stop on a claimed signoff write" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/signoff.yaml"
contains "no-signoff-write" "names no-signoff-write"

# the same wording in a denial must NOT trip it
cat > "${TMP}/denial.yaml" <<YAML
step: advance2
kind: deliver.advance
agent: idev-deliver
brief: {ticket_home: ${TICKET}, repo: ${TMP}, stage: req, must_read: deliver/SKILL.md}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    CHECKS: no-signoff-write=PASS
    CONCLUSION: 未写 accepted,等导体请人签
YAML
expect 0 "a denial does not trip no-signoff-write" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/denial.yaml"

# nested metrics must be refused outright: a nested shape grows into a
# second eval, and the kernel forbids a second ledger.
cat > "${TMP}/badmetrics.yaml" <<YAML
step: report-m
kind: review.report
agent: idev-reviewer
brief: {ticket_home: ${TICKET}, repo: ${TMP}, stage: code, must_read: x}
metrics:
  findings:
    blocking: 1
    minor: 2
report: {raw: "STATUS: PASS\nEVIDENCE: ${TICKET}/review.md\n"}
YAML
expect 2 "refuse nested metrics" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/badmetrics.yaml"
contains "metrics" "names the metrics shape problem"

# --- the §0 checks from boost.md, which only apply to idev-coder ---

# No declarations at all -> s0-declared FAIL.
cat > "${TMP}/s0none.yaml" <<YAML
step: code-s0a
kind: deliver.code_pass
agent: idev-coder
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: code
  must_read: conventions/coding.md
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    CONCLUSION: 改完了,但没交代 §0
YAML
expect 1 "flag a coder report with no §0 declarations" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/s0none.yaml"
contains "s0-declared" "names s0-declared"
contains "CHANGE_KIND" "lists which declarations are missing"

# A canon trigger with no T# in review.md -> canon-walked FAIL.
# CHANGE_KIND deliberately avoids 结构 so struct-gated stays PASS: a fixture
# that trips two checks proves neither.
cat > "${TMP}/s0canon.yaml" <<YAML
step: code-s0b
kind: deliver.code_pass
agent: idev-coder
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: code
  must_read: conventions/coding.md
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    CHANGE_KIND: 追加行为
    CANON_TRIGGER: 缓存
    TABLE_HIT: 零命中
YAML
expect 1 "flag a canon trigger that never reached review.md" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/s0canon.yaml"
contains "canon-walked" "names canon-walked"

# Positive: declarations complete, 无 trigger and 零命中 short-circuit the
# review.md lookups, so everything passes.
cat > "${TMP}/s0ok.yaml" <<YAML
step: code-s0c
kind: deliver.code_pass
agent: idev-coder
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: code
  must_read: conventions/coding.md
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    CHANGE_KIND: 追加行为
    CANON_TRIGGER: 无
    TABLE_HIT: 零命中
    CONCLUSION: 零命中,写了具体类型
YAML
expect 0 "a complete §0 declaration passes" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/s0ok.yaml"

# The §0 checks must not fire for other agents.
expect 0 "§0 checks do not apply to non-coder agents" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/good.yaml"
if printf '%s' "$LAST_OUT" | grep -q "s0-declared"; then
  bad "s0-declared fired for idev-reviewer"
else
  ok "s0-declared stayed out of the reviewer's record"
fi

say "4 failure signature"
cat > "${TMP}/log-a.txt" <<'LOG'
2026-10-12 22:30:01.123 ERROR run
java.lang.AssertionError: expected traceId to be present but was null
	at com.example.GatewayTest.shouldKeepTrace(GatewayTest.java:88)
LOG
# Same failure, different timestamp and line number: the signature must match.
cat > "${TMP}/log-b.txt" <<'LOG'
2026-10-13 09:14:57.987 ERROR run
java.lang.AssertionError: expected traceId to be present but was null
	at com.example.GatewayTest.shouldKeepTrace(GatewayTest.java:91)
LOG
# Assert it runs at all first. Comparing two outputs without this gives a
# false green: if the script crashes, both runs return the same error text
# and the equality check "passes".
expect 0 "sig runs" -- python3 "${S}/failure_signature.py" sig --log "${TMP}/log-a.txt"
SIG_A="$(python3 "${S}/failure_signature.py" sig --log "${TMP}/log-a.txt" 2>/dev/null)"
SIG_B="$(python3 "${S}/failure_signature.py" sig --log "${TMP}/log-b.txt" 2>/dev/null)"
if [ -n "$SIG_A" ] && [ "$SIG_A" = "$SIG_B" ]; then
  ok "signature is stable across timestamp and line number"
  printf '       %s\n' "$SIG_A"
else
  bad "signature differs across runs of the same failure"
  printf '       a: %s\n       b: %s\n' "$SIG_A" "$SIG_B" >&2
fi

# A genuinely different failure must NOT collapse into the same signature.
cat > "${TMP}/log-c.txt" <<'LOG'
2026-10-13 09:20:00.000 ERROR run
java.lang.NullPointerException: Cannot invoke "Order.total()" because order is null
	at com.example.OrderTest.shouldSum(OrderTest.java:12)
LOG
SIG_C="$(python3 "${S}/failure_signature.py" sig --log "${TMP}/log-c.txt" 2>/dev/null)"
if [ -n "$SIG_C" ] && [ "$SIG_A" != "$SIG_C" ]; then
  ok "a different failure keeps a different signature"
else
  bad "two different failures collapsed into one signature (over-normalized)"
  printf '       a: %s\n       c: %s\n' "$SIG_A" "$SIG_C" >&2
fi

expect 0 "no attempts yet -> check is quiet" -- \
  python3 "${S}/failure_signature.py" --repo "$TMP" check --feature "$FEATURE"
expect 0 "append 1" -- python3 "${S}/failure_signature.py" --repo "$TMP" append \
  --feature "$FEATURE" --log "${TMP}/log-a.txt" --delta 5
expect 0 "append 2" -- python3 "${S}/failure_signature.py" --repo "$TMP" append \
  --feature "$FEATURE" --log "${TMP}/log-b.txt" --delta 7
# Third identical signature crosses the tripwire: append itself returns 2.
expect 2 "third same signature trips the wire" -- \
  python3 "${S}/failure_signature.py" --repo "$TMP" append \
  --feature "$FEATURE" --log "${TMP}/log-a.txt" --delta 3
expect 2 "check agrees the wire is crossed" -- \
  python3 "${S}/failure_signature.py" --repo "$TMP" check --feature "$FEATURE"
contains "escalate" "tells you to escalate instead of patching again"

say "5 hypothesis ledger"
expect 0 "add H1 with a case" -- python3 "${S}/hypothesis.py" --repo "$TMP" add \
  --feature "$FEATURE" --claim "gateway drops X-Trace" --case "curl with header, assert downstream log"
expect 0 "check passes while open" -- \
  python3 "${S}/hypothesis.py" --repo "$TMP" check --feature "$FEATURE"

# proven without repro -> finding
expect 1 "proven without repro is rejected" -- python3 "${S}/hypothesis.py" --repo "$TMP" set \
  --feature "$FEATURE" --id H1 --status proven
contains "proven-needs-repro" "names proven-needs-repro"

# repro yes but still no evidence -> finding
expect 1 "proven without evidence is rejected" -- python3 "${S}/hypothesis.py" --repo "$TMP" set \
  --feature "$FEATURE" --id H1 --repro yes
contains "proven-needs-evidence" "names proven-needs-evidence"

expect 0 "proven with repro and evidence passes" -- python3 "${S}/hypothesis.py" --repo "$TMP" set \
  --feature "$FEATURE" --id H1 --evidence "${TICKET}/review.md"

# an open hypothesis with no case, followed by another -> case-before-next
python3 "${S}/hypothesis.py" --repo "$TMP" add --feature "$FEATURE" --claim "no case yet" >/dev/null 2>&1
python3 "${S}/hypothesis.py" --repo "$TMP" add --feature "$FEATURE" --claim "jumped ahead" --case "c" >/dev/null 2>&1
expect 1 "case-before-next fires" -- \
  python3 "${S}/hypothesis.py" --repo "$TMP" check --feature "$FEATURE"
contains "case-before-next" "names case-before-next"
expect 0 "list works" -- python3 "${S}/hypothesis.py" --repo "$TMP" list --feature "$FEATURE"

say "6 metrics"
expect 0 "metrics over the temp checkout" -- python3 "${S}/agent-metrics.py" --repo "$TMP"
contains "按 agent" "metrics has the per-agent table"
contains "p50" "metrics reports the duration distribution"
contains "从未使用" "metrics reports never-used registry rows"
expect 0 "metrics --signal" -- python3 "${S}/agent-metrics.py" --repo "$TMP" --signal
contains "signal=" "signal line is printed"
expect 0 "metrics --by kind" -- python3 "${S}/agent-metrics.py" --repo "$TMP" --by kind
expect 0 "metrics --trend" -- python3 "${S}/agent-metrics.py" --repo "$TMP" --trend
contains "趋势" "trend table is printed"
expect 0 "metrics --unused" -- python3 "${S}/agent-metrics.py" --repo "$TMP" --unused

say "7 agents-check negatives (a checker nobody tests is a checker nobody should trust)"

# Each case gets its own directory with one deliberately broken definition.
# --agents-dir skips the roster check, so only the per-file checks fire.
#
# mkbad sets BAD rather than printing the path. Wrapping a heredoc in $(...)
# makes bash count parentheses inside the heredoc *body*, so a fixture
# containing a literal "BLOCKED(" silently broke this whole script's lexing
# — `bash -n` reported an unclosed quote 300 lines later. See
# references/failure-modes.md.
mkbad() {   # mkbad <slug> <filename>; file body on stdin; sets BAD
  BAD="${TMP}/bad-$1"
  mkdir -p "$BAD"
  cat > "${BAD}/$2"
}

BODY='正文需要含这些标记:STATUS: EVIDENCE: CHECKS: SUGGEST: BLOCKED('

mkbad noname idev-reviewer.md <<MD
---
description: 缺 name
model: inherit
readonly: false
tools: Read, Bash
---
${BODY}
MD
expect 1 "missing name is caught" -- python3 "${S}/agents-check.py" --agents-dir "$BAD"
contains "no name field" "names the missing-name problem"

mkbad nodesc idev-reviewer.md <<MD
---
name: idev-reviewer
model: inherit
readonly: false
tools: Read, Bash
---
${BODY}
MD
expect 1 "missing description is caught" -- python3 "${S}/agents-check.py" --agents-dir "$BAD"
contains "no description" "names the missing-description problem"

mkbad readonly idev-coder.md <<MD
---
name: idev-coder
description: readonly would break it in Cursor
model: inherit
readonly: true
tools: Read, Bash, Write, Edit
---
${BODY}
MD
expect 1 "readonly: true is caught" -- python3 "${S}/agents-check.py" --agents-dir "$BAD"
contains "readonly" "names the readonly problem"

mkbad notools idev-reviewer.md <<MD
---
name: idev-reviewer
description: omitting tools inherits Edit, voiding the ban
model: inherit
readonly: false
---
${BODY}
MD
expect 1 "omitted tools is caught for a banned-tool agent" -- \
  python3 "${S}/agents-check.py" --agents-dir "$BAD"
contains "must list tools" "explains that omitting tools voids the ban"

mkbad banned idev-reviewer.md <<MD
---
name: idev-reviewer
description: reviewer must never hold Edit
model: inherit
readonly: false
tools: Read, Bash, Edit
---
${BODY}
MD
expect 1 "a forbidden tool is caught" -- python3 "${S}/agents-check.py" --agents-dir "$BAD"
contains "forbids" "names the forbidden tool"

mkbad noreport idev-reviewer.md <<'MD'
---
name: idev-reviewer
description: report format drifted away from what delegation.py parses
model: inherit
readonly: false
tools: Read, Bash
---
STATUS: 有,但缺 EVIDENCE 与 SUGGEST,也没有分类后缀
CHECKS: 有
MD
expect 1 "a drifted report format is caught" -- python3 "${S}/agents-check.py" --agents-dir "$BAD"
contains "report format" "names the report-format drift"

# Positive: Claude Code accepts a block sequence for tools. Reading that as
# "no tools field" would report a narrowing as missing when it is right there.
mkbad listform idev-reviewer.md <<MD
---
name: idev-reviewer
description: block-sequence tools must be recognized, not read as absent
model: inherit
readonly: false
tools:
  - Read
  - Grep
  - Bash
---
${BODY}
MD
expect 0 "block-sequence tools is recognized" -- python3 "${S}/agents-check.py" --agents-dir "$BAD"

say "8 workflow-agent driving a real run.yaml"

# The kernel driver resolves the ticket home from a git checkout. Without
# one, product_repo() returns None and run.yaml would land in the kernel's
# own state/workflow-runs — the real tree. So this only runs once .git is
# confirmed present; no checkout means skip, never "try anyway".
git init -q "$TMP" >/dev/null 2>&1 || true
if [ ! -d "${TMP}/.git" ]; then
  printf '  skip no git checkout in the temp dir; refusing to drive a run\n'
  printf '       (without it run.yaml would be written into the real kernel state/)\n'
else
  # lite-change has needs_ticket defaulting to true, so start refuses
  # without a deliver.yaml in the ticket home.
  cat > "${TICKET}/deliver.yaml" <<'YAML'
schema_version: 2
feature: smoke-change
stage: code
risk_tier: P1
aligned: false
by: ""
YAML

  # Run from inside the checkout so this does not depend on whether the
  # kernel's --repo flag sits on the main parser or the subcommand.
  # workflow.py directly now — the wrapper is gone, patch 0001 landed.
  wf() { (cd "$TMP" && python3 "${S}/workflow.py" "$@"); }

  expect 0 "resolve a kernel recipe" -- wf resolve lite-change
  contains "lite-change.yaml" "resolve names the recipe file"
  expect 0 "start a run" -- wf start lite-change --feature "$FEATURE"
  expect 0 "next runs" -- wf next --feature "$FEATURE"
  contains "NEXT" "next carries the kernel's NEXT line"
  contains "OPEN" "next carries the kernel's OPEN line"
  # lite-change opens with preflight.inputs, which the conductor keeps.
  contains "DELEGATE none" "the wrapper's DELEGATE line is present and correct"

  expect 0 "timeline joins run.yaml with the records" -- \
    python3 "${S}/delegation.py" --repo "$TMP" timeline --feature "$FEATURE"
  contains "lite-change" "timeline names the run"
  contains "不在 run.yaml 里" "timeline flags records whose step the recipe does not have"
  expect 0 "eval counts the conductor's own steps" -- \
    python3 "${S}/delegation.py" --repo "$TMP" eval --feature "$FEATURE"
  contains "conductor_kept" "eval reports conductor_kept from run.yaml"
fi

say "9 link-agents exposes the agents to a throwaway HOME"

# No swap, no kernel-reachability dance: the agent layer lives inside idev
# now, so this only links agents/*.md. The /idev skill is untouched.
HOME_B="${TMP}/home"
mkdir -p "$HOME_B"
LINK="${HOME_B}/.claude/agents/idev-reviewer.md"

# Prove the isolation: compare the real HOME before and after rather than
# checking whether it has a link (it may well have one already, which says
# nothing about this run).
REAL_LINK="${HOME}/.claude/agents/idev-reviewer.md"
if [ -e "$REAL_LINK" ] || [ -L "$REAL_LINK" ]; then REAL_BEFORE_H=present; else REAL_BEFORE_H=absent; fi

expect 0 "link the five agents" -- env HOME="$HOME_B" bash "${S}/link-agents.sh"
if [ -L "$LINK" ]; then
  ok "symlink created under the fake HOME"
else
  bad "no symlink at $LINK"
fi
if [ "$(ls -1 "${HOME_B}/.claude/agents" | wc -l | tr -d ' ')" = "5" ]; then
  ok "all five agents linked"
else
  bad "expected 5 agents, got $(ls -1 "${HOME_B}/.claude/agents" | wc -l | tr -d ' ')"
fi
# The skill side must be left alone entirely.
if [ ! -e "${HOME_B}/.claude/skills/idev" ] && [ ! -e "${HOME_B}/.cursor/skills/idev" ]; then
  ok "the skill entry was not touched (nothing to replace any more)"
else
  bad "link-agents created a skill mount; it should only link agents"
fi

if [ -e "$REAL_LINK" ] || [ -L "$REAL_LINK" ]; then REAL_AFTER_H=present; else REAL_AFTER_H=absent; fi
if [ "$REAL_BEFORE_H" = "$REAL_AFTER_H" ]; then
  ok "the real HOME is unchanged ($REAL_BEFORE_H)"
else
  bad "the real HOME changed: ${REAL_BEFORE_H} -> ${REAL_AFTER_H}"
fi

expect 0 "second run is idempotent" -- env HOME="$HOME_B" bash "${S}/link-agents.sh"
if printf '%s' "$LAST_OUT" | grep -q "HEAL"; then
  bad "second run re-created a link (not idempotent)"
else
  ok "second run did not re-create the links"
fi

rm -f "$LINK"
printf 'not a symlink\n' > "$LINK"
expect 1 "refuse to overwrite a real file" -- env HOME="$HOME_B" bash "${S}/link-agents.sh"
contains "not a symlink" "explains why it refused"
if [ "$(cat "$LINK")" = "not a symlink" ]; then
  ok "the real file was left intact"
else
  bad "the real file was clobbered"
fi
rm -f "$LINK"

expect 0 "unlink cleans up" -- env HOME="$HOME_B" bash "${S}/link-agents.sh" --unlink
if [ -L "${HOME_B}/.claude/agents/idev-coder.md" ]; then
  bad "unlink left a link in place"
else
  ok "unlink removed the links"
fi
expect 1 "reject an unknown flag" -- env HOME="$HOME_B" bash "${S}/link-agents.sh" --keep-idev

say "10 the two patches are already in the kernel"

# They were applied when the layer merged, so what matters now is that the
# kernel carries them — not that they still apply.
if grep -q 'kind_agents.delegate_line' "${S}/workflow.py"; then
  ok "workflow.py prints the DELEGATE line natively"
else
  bad "workflow.py lost the DELEGATE line"
fi
if grep -q '"agent"' "${S}/trace.py"; then
  ok "trace.py accepts calls[].kind: agent"
else
  bad "trace.py does not accept kind: agent"
fi
if [ -e "${S}/workflow-agent.py" ]; then
  bad "the wrapper workflow-agent.py is obsolete after the merge; remove it"
else
  ok "the obsolete wrapper is gone"
fi

say "11 agent-review drafts but never lands"

REVIEW_OUT="${TMP}/review-out"
# Count the real proposals first, to prove none were written there.
REAL_BEFORE="$(ls -1 "${REPO}/state/proposals" 2>/dev/null | wc -l | tr -d ' ')"

expect 0 "dry-run reports without writing" -- \
  bash "${S}/agent-review.sh" --repo "$TMP" --out "$REVIEW_OUT" --dry-run
contains "signal=" "dry-run states a signal verdict"
if [ -d "$REVIEW_OUT" ]; then
  bad "dry-run created $REVIEW_OUT"
else
  ok "dry-run left the output directory alone"
fi

expect 0 "a real run writes the receipt" -- \
  bash "${S}/agent-review.sh" --repo "$TMP" --out "$REVIEW_OUT"
if [ -f "${REVIEW_OUT}/reviews/agent-review-status.env" ]; then
  ok "status file written"
else
  bad "no status file at ${REVIEW_OUT}/reviews/agent-review-status.env"
fi

# The temp checkout accumulated check_fail >= 2 on idev-coder in section 3,
# so this must signal and therefore must draft.
if grep -q "^signal=yes" "${REVIEW_OUT}/reviews/agent-review-status.env" 2>/dev/null; then
  ok "signalled on a checkout with repeated check failures"
  DRAFT="$(ls -1 "${REVIEW_OUT}"/proposals/*.md 2>/dev/null | head -1)"
  if [ -z "$DRAFT" ]; then
    bad "signal=yes but no draft was written"
  else
    ok "a draft proposal was written"
    if grep -qiE "^status:[[:space:]]*draft" "$DRAFT"; then
      ok "the draft is marked draft"
    else
      bad "the draft is not marked draft"
    fi
    if grep -qiE "^status:[[:space:]]*landed" "$DRAFT"; then
      bad "the draft marked itself landed (only a person may do that)"
    else
      ok "the draft did not mark itself landed"
    fi
    if grep -q "人填" "$DRAFT"; then
      ok "the decision sections are left for a person"
    else
      bad "the draft decided what to change by itself"
    fi
  fi
else
  printf '  note no signal on this checkout; the draft path was not exercised\n'
fi

REAL_AFTER="$(ls -1 "${REPO}/state/proposals" 2>/dev/null | wc -l | tr -d ' ')"
if [ "$REAL_BEFORE" = "$REAL_AFTER" ]; then
  ok "the real state/proposals is untouched (${REAL_BEFORE} files)"
else
  bad "the real state/proposals changed: ${REAL_BEFORE} -> ${REAL_AFTER}"
fi

say "12 malformed input must not crash"

# These ledgers are written by hand and by agents, so bad yaml is a normal
# event. Every one of these used to be a traceback.

printf -- '- just\n- a\n- list\n' > "${TMP}/notmap.yaml"
expect 2 "refuse yaml whose top level is not a mapping" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/notmap.yaml"
contains "mapping" "says what is wrong"

printf 'step: [unclosed\n' > "${TMP}/broken.yaml"
expect 2 "refuse unparseable yaml" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/broken.yaml"

expect 2 "refuse a --file path that does not exist" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/nope.yaml"
contains "no such file" "names the missing file instead of a traceback"

# A broken record in the directory must be skipped, not fatal: the other
# records still have to render — that is when you need the view most.
DELEG="${TICKET}/workflow/delegations"
printf 'this: [is broken\n' > "${DELEG}/zz-broken-1.yaml"
expect 0 "timeline survives a broken record" -- \
  python3 "${S}/delegation.py" --repo "$TMP" timeline --feature "$FEATURE"
contains "idev-reviewer" "the good records still render"
contains "WARN" "the broken one is reported, not swallowed"
expect 0 "eval survives a broken record" -- \
  python3 "${S}/delegation.py" --repo "$TMP" eval --feature "$FEATURE"
expect 0 "metrics survives a broken record" -- python3 "${S}/agent-metrics.py" --repo "$TMP"
rm -f "${DELEG}/zz-broken-1.yaml"

# Valid yaml that is a list, not a mapping. A YAMLError guard alone lets
# this through — it parses fine, then .get() on a list raises.
printf -- '- one\n- two\n' > "${DELEG}/zz-listrecord-1.yaml"
expect 0 "metrics survives a record that is a valid yaml list" -- \
  python3 "${S}/agent-metrics.py" --repo "$TMP"
contains "not a mapping" "names the shape problem rather than parsing it"
expect 0 "timeline survives a yaml-list record" -- \
  python3 "${S}/delegation.py" --repo "$TMP" timeline --feature "$FEATURE"
# Exit 1, not 0: section 3 deliberately left records with real findings in
# this ticket. The point here is that the bad file is skipped while those
# findings are still reported — skipping must not turn into swallowing.
expect 1 "check skips the bad record and still reports the real findings" -- \
  python3 "${S}/delegation.py" --repo "$TMP" check --feature "$FEATURE"
contains "not a mapping" "the skipped file is named"
rm -f "${DELEG}/zz-listrecord-1.yaml"

# items holding the wrong shape must not crash the checker.
printf 'schema_version: 1\nfeature: %s\nitems: not-a-list\n' "$FEATURE" > "${TICKET}/hypotheses.yaml"
expect 0 "hypothesis check survives a malformed items field" -- \
  python3 "${S}/hypothesis.py" --repo "$TMP" check --feature "$FEATURE"

# A non-numeric delta must not crash the tripwire check — that check is the
# brake on a runaway fix loop, so it failing closed would be the worst case.
# The timestamp is generated, not fixed: a hard-coded one ages past the
# 15-minute line and turns this into a test of the clock.
cat > "${TICKET}/fix-attempts.yaml" <<YAML
schema_version: 1
feature: ${FEATURE}
attempts:
  - at: $(python3 -c 'import datetime as d; print(d.datetime.now().astimezone().isoformat(timespec="seconds"))')
    signature: "[X] [y] [z]"
    delta: 很多
    semantic_change: true
    result: FAIL
YAML
expect 0 "failure_signature check survives a non-numeric delta" -- \
  python3 "${S}/failure_signature.py" --repo "$TMP" check --feature "$FEATURE"

printf '\n== result\n'
printf '  pass %d   fail %d\n' "$PASS" "$FAIL"
if [ "$FAIL" -ne 0 ]; then
  echo "smoke FAIL"
  exit 1
fi
echo "smoke PASS"
exit 0
