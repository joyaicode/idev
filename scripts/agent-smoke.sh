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
IDEV_LIB="${REPO}/scripts/lib"
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
    FACTS: codegraph_context + 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    ASSUMED: 无
    EVIDENCE: ${TICKET}/review.md
    CONCLUSION: smoke
YAML
expect 0 "write a clean record" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/good.yaml"
contains "3m05s" "duration derived from started_at/finished_at (185s)"
expect 0 "check passes" -- python3 "${S}/delegation.py" --repo "$TMP" check --feature "$FEATURE"

# A record's filename is <step>-<attempt>.yaml, and attempt defaults to 1, so
# writing twice used to replace the first record and report OK — losing the
# failure that caused the retry. The second write is now BLOCKED.
expect 2 "the same step and attempt cannot be written twice" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/good.yaml"
contains "already records" "it says the record already exists"
contains "attempt: 2" "it says how to log a retry instead"
if grep -q "CONCLUSION: smoke" "${TICKET}/workflow/delegations/report-1.yaml"; then
  ok "the first record survived the second write"
else
  bad "the blocked write damaged the record it refused to replace"
fi
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
    FACTS: codegraph_context + 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    SCOPE: scripts/delegation.py:check_accuracy
    ASSUMED: 无
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
  artifact: /tmp/app.jar
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
    FACTS: codegraph_context + 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    SCOPE: scripts/delegation.py:check_accuracy
    ASSUMED: 无
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
    FACTS: codegraph_context + 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    SCOPE: scripts/delegation.py:check_accuracy
    ASSUMED: 无
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
    FACTS: codegraph_context + 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    SCOPE: scripts/delegation.py:check_accuracy
    ASSUMED: 无
    EVIDENCE: ${TICKET}/review.md
    CHANGE_KIND: 追加行为
    CANON_TRIGGER: 无
    TABLE_HIT: 零命中
    CONCLUSION: 零命中,写了具体类型
YAML
expect 0 "a complete §0 declaration passes" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/s0ok.yaml"

# The §0 checks must not fire for other agents.
# Its own step id, not a second write of good.yaml: since P0 a record is
# created with O_EXCL, so re-writing the same step and attempt is BLOCKED
# (exit 2) rather than silently replacing the first record.
cat > "${TMP}/s0other.yaml" <<YAML
step: report-s0
kind: review.report
agent: idev-reviewer
attempt: 1
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: code
  risk_tier: P1
  must_read: conventions/coding.md
  idev_root: ${REPO}
metrics:
  findings: 3
  blocking: 1
report:
  raw: |
    STATUS: PASS
    FACTS: codegraph_context + 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    ASSUMED: 无
    EVIDENCE: ${TICKET}/review.md
    CONCLUSION: smoke
YAML
expect 0 "§0 checks do not apply to non-coder agents" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/s0other.yaml"
if printf '%s' "$LAST_OUT" | grep -q "s0-declared"; then
  bad "s0-declared fired for idev-reviewer"
else
  ok "s0-declared stayed out of the reviewer's record"
fi

# --- boost.md 第零节: 本地事实优先 ---

# 只写"文档"不算第一手来源 —— 那正是它不可信的东西。
cat > "${TMP}/nofacts.yaml" <<YAML
step: classify-nf
kind: ops.classify
agent: idev-ops
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: ops
  must_read: ops/SKILL.md
  artifact: /tmp/app.jar
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    FACTS: 看了文档
    DOC_DRIFT: 无
    ASSUMED: 无
YAML
expect 1 "reject 文档-only as a fact source" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/nofacts.yaml"
contains "facts-first" "names facts-first"
contains "first-hand" "explains what counts as first-hand"

# 不交代文档漂移 —— 写"无"也算交代，缺这一行才是问题。
cat > "${TMP}/nodrift.yaml" <<YAML
step: classify-nd
kind: ops.classify
agent: idev-ops
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: ops
  must_read: ops/SKILL.md
  artifact: /tmp/app.jar
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    FACTS: codegraph_impact --depth 1 + 源码 scripts/trace.py:45
YAML
expect 1 "require a DOC_DRIFT declaration" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/nodrift.yaml"
contains "drift-declared" "names drift-declared"

# 文档类步骤不查这两项 —— 它的产出本身就是文档，"文档说"在那里不循环。
cat > "${TMP}/docsok.yaml" <<YAML
step: changelog-ok
kind: docs.changelog
agent: idev-deliver
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: code
  must_read: docs/SKILL.md
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    CONCLUSION: 文档类步骤无需交代 FACTS
YAML
expect 0 "facts checks do not apply to the docs agent" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/docsok.yaml"

# --- agent-accuracy.md: the borrowed guards ---

# Scope creep: CHANGED names a file SCOPE never did. This is the guard that
# catches "while I was in there I also fixed...".
cat > "${TMP}/creep.yaml" <<YAML
step: code-creep
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
    FACTS: 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    ASSUMED: 无
    SCOPE: a.py:f
    READ: a.py:f, b.py:g
    CHANGED: a.py:f, b.py:g
    REVERT: abc1234
YAML
expect 1 "catch a change outside the declared SCOPE" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/creep.yaml"
contains "scope-held" "names scope-held"
contains "b.py" "names the file that escaped scope"

# Blind edit: changed a file that was never read.
cat > "${TMP}/blind.yaml" <<YAML
step: code-blind
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
    FACTS: 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    ASSUMED: 无
    SCOPE: a.py:f, b.py:g
    READ: a.py:f
    CHANGED: a.py:f, b.py:g
    REVERT: abc1234
YAML
expect 1 "catch editing a file that was never read" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/blind.yaml"
contains "read-before-change" "names read-before-change"

# No revert anchor: undoing this delegation would be an excavation.
cat > "${TMP}/noanchor.yaml" <<YAML
step: code-noanchor
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
    FACTS: 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    ASSUMED: 无
    SCOPE: a.py:f
    READ: a.py:f
    CHANGED: a.py:f
YAML
expect 1 "require a REVERT anchor when files changed" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/noanchor.yaml"
contains "revert-anchor" "names revert-anchor"

# Fixing without having seen it red.
cat > "${TMP}/nored.yaml" <<YAML
step: fix-nored
kind: review.fix
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
    FACTS: 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    ASSUMED: 无
    SCOPE: a.py:f
    READ: a.py:f
    CHANGED: a.py:f
    REVERT: abc1234
YAML
expect 1 "require RED_FIRST on a fix step" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/nored.yaml"
contains "red-first" "names red-first"

# An undeclared assumption, on a non-coder agent.
cat > "${TMP}/noassume.yaml" <<YAML
step: classify-na
kind: ops.classify
agent: idev-ops
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: ops
  must_read: ops/SKILL.md
  artifact: /tmp/app.jar
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    FACTS: codegraph_context + 源码 scripts/trace.py:45
    DOC_DRIFT: 无
YAML
expect 1 "require an ASSUMED declaration" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/noassume.yaml"
contains "assumption-declared" "names assumption-declared"

# All four guards honoured, on a fix step: must pass.
cat > "${TMP}/cleanfix.yaml" <<YAML
step: fix-clean
kind: review.fix
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
    FACTS: 源码 scripts/delegation.py:250
    DOC_DRIFT: 无
    ASSUMED: 无
    CHANGE_KIND: 追加行为
    CANON_TRIGGER: 无
    TABLE_HIT: 零命中
    SCOPE: scripts/delegation.py:check_accuracy
    READ: scripts/delegation.py:check_accuracy
    CHANGED: scripts/delegation.py:check_accuracy
    REVERT: 5ded958
    RED_FIRST: 用例 guard-a 红过,日志 ${TICKET}/repl/guard-a-1.out
YAML
expect 0 "a fix honouring every guard passes" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/cleanfix.yaml"

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

# code-tier evidence (file:line) plus a guard case, so this exercises
# proven-needs-repro / proven-needs-evidence without tripping the newer
# tier and blast-radius checks.
# Exit 1 here, not 0: the blast radius is recorded in the next step, so at
# this moment proven-needs-blast-radius is the one finding left. Asserting 0
# would mean asserting the guard check does not exist.
expect 1 "code evidence clears the tier check, blast radius still pending" -- \
  python3 "${S}/hypothesis.py" --repo "$TMP" set \
  --feature "$FEATURE" --id H1 --evidence "scripts/delegation.py:250"
if printf '%s' "$LAST_OUT" | grep -q "proven-needs-code-evidence"; then
  bad "file:line was not accepted as code-tier evidence"
else
  ok "file:line clears the evidence-tier check"
fi
expect 0 "record its blast radius" -- python3 "${S}/hypothesis.py" --repo "$TMP" blast \
  --feature "$FEATURE" --id H1 --guard t_neighbour_unchanged
# The three-question report and a second evidence kind: both are required
# since references/rootcause-guards.md landed.
expect 0 "answer the three-question report" -- python3 "${S}/hypothesis.py" --repo "$TMP" set \
  --feature "$FEATURE" --id H1 --evidence "监控 traceId 命中率跌零 grafana/gw" \
  --impact "下游取不到 traceId,影响 09:00-09:30 全量请求的链路追踪" \
  --remedy "补回透传;验证用例 t-trace-passthrough;必要时回滚网关配置" \
  --window-source "告警时间"

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

BODY='正文需要含这些标记:STATUS: EVIDENCE: CHECKS: SUGGEST: GUIDE: DOMAIN: FACTS: DOC_DRIFT: ASSUMED: BLOCKED('

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
FACTS: 有
DOC_DRIFT: 无
ASSUMED: 无
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
if grep -q '"model"' "${S}/trace.py"; then
  ok "trace.py accepts calls[].kind: model"
else
  bad "trace.py does not accept kind: model"
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

say "13 repl: computation as evidence"

# The signoff guard is the one that matters most: a REPL must not become the
# way around workflow_spec.is_human(). Assert it refuses BEFORE executing.
cat > "${TMP}/bad-signoff.py" <<'PYSNIP'
import safeyaml
d = safeyaml.mapping(TICKET / "deliver.yaml") or {}
d["aligned"] = True
print("would have written aligned")
PYSNIP
expect 2 "refuse a snippet that writes a signoff field" -- \
  python3 "${S}/repl.py" --repo "$TMP" run --feature "$FEATURE" --step guard-a \
    --code "${TMP}/bad-signoff.py"
contains "signoff" "names the signoff problem"
contains "nothing was executed" "says it did not run"
if [ -e "${TICKET}/repl/guard-a-1.py" ]; then
  bad "a refused snippet was still saved"
else
  ok "a refused snippet leaves no transcript"
fi

# Writing a ticket YAML from a REPL is refused too.
cat > "${TMP}/bad-write.py" <<'PYSNIP'
(TICKET / "plan.yaml").write_text("cases: []\n")
PYSNIP
expect 2 "refuse a snippet that writes a ticket yaml" -- \
  python3 "${S}/repl.py" --repo "$TMP" run --feature "$FEATURE" --step guard-b \
    --code "${TMP}/bad-write.py"

expect 2 "refuse an empty snippet" -- \
  python3 "${S}/repl.py" --repo "$TMP" run --feature "$FEATURE" --step guard-c --code /dev/null

# The happy path: a computation whose source and output both land in the
# ticket, so someone else can re-run it.
cat > "${TMP}/count.py" <<'PYSNIP'
print("IDEV ok:", (IDEV / "SKILL.md").is_file())
print("TICKET ok:", TICKET.is_dir())
import safeyaml
print("safeyaml importable:", callable(safeyaml.mapping))
print("cases:", 3)
PYSNIP
expect 0 "run a real computation" -- \
  python3 "${S}/repl.py" --repo "$TMP" run --feature "$FEATURE" --step compute \
    --code "${TMP}/count.py" --note "smoke"
contains "EVIDENCE" "prints the evidence path"
contains "IDEV ok: True" "the preamble resolved IDEV"
contains "safeyaml importable: True" "the idev libs are on sys.path"
if [ -f "${TICKET}/repl/compute-1.py" ] && [ -f "${TICKET}/repl/compute-1.out" ]; then
  ok "source and transcript both saved"
else
  bad "missing ${TICKET}/repl/compute-1.{py,out}"
fi
if grep -q "exit: 0" "${TICKET}/repl/compute-1.out"; then
  ok "the transcript records the exit status"
else
  bad "no exit status in the transcript"
fi

# A failing snippet is recorded, not hidden — exit 1, transcript kept.
cat > "${TMP}/boom.py" <<'PYSNIP'
raise ValueError("boom")
PYSNIP
expect 1 "a failing snippet exits non-zero" -- \
  python3 "${S}/repl.py" --repo "$TMP" run --feature "$FEATURE" --step boom \
    --code "${TMP}/boom.py"
if grep -q "ValueError" "${TICKET}/repl/boom-1.out"; then
  ok "the failure is in the transcript, not swallowed"
else
  bad "the traceback was not recorded"
fi

# Runs are numbered, never overwritten.
expect 0 "a second run of the same step" -- \
  python3 "${S}/repl.py" --repo "$TMP" run --feature "$FEATURE" --step compute \
    --code "${TMP}/count.py"
if [ -f "${TICKET}/repl/compute-2.out" ]; then
  ok "the second run got its own index"
else
  bad "the second run overwrote the first"
fi

expect 0 "list the runs" -- python3 "${S}/repl.py" --repo "$TMP" list --feature "$FEATURE"
contains "compute-1" "list names the runs"
expect 0 "show a transcript" -- \
  python3 "${S}/repl.py" --repo "$TMP" show --feature "$FEATURE" --step compute
contains "stdout" "show prints the transcript"
expect 2 "show refuses an unknown step" -- \
  python3 "${S}/repl.py" --repo "$TMP" show --feature "$FEATURE" --step nope

say "14 stage-gate: the experts.md reject-lists"

# A gate nobody tested is a gate nobody should trust. Each stage gets one
# deliberately bad ticket and one clean one — findings must fire on the bad
# input AND stay quiet on the good, or the gate is just crying wolf.
GT="${TMP}/.idev/task/gate-bad"
mkdir -p "${GT}/verify"

cat > "${GT}/baseline.yaml" <<'YML'
schema_version: 1
goal: 让系统更稳定
objections:
  - 还没谈完
items:
  - {id: B1, must: 用 Redis 缓存用户态, acceptance: 响应要流畅}
  - {id: B2, must: 记审计日志}
YML
expect 1 "req-review catches vague acceptance and solution-as-requirement" -- \
  python3 "${S}/stage-gate.py" --repo "$TMP" --feature gate-bad --stage req-review
contains "untestable-acceptance" "names the vague acceptance"
contains "solution-as-requirement" "names the solution smuggled into a requirement"
contains "no-acceptance" "names the item with no acceptance at all"
contains "open-objections" "names the unresolved objections"

cat > "${GT}/req.yaml" <<'YML'
slices:
  - {id: S1, baseline_item_id: B1, points: 13}
  - {id: S2, must: 顺手加个导出}
YML
expect 1 "req catches oversized stories and unanchored slices" -- \
  python3 "${S}/stage-gate.py" --repo "$TMP" --feature gate-bad --stage req
contains "story-too-big" "names the 13-point story"
contains "unanchored-slice" "names the slice with no baseline item"
contains "dropped-baseline-item" "names the baseline item nobody covers"

cat > "${GT}/arch.yaml" <<'YML'
include: [src/a.py, src/b.py]
case_intents:
  - {id: CI1}
YML
expect 1 "arch catches a missing impact set and no rollback" -- \
  python3 "${S}/stage-gate.py" --repo "$TMP" --feature gate-bad --stage arch
contains "no-impact" "names the missing impact_candidates"
contains "no-rollback" "names the missing rollback path"

cat > "${GT}/review.md" <<'YML'
编码规范: P? 待定
C7 命中,待改下轮处理
YML
expect 1 "code catches placeholder codes and logged-not-fixed hits" -- \
  python3 "${S}/stage-gate.py" --repo "$TMP" --feature gate-bad --stage code
contains "placeholder-codes" "names the P? placeholder"
contains "hit-not-applied" "names the hit deferred to next round"

cat > "${GT}/verify/plan.yaml" <<'YML'
cases:
  - {id: c1, status: PASS, assert: 接口不报错}
YML
expect 1 "test catches a weak assertion and a PASS with no evidence" -- \
  python3 "${S}/stage-gate.py" --repo "$TMP" --feature gate-bad --stage test
contains "weak-assertion" "names the 不报错 assertion"
contains "pass-without-evidence" "names the evidence-free PASS"

cat > "${GT}/ops.yaml" <<'YML'
phenomenon: 页面空白
kind: unknown
root_cause: 应该是缓存没刷
YML
expect 1 "ops catches an unreproduced root cause" -- \
  python3 "${S}/stage-gate.py" --repo "$TMP" --feature gate-bad --stage ops
contains "rootcause-without-repro" "names the unreproduced root cause"
contains "conclusion-before-classify" "names the conclusion before classification"
contains "scene-incomplete" "names the incomplete scene"

# The other direction: a compliant ticket must come back clean, or findings
# become noise people learn to ignore.
GK="${TMP}/.idev/task/gate-ok"
mkdir -p "${GK}/verify"
cat > "${GK}/baseline.yaml" <<'YML'
schema_version: 1
goal: 登录失败时给出可定位的提示
items:
  - id: B1
    must: 登录失败提示
    acceptance: 3 秒内返回带错误码的提示
    ui:
      screen: 登录页
      intent: 用户输错密码后知道该怎么办
      fields:
        - {name: password, label: 密码, type: password, required: true, on_invalid: 字段下方红字「请输入密码」}
      actions:
        - name: 登录
          primary: true
          on_success: 跳转工作台
          on_failure: 留在本页,错误码 AUTH_401 显示在表单上方
          on_pending: 按钮禁用,不允许重复提交
      states:
        loading: 骨架屏,不显示空数据文案
        error: 网络失败显示「网络不可用,请重试」与重试按钮
YML
cat > "${GK}/req.yaml" <<'YML'
slices:
  - {id: S1, baseline_item_id: B1, must: 登录失败提示, points: 5}
YML
cat > "${GK}/arch.yaml" <<'YML'
include: [src/auth.py]
impact_candidates:
  - {path: src/login_handler.py, hop: 1}
rollback: feature flag auth_msg_v2,关掉即回旧行为
case_intents:
  - {id: CI1, baseline_item_id: B1}
YML
cat > "${GK}/review.md" <<'YML'
编码规范: §1 零命中;§2 已扫;T# 无。五轴 / 栈指南 / 增强扫描已跑。
YML
cat > "${GK}/verify/plan.yaml" <<'YML'
cases:
  - {id: c1, baseline_item_id: B1, status: PASS, evidence: target/verify/c1/run.log,
     assert: 密码错误时 3 秒内收到错误码 AUTH_401}
YML
cat > "${GK}/ops.yaml" <<'YML'
phenomenon: 登录提示缺失
env: test
artifact: 已发布包 v1.2.3
observable: 网关日志
kind: feature
repro: yes
root_cause: 错误码未透传,固定它可红绿切换
YML
expect 0 "a compliant ticket passes every stage" -- \
  python3 "${S}/stage-gate.py" --repo "$TMP" --feature gate-ok --all
contains "没发现 ≠ 没问题" "PASS still says machine silence is not approval"

expect 0 "--list explains what each stage checks" -- python3 "${S}/stage-gate.py" --list
expect 2 "refuse a feature with no ticket home" -- \
  python3 "${S}/stage-gate.py" --repo "$TMP" --feature nope --stage req

say "15 realign: after the baseline moved"

# The dangerous case this exists for: a PASS case still anchored to an item
# the correction removed, so new requirements get validated by old evidence.
RA="${TMP}/.idev/task/realign-bad"
mkdir -p "${RA}/verify"
cat > "${RA}/baseline.yaml" <<'YML'
revision: 2
sealed: false
items:
  - {id: B3, must: 登录失败给错误码, acceptance: 3 秒内 AUTH_401}
YML
cat > "${RA}/deliver.yaml" <<'YML'
stage: req-review
reopen_baseline: true
aligned: true
last_rewind: {origin: req, note: 需求订正}
semantic_gate:
  arch: {passed: true, by: p}
YML
cat > "${RA}/req.yaml" <<'YML'
baseline_revision: 1
accepted: true
slices:
  - {id: S1, baseline_item_id: B1, must: 旧需求}
YML
cat > "${RA}/arch.yaml" <<'YML'
baseline_revision: 1
accepted: true
case_intents: [{id: CI1, baseline_item_id: B1}]
YML
cat > "${RA}/verify/plan.yaml" <<'YML'
accepted: true
cases:
  - {id: c1, baseline_item_id: B1, status: PASS, evidence: logs/c1.log}
YML
expect 1 "realign finds drift after a reopen" -- \
  python3 "${S}/realign.py" --repo "$TMP" --feature realign-bad
contains "baseline_revision=1" "names the artifact built on the old revision"
contains "B1" "names the vanished item the artifacts still point at"
contains "证的是旧需求" "flags the PASS that proves a removed requirement"
contains "已失效,但仍是 true" "flags the signoffs the schema voided"
contains "没有 slice 覆盖" "flags the corrected item nobody decomposed"

expect 1 "realign --plan gives a forward redo order" -- \
  python3 "${S}/realign.py" --repo "$TMP" --feature realign-bad --plan
contains "从 req 开始" "starts from the earliest drifting stage"
contains "停问点" "keeps the human gates in the redo path"

# Aligned ticket: quiet, or the findings become noise.
RK="${TMP}/.idev/task/realign-ok"
mkdir -p "${RK}/verify"
cat > "${RK}/baseline.yaml" <<'YML'
revision: 2
sealed: true
items: [{id: B3, must: 登录失败给错误码, acceptance: 3 秒内 AUTH_401}]
YML
cat > "${RK}/deliver.yaml" <<'YML'
stage: code
baseline_revision: 2
semantic_gate: {req: {passed: true, by: p}, arch: {passed: true, by: p}}
YML
cat > "${RK}/req.yaml" <<'YML'
baseline_revision: 2
accepted: true
slices: [{id: S1, baseline_item_id: B3, must: 登录失败给错误码}]
YML
cat > "${RK}/arch.yaml" <<'YML'
baseline_revision: 2
accepted: true
case_intents: [{id: CI1, baseline_item_id: B3}]
YML
cat > "${RK}/verify/plan.yaml" <<'YML'
accepted: true
cases: [{id: c1, baseline_item_id: B3, status: PASS, evidence: logs/c1.log}]
YML
expect 0 "an aligned ticket comes back clean" -- \
  python3 "${S}/realign.py" --repo "$TMP" --feature realign-ok
contains "对准 ≠ 做对了" "PASS still says alignment is not correctness"
expect 0 "--plan on an aligned ticket says nothing to redo" -- \
  python3 "${S}/realign.py" --repo "$TMP" --feature realign-ok --plan

expect 2 "refuse a feature with no ticket home" -- \
  python3 "${S}/realign.py" --repo "$TMP" --feature nope

say "16 artifact-match: is the source the build that is running"

# Needs git and zip to build a real jar; skip rather than fake it.
if ! command -v zip >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then
  printf '  skip zip or git missing; artifact matching not covered\n'
else
  AM="${TMP}/am"
  mkdir -p "$AM"
  (
    cd "$AM"
    git init -q .
    echo one > a.txt && git add -A
    git -c user.email=t@t -c user.name=t commit -qm one
    git rev-parse HEAD > "${TMP}/c1"
    echo two > b.txt && git add -A
    git -c user.email=t@t -c user.name=t commit -qm two
    git rev-parse HEAD > "${TMP}/c2"
  ) >/dev/null 2>&1
  C1="$(cat "${TMP}/c1")"
  C2="$(cat "${TMP}/c2")"

  mkjar() {   # mkjar <commit> <out.jar>
    local d
    d="$(mktemp -d)"
    mkdir -p "$d/BOOT-INF/classes" "$d/META-INF"
    printf 'git.commit.id.full=%s\ngit.branch=main\n' "$1" > "$d/BOOT-INF/classes/git.properties"
    printf 'Manifest-Version: 1.0\nImplementation-Version: 1.2.3\n' > "$d/META-INF/MANIFEST.MF"
    echo x > "$d/BOOT-INF/classes/A.class"
    (cd "$d" && zip -qr "$2" .)
  }
  mkjar "$C2" "${TMP}/match.jar"
  mkjar "$C1" "${TMP}/old.jar"

  expect 0 "same commit is a MATCH" -- \
    python3 "${S}/artifact-match.py" --artifact "${TMP}/match.jar" --repo "$AM"
  contains "MATCH" "states the verdict"
  contains "读源码得到的逻辑就是运行时的逻辑" "says source may be trusted here"

  expect 1 "an older artifact is AHEAD" -- \
    python3 "${S}/artifact-match.py" --artifact "${TMP}/old.jar" --repo "$AM"
  contains "源码比产物新 1 个提交" "counts how far the source moved"
  contains "b.txt" "names the file changed since the build"
  # The suspect list drops ticket/doc/test paths, but must NOT drop things
  # that actually get packaged — hiding the real culprit is worse than the
  # noise. Filtering is by location, never by extension.
  python3 - <<'PYX'
import importlib.util, sys, pathlib
spec = importlib.util.spec_from_file_location("am", "scripts/artifact-match.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
cases = [("src/auth/login.py", False), (".idev/task/x/req.yaml", True),
         ("src/main/resources/messages.txt", False), ("src/config.json", False),
         ("e2e/flows/a.spec.ts", True), ("docs/guide.md", True),
         ("package-lock.json", True), ("src/test/java/T.java", True)]
bad = [f for f, want in cases if bool(m.NOT_SHIPPED.search(f)) != want]
sys.exit(1 if bad else 0)
PYX
  if [ $? -eq 0 ]; then
    ok "the suspect filter keeps packaged files and drops ticket paths"
  else
    bad "the suspect filter misclassifies a path"
  fi
  contains "不要用当前源码的逻辑解释线上现象" "refuses reasoning from newer source"

  # No build identity at all must be UNKNOWN, and UNKNOWN is not a pass.
  BD="$(mktemp -d)"
  echo x > "$BD/A.class"
  (cd "$BD" && zip -q "${TMP}/bare.jar" A.class)
  expect 1 "an artifact with no identity is UNKNOWN" -- \
    python3 "${S}/artifact-match.py" --artifact "${TMP}/bare.jar" --repo "$AM"
  contains "UNKNOWN" "states the verdict"
  contains "这不是放行" "refuses to treat UNKNOWN as a pass"
  contains "假想臆断" "names what assuming sameness would be"

  expect 2 "refuse a missing artifact" -- \
    python3 "${S}/artifact-match.py" --artifact "${TMP}/nope.jar" --repo "$AM"
fi

# The ops report must carry the verdict — for kind=feature only, since
# onboard / runtime are handed off and patrol replays a registered pack.
cat > "${TMP}/ops-noart.yaml" <<YAML
step: classify-noart
kind: ops.classify
agent: idev-ops
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: ops
  must_read: ops/SKILL.md
  artifact: /tmp/app.jar
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    KIND: feature
    FACTS: codegraph_context + 源码 scripts/trace.py:45
    DOC_DRIFT: 无
    ASSUMED: 无
YAML
expect 1 "a feature defect must confirm the artifact" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/ops-noart.yaml"
contains "artifact-verified" "names artifact-verified"

cat > "${TMP}/ops-handoff.yaml" <<YAML
step: classify-handoff
kind: ops.classify
agent: idev-ops
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: ops
  must_read: ops/SKILL.md
  artifact: /tmp/app.jar
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    KIND: onboard
    FACTS: 源码 scripts/trace.py:45
    DOC_DRIFT: 无
    ASSUMED: 无
YAML
expect 0 "a handoff kind does not need the artifact check" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/ops-handoff.yaml"

say "17 root-cause rigour: evidence tier, candidates, blast radius"

# Its own checkout and ticket: section 5 drives the same ledger, and two
# sections sharing one ticket means adding a field in one silently changes
# what the other asserts.
RR_REPO="$(mktemp -d)"
git init -q "$RR_REPO" >/dev/null 2>&1 || true
RR_HOME="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$RR_REPO" --feature rigour --key task 2>/dev/null)"
mkdir -p "${RR_HOME:?rigour ticket home unresolved}"
H() {  # subcommand first, then --feature: argparse puts it on the subparser
  local sub="$1"; shift
  python3 "${S}/hypothesis.py" --repo "$RR_REPO" "$sub" --feature rigour "$@"
}

# A log proves the symptom happened; it does not explain why. Calling that a
# root cause is the mistake this tier check exists for.
expect 0 "add a hypothesis" -- H add \
  --claim "网关丢了 X-Trace" --case "curl 带头,断言下游日志"
expect 1 "proving on log evidence alone is refused" -- H set \
  --id H1 --evidence "logs/gw.log" --repro yes --status proven
contains "proven-needs-code-evidence" "names the evidence-tier finding"
contains "file:line" "says what would count"
contains "blast-radius" "also wants the blast-radius cases"

# file:line reaches the code tier — now only the blast radius is missing.
expect 1 "code evidence still needs a blast radius" -- H set \
  --id H1 --evidence "src/gateway/filter.py:88"
contains "proven-needs-blast-radius" "names the blast-radius finding"
CT_OUT="$(H check 2>&1)"
if printf '%s' "$CT_OUT" | grep -q "proven-needs-code-evidence"; then
  bad "file:line was not recognised as code-tier evidence"
else
  ok "file:line counts as code-tier evidence"
fi

expect 0 "record the blast radius" -- H blast --id H1 \
  --guard t_trace_passthrough --baseline t_before_fix
# rootcause-guards.md also asks for a second evidence kind and the
# three-question report before a root cause counts as answered.
contains "guard" "reports the guard count"
expect 0 "complete the answer" -- H set --id H1 \
  --evidence "监控 traceId 命中率跌零 grafana/gw" \
  --impact "下游取不到 traceId,影响该时间窗全量请求的链路追踪" \
  --remedy "补回透传;验证用例 t-trace-passthrough" --window-source "告警时间"
# Now everything the checks ask for is on file: code-tier evidence, a repro,
# and a guard case.
expect 0 "a proven hypothesis with code evidence and guards passes" -- \
  H check

# One proven hypothesis and nothing ruled out is a warning, not a failure:
# the first guess being right is possible, just less common than nobody
# having written the alternatives down.
# The lone-proven warning is exercised on its own feature, since this
# ticket already carries hypotheses from section 5.
# Its own checkout: by this point $TMP carries a git repo, a driven run and
# a dozen ledgers from earlier sections. A case about "a ledger with exactly
# one hypothesis" must not depend on any of that.
RC_REPO="$(mktemp -d)"
git init -q "$RC_REPO" >/dev/null 2>&1 || true
RC_HOME="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$RC_REPO" --feature rc-lone --key task 2>/dev/null)"
mkdir -p "${RC_HOME:?rc-lone ticket home unresolved}"
L() { python3 "${S}/hypothesis.py" --repo "$RC_REPO" "$@"; }
L add --feature rc-lone --claim "单一猜想" --case "c" >/dev/null 2>&1 || true
L set --feature rc-lone --id H1 --evidence "src/a.py:10" --repro yes --status proven >/dev/null 2>&1 || true
L blast --feature rc-lone --id H1 --guard g >/dev/null 2>&1 || true
RC_OUT="$(L check --feature rc-lone 2>&1)"
if printf '%s' "$RC_OUT" | grep -q "没有任何被排除的候选"; then
  ok "a lone proven hypothesis is flagged as suspicious"
else
  bad "no warning about missing ruled-out candidates"
  printf '%s\n' "$RC_OUT" | sed 's/^/       | /' >&2
fi
rm -rf "$RC_REPO"

expect 0 "candidates lists what was considered" -- H candidates
contains "已证成" "groups by status"

# A ruled-out candidate with no reason recorded means the next round walks
# the same path again.
expect 0 "add a second candidate" -- H add \
  --claim "下游没读 header" --case "直接调下游断言"
expect 0 "rule it out with a reason" -- H set --id H2 \
  --status disproven --note "打开 debug 看到该分支没进,见 logs/h2.log"
expect 0 "candidates shows the ruled-out reason" -- H candidates
contains "已排除" "shows the ruled-out group"
contains "排除依据" "shows why it was ruled out"
CD_OUT="$(H candidates 2>&1)"
if printf '%s' "$CD_OUT" | grep -q "没有任何被排除的候选"; then
  bad "still complaining about missing candidates after one was ruled out"
else
  ok "the warning clears once a candidate is ruled out"
fi

expect 2 "blast refuses an unknown hypothesis" -- H blast \
  --id H99 --guard x
rm -rf "$RR_REPO"

say "18 ui-spec: requirements down to the interaction layer"

UI_REPO="$(mktemp -d)"
git init -q "$UI_REPO" >/dev/null 2>&1 || true
UH="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$UI_REPO" --feature login --key task 2>/dev/null)"
mkdir -p "${UH:?login ticket home unresolved}"

# Rules missing exactly the things that get skipped in practice, plus an
# implementation detail that does not belong in a requirement.
cat > "${UH}/baseline.yaml" <<'YML'
revision: 1
items:
  - id: B1
    must: 登录失败给出可定位提示
    acceptance: 3 秒内返回带错误码的提示
    ui:
      screen: 登录页
      intent: 用户输错密码后知道该怎么办
      fields:
        - {name: username, label: 用户名, type: text, required: true}
        - {name: password, label: 密码, type: el-input, rule: 非空}
      actions:
        - {name: 登录, primary: true, on_success: 跳转工作台}
YML
expect 1 "catch the gaps that matter in a ui rule set" -- \
  python3 "${S}/ui-spec.py" --repo "$UI_REPO" --feature login
contains "on_invalid" "asks what the user sees when input is wrong"
contains "on_failure" "asks what happens when the action fails"
contains "states 缺 loading" "asks what the screen looks like mid-request"
contains "重复提交就在这里发生" "explains why loading matters"
contains "el-input" "rejects an implementation detail in a requirement"

# A complete rule set renders.
cat > "${UH}/baseline.yaml" <<'YML'
revision: 2
items:
  - id: B1
    must: 登录失败给出可定位提示
    acceptance: 3 秒内返回带错误码的提示
    ui:
      screen: 登录页
      intent: 用户输错密码后知道该怎么办
      fields:
        - name: username
          label: 用户名
          type: text
          required: true
          rule: 非空,长度 4-32
          on_invalid: 字段下方红字「用户名需 4-32 字符」,焦点留在该字段
        - {name: password, label: 密码, type: password, required: true, on_invalid: 字段下方红字「请输入密码」}
      actions:
        - name: 登录
          primary: true
          on_success: 跳转工作台,顶部提示「欢迎回来」
          on_failure: 留在本页,错误码 AUTH_401 显示在表单上方
          on_pending: 按钮禁用并显示加载态,不允许重复提交
      states:
        loading: 骨架屏,不显示空数据文案
        error: 网络失败显示「网络不可用,请重试」与重试按钮
YML
expect 0 "a complete rule set generates the artifacts" -- \
  python3 "${S}/ui-spec.py" --repo "$UI_REPO" --feature login
contains "1 个界面 / 2 个输入项 / 1 个动作" "counts what it rendered"
contains "不是实现,也不是尺" "says the preview is not the measuring stick"

if [ -f "${UH}/ui/login.spec.json" ] && [ -f "${UH}/ui/login.html" ]; then
  ok "both the spec and the preview were written"
else
  bad "missing ${UH}/ui/login.{spec.json,html}"
fi
if grep -q '"format": "json-render/flat@1"' "${UH}/ui/login.spec.json"; then
  ok "the spec declares the json-render flat format"
else
  bad "the spec does not declare its format"
fi
# Semantic types only — picking components would put a product asset in the kernel.
if grep -q '"type": "field"' "${UH}/ui/login.spec.json" \
  && ! grep -qi 'el-input\|shadcn\|<div' "${UH}/ui/login.spec.json"; then
  ok "the spec names semantic types, not components"
else
  bad "the spec leaked component choices"
fi
# The preview must open offline: a review that needs a network is a review
# that gets skipped.
if ! grep -qE '(src|href)=' "${UH}/ui/login.html"; then
  ok "the preview is self-contained (no external references)"
else
  bad "the preview pulls in external resources"
fi
if grep -q "baseline.yaml" "${UH}/ui/login.html"; then
  ok "the preview names the baseline as the measuring stick"
else
  bad "the preview does not point back at the baseline"
fi

# --check validates without writing.
rm -rf "${UH}/ui"
expect 0 "--check validates without writing" -- \
  python3 "${S}/ui-spec.py" --repo "$UI_REPO" --feature login --check
if [ -f "${UH}/ui/login.html" ]; then
  bad "--check wrote the preview"
else
  ok "--check left the output alone"
fi

expect 0 "--schema documents the ui block" -- python3 "${S}/ui-spec.py" --schema
contains "on_invalid" "the schema explains the field-level rules"

# A backend-only requirement must not be forced to invent a ui block.
cat > "${UH}/baseline.yaml" <<'YML'
revision: 1
goal: 清理过期会话
items:
  - {id: B9, must: 后台定时清理过期会话, acceptance: 每小时清理一次}
YML
expect 0 "a backend-only requirement needs no ui block" -- \
  python3 "${S}/ui-spec.py" --repo "$UI_REPO" --feature login
UG_OUT="$(python3 "${S}/stage-gate.py" --repo "$UI_REPO" --feature login --stage req-review 2>&1)"
if printf '%s' "$UG_OUT" | grep -q "ui-not-specified"; then
  bad "stage-gate demanded a ui block for a backend requirement"
else
  ok "stage-gate leaves backend requirements alone"
fi
rm -rf "$UI_REPO"

say "19 ui-playbook: the lifecycle a UI flow must cover"

PB="$(mktemp -d)"
mkdir -p "${PB}/e2e/flows"

# The failure mode this exists for: a flow that changes before it reads, on
# an entity it did not create and did not tag.
cat > "${PB}/e2e/flows/bad.spec.ts" <<'TSX'
import { test, expect } from '@playwright/test';
test('实例管理', async ({ page }) => {
  await test.step('change: 改配置', async () => {
    await page.goto('/instance/1234567');
    await page.click('.btn-save');
  });
  await test.step('read: 看详情', async () => {
    await expect(page.locator('.name')).toContainText('x');
  });
  await test.step('create: 新建', async () => { await page.click('.btn-create'); });
});
TSX
expect 1 "catch a flow that skips the lifecycle" -- \
  python3 "${S}/ui-playbook.py" --repo "$PB"
contains "phase-order" "names the ordering problem"
contains "读回要在变更之前" "explains why read precedes change"
contains "untagged-entity" "names the untagged entity"
contains "missing-cleanup" "names the missing cleanup"

# A correct flow: cleanup in afterEach is written early but RUNS last, so
# judging order by text position must not punish it.
cat > "${PB}/e2e/flows/bad.spec.ts" <<'TSX'
import { test, expect } from '@playwright/test';
const TAG = `AUTOTEST_${Date.now()}`;
let id = '';
test.afterEach(async ({ request }) => {
  // @phase: cleanup
  if (id) await request.delete(`/api/instance/${id}`);
});
test('实例全生命周期', async ({ page }) => {
  await test.step('create: 新建实例', async () => {
    await page.fill('.name-input', TAG);
    id = (await page.locator('.instance-id').textContent()) ?? '';
    expect(id).not.toBe('');
  });
  await test.step('read: 读回只读信息', async () => {
    await expect(page.locator('.name')).toContainText(TAG);
  });
  await test.step('change: 改配置', async () => {
    await page.fill('.desc-input', 'changed');
    await expect(page.locator('.desc')).toContainText('changed');
  });
  await test.step('restore: 归位', async () => {
    await page.fill('.desc-input', '');
    await expect(page.locator('.desc')).toHaveText('');
  });
});
TSX
expect 0 "a complete lifecycle passes" -- python3 "${S}/ui-playbook.py" --repo "$PB"
contains "阶段齐 ≠ 测得对" "PASS still says structure is not correctness"

# An irreversible step may skip restore, but must say why.
cat > "${PB}/e2e/flows/approve.spec.ts" <<'TSX'
import { test, expect } from '@playwright/test';
const TAG = 'E2E_approve';
let id = '';
test.afterEach(async ({ request }) => {
  // @phase: cleanup
  if (id) await request.delete(`/api/order/${id}`);
});
test('审批单', async ({ page }) => {
  // @phase: create
  await page.fill('.name-input', TAG); id = 'x';
  // @phase: read
  await expect(page.locator('.status')).toContainText('pending');
  // @phase: change
  await page.click('.btn-approve');
  // @phase: restore (irreversible: 审批通过后不可撤回,预期状态为 approved)
  await expect(page.locator('.status')).toContainText('approved');
});
TSX
expect 0 "an irreversible flow may skip restore when it says why" -- \
  python3 "${S}/ui-playbook.py" --repo "$PB"

# Cleanup only on the happy path leaves debris.
cat > "${PB}/e2e/flows/leaky.spec.ts" <<'TSX'
import { test, expect } from '@playwright/test';
const TAG = 'AUTOTEST_leaky';
test('漏清理', async ({ page }) => {
  // @phase: create
  await page.fill('.n', TAG);
  // @phase: read
  await expect(page.locator('.n')).toContainText(TAG);
  // @phase: change
  await page.click('.s');
  // @phase: restore
  await page.click('.undo');
  // @phase: cleanup
  await page.click('.del');
});
TSX
expect 1 "catch cleanup that only runs on success" -- \
  python3 "${S}/ui-playbook.py" --repo "$PB"
contains "cleanup-not-guaranteed" "names the unguaranteed cleanup"
contains "下一轮继承垃圾" "explains the consequence"
rm -f "${PB}/e2e/flows/leaky.spec.ts"

# A flow that clicks through the UI and asserts nothing.
cat > "${PB}/e2e/flows/silent.spec.ts" <<'TSX'
import { test } from '@playwright/test';
const TAG = 'AUTOTEST_silent';
test.afterEach(async ({ request }) => {
  // @phase: cleanup
  await request.delete('/api/x');
});
test('无断言', async ({ page }) => {
  // @phase: create
  await page.fill('.n', TAG);
  // @phase: read
  await page.goto('/x');
  // @phase: change
  await page.click('.s');
  // @phase: restore
  await page.click('.undo');
});
TSX
expect 1 "catch a flow with no assertions" -- python3 "${S}/ui-playbook.py" --repo "$PB"
contains "no-assertion" "names the missing assertions"
contains "只是点了一遍界面" "says what such a flow actually does"
rm -f "${PB}/e2e/flows/silent.spec.ts"

expect 0 "--schema documents the contract" -- python3 "${S}/ui-playbook.py" --schema
contains "AUTOTEST" "the schema explains the tagging requirement"
expect 2 "refuse a repo with no e2e dir" -- python3 "${S}/ui-playbook.py" --repo "$TMP"
rm -rf "$PB"

say "20 ui-evolve: state conflicts while authoring a playbook"

EV="$(mktemp -d)"
mkdir -p "${EV}/e2e/flows"

# The example from the brief: one flow turns auth on, the next needs it off.
# Re-running never fixes this, which is why it has to be caught while writing.
cat > "${EV}/e2e/flows/a-auth.spec.ts" <<'TSX'
import { test, expect } from '@playwright/test';
// @switch: auth on
test('开启鉴权', async ({ page }) => { await page.click('.enable-auth'); expect(1).toBe(1); });
TSX
cat > "${EV}/e2e/flows/b-instance.spec.ts" <<'TSX'
import { test, expect } from '@playwright/test';
// @requires: auth off
test('实例列表', async ({ page }) => { await page.goto('/instance'); expect(1).toBe(1); });
TSX
expect 1 "catch a flow whose prerequisite an earlier flow destroys" -- \
  python3 "${S}/ui-evolve.py" --repo "$EV"
contains "前置状态被上游改掉了" "names the conflict in words a reader sees"
contains "重跑多少次都一样" "says re-running will not fix it"
contains "branch" "offers the branch restructuring"
contains "reorder" "offers the reorder restructuring"
contains "跑完之后遗留" "reports the leftover switch state"

# A declaration line must not be read as an action. `@requires: auth off`
# states a dependency; calling it a flip is a false positive, and false
# positives teach people to ignore findings.
EV_OUT="$(python3 "${S}/ui-evolve.py" --repo "$EV" 2>&1)"
if printf '%s' "$EV_OUT" | grep -q "b-instance.spec.ts → (后续全部)"; then
  bad "read @requires as an undeclared switch flip"
else
  ok "a @requires declaration is not mistaken for a flip"
fi

# reorder actually resolves it: the switch flow runs last, so everything
# depending on the default state runs first.
cat > "${EV}/e2e/flows/a-auth.spec.ts" <<'TSX'
import { test, expect } from '@playwright/test';
// @switch: auth on
// @order: last
test('开启鉴权', async ({ page }) => { await page.click('.enable-auth'); expect(1).toBe(1); });
TSX
expect 0 "the reorder fix resolves the conflict" -- python3 "${S}/ui-evolve.py" --repo "$EV"
contains "@order:last" "shows the reordered run"
contains "没冲突 ≠ 剧本够好" "PASS still says this is only one dimension"

# branch also resolves it: each flow self-contained on its own switch state.
rm -f "${EV}/e2e/flows/"*.spec.ts
cat > "${EV}/e2e/flows/auth-on.spec.ts" <<'TSX'
import { test, expect } from '@playwright/test';
// @switch: auth on
// @requires: auth on
test('鉴权开启下的列表', async ({ page }) => { await page.goto('/instance'); expect(1).toBe(1); });
TSX
cat > "${EV}/e2e/flows/auth-off.spec.ts" <<'TSX'
import { test, expect } from '@playwright/test';
// @switch: auth restore
test('默认状态下的列表', async ({ page }) => { await page.goto('/instance'); expect(1).toBe(1); });
TSX
expect 0 "the branch fix also resolves it" -- python3 "${S}/ui-evolve.py" --repo "$EV"

# An undeclared flip is invisible downstream.
cat > "${EV}/e2e/flows/c-sneaky.spec.ts" <<'TSX'
import { test, expect } from '@playwright/test';
test('悄悄关审批', async ({ page }) => { await page.click('.disable-approval'); expect(1).toBe(1); });
TSX
expect 1 "catch a switch flipped without a declaration" -- \
  python3 "${S}/ui-evolve.py" --repo "$EV"
contains "改了全局开关却没声明" "names the undeclared flip in words a reader sees"
contains "后续场景无法预见" "explains why declaring matters"

expect 0 "--schema documents the switch contract" -- python3 "${S}/ui-evolve.py" --schema
contains "@order: last" "the schema shows the reorder form"
contains "降低复杂度" "the schema names the tradeoff"
expect 2 "refuse a repo with no flows" -- python3 "${S}/ui-evolve.py" --repo "$TMP"
rm -rf "$EV"

say "21 link-agents: install to both Claude Code and Cursor"

# Run against a fake HOME so this never touches the real install.
LA_HOME="$(mktemp -d)"
expect 0 "install reaches both locations" -- env HOME="$LA_HOME" bash "${S}/link-agents.sh"
contains "两个位置" "says it installed to both"

for loc in ".claude/agents" ".cursor/agents"; do
  n=0
  for f in "${LA_HOME}/${loc}"/idev-*.md; do
    [ -L "$f" ] || continue
    n=$((n + 1))
  done
  if [ "$n" -ge 5 ]; then
    ok "${loc} has all five agents as symlinks"
  else
    bad "${loc} has $n agent symlinks, expected 5"
  fi
done

# Symlinks, not copies: editing the repo must change what both tools read.
if [ "$(readlink "${LA_HOME}/.cursor/agents/idev-coder.md")" = "${REPO}/agents/idev-coder.md" ]; then
  ok "the Cursor link points back at the repo"
else
  bad "the Cursor link does not point at the repo"
fi

expect 0 "--check reports a clean install" -- env HOME="$LA_HOME" bash "${S}/link-agents.sh" --check
contains "CHECK PASS" "says both locations are complete"

# A missing link must be reported, not silently healed by --check.
rm -f "${LA_HOME}/.cursor/agents/idev-ops.md"
expect 1 "--check notices a missing link" -- env HOME="$LA_HOME" bash "${S}/link-agents.sh" --check
contains "MISS idev-ops.md" "names the missing agent"
if [ -e "${LA_HOME}/.cursor/agents/idev-ops.md" ]; then
  bad "--check wrote something; it must only report"
else
  ok "--check changed nothing"
fi

# Re-running heals it.
expect 0 "re-running restores the missing link" -- env HOME="$LA_HOME" bash "${S}/link-agents.sh"
expect 0 "--check is clean again" -- env HOME="$LA_HOME" bash "${S}/link-agents.sh" --check

# A real file at the destination must be refused, never overwritten: that
# file belongs to someone, and clobbering it is unrecoverable.
rm -f "${LA_HOME}/.cursor/agents/idev-ops.md"
echo "someone else's agent" > "${LA_HOME}/.cursor/agents/idev-ops.md"
expect 1 "refuse to overwrite a real file" -- env HOME="$LA_HOME" bash "${S}/link-agents.sh"
contains "not a symlink" "says why it refused"
if grep -q "someone else" "${LA_HOME}/.cursor/agents/idev-ops.md"; then
  ok "the pre-existing file is intact"
else
  bad "the pre-existing file was destroyed"
fi
rm -f "${LA_HOME}/.cursor/agents/idev-ops.md"

# --unlink clears both locations and leaves non-symlinks alone.
env HOME="$LA_HOME" bash "${S}/link-agents.sh" >/dev/null 2>&1 || true
expect 0 "--unlink removes them" -- env HOME="$LA_HOME" bash "${S}/link-agents.sh" --unlink
left=0
for loc in ".claude/agents" ".cursor/agents"; do
  for f in "${LA_HOME}/${loc}"/idev-*.md; do
    [ -e "$f" ] && left=$((left + 1))
  done
done
if [ "$left" -eq 0 ]; then
  ok "both locations are clear after --unlink"
else
  bad "$left links survived --unlink"
fi

expect 1 "reject an unknown flag" -- env HOME="$LA_HOME" bash "${S}/link-agents.sh" --nope
contains "用法" "shows the usage line"
rm -rf "$LA_HOME"

say "22 req-ground: a requirement must land on existing code"

RG_REPO="$(mktemp -d)"
git init -q "$RG_REPO" >/dev/null 2>&1 || true
RH="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$RG_REPO" --feature login --key task 2>/dev/null)"
mkdir -p "${RH:?login ticket home unresolved}"

# No grounding at all, plus a half-filled one. The conflict with no grill
# question is the finding that matters most: experts.md calls leaving a
# known conflict out of the questions a reject.
cat > "${RH}/baseline.yaml" <<'YML'
revision: 1
items:
  - {id: B1, must: 登录失败给出可定位提示, acceptance: 3 秒内返回带错误码的提示}
  - id: B2
    must: 展示剩余重试次数
    acceptance: 3 次内显示
    grounding:
      touches: [src/auth/login.py]
      conflicts:
        - {where: src/auth/login.py:authenticate, existing: 统一返回 AUTH_FAILED}
    comparison:
      peers: [{name: 竞品A, behaviour: 显示剩余次数}]
      differs: 我们不显示
YML
expect 1 "catch a requirement never grounded in the code" -- \
  python3 "${S}/req-ground.py" --repo "$RG_REPO" --feature login
contains "no-grounding" "names the item with no grounding at all"
contains "reopen" "explains what finding this late costs"
contains "touches-not-anchored" "wants file:symbol, not a bare path"
contains "conflict-not-grilled" "a known conflict must become a question"
contains "拒过项" "cites why leaving it out is refused"
contains "differs-without-why" "a difference from a competitor needs a reason"
contains "differs-not-grilled" "a large difference must be discussed"
contains "no-boundary" "wants what is explicitly out of scope"

# Grounded, with both conflicts and the competitor difference raised as
# questions that actually exist in grill.md.
cat > "${RH}/grill.md" <<'YML'
# 待拷问
Q3. 区分「密码错」与「账号锁定」是否违反「不泄漏账号状态」?
Q5. 不给剩余重试次数,是否接受与竞品 A 的体验差距?
YML
cat > "${RH}/baseline.yaml" <<'YML'
revision: 1
items:
  - id: B1
    must: 登录失败给出可定位提示
    acceptance: 3 秒内返回带错误码的提示
    grounding:
      touches: [src/auth/login.py:authenticate, src/gateway/filter.py:AuthFilter]
      impact: [src/api/session.py:create_session]
      conflicts:
        - where: src/auth/login.py:authenticate
          existing: 现在统一返回 AUTH_FAILED,不区分原因
          tension: 本需求要区分原因,与既有的「不泄漏账号状态」相悖
          grill: Q3
      boundary: [不改第三方 SSO 回调, 不动既有错误码编号规则]
      direction: 与 ADR-012「可观测性优先」一致
    comparison:
      peers: [{name: 竞品A, behaviour: 区分并给剩余次数}]
      differs: 我们不给剩余重试次数
      why: 剩余次数可被用来枚举有效账号,见 ADR-007 威胁模型
      grill: Q5
YML
expect 0 "a grounded requirement passes" -- \
  python3 "${S}/req-ground.py" --repo "$RG_REPO" --feature login
contains "落地了 ≠ 读对了" "PASS still says the homework was only declared"

# A question id that does not exist in grill.md is a dangling promise.
python3 - "$RH" <<'PYX'
import pathlib, sys
p = pathlib.Path(sys.argv[1]) / "baseline.yaml"
p.write_text(p.read_text(encoding="utf-8").replace("grill: Q3", "grill: Q9"), encoding="utf-8")
PYX
expect 1 "catch a grill reference that does not exist" -- \
  python3 "${S}/req-ground.py" --repo "$RG_REPO" --feature login
contains "grill-ref-dangling" "names the dangling reference"

expect 0 "--probe says what to go read" -- \
  python3 "${S}/req-ground.py" --repo "$RG_REPO" --feature login --probe
contains "codegraph_impact" "gives the impact command"
contains "挂一条 grill 问句" "repeats that conflicts become questions"

expect 0 "--schema documents the grounding block" -- python3 "${S}/req-ground.py" --schema
contains "comparison" "the schema covers the competitor comparison"

# stage-gate only demands grounding once the baseline is sealed: a draft is
# still collecting, and nagging there would train people to ignore it.
cat > "${RH}/baseline.yaml" <<'YML'
revision: 1
sealed: false
goal: 登录失败时给出可定位的提示
items:
  - {id: B1, must: 后台清理会话, acceptance: 每小时 1 次}
YML
RG_OUT="$(python3 "${S}/stage-gate.py" --repo "$RG_REPO" --feature login --stage req-review 2>&1)"
if printf '%s' "$RG_OUT" | grep -q "not-grounded"; then
  bad "stage-gate demanded grounding on an unsealed draft"
else
  ok "an unsealed draft is not nagged about grounding"
fi
cat > "${RH}/baseline.yaml" <<'YML'
revision: 1
sealed: true
goal: 登录失败时给出可定位的提示
items:
  - {id: B1, must: 后台清理会话, acceptance: 每小时 1 次}
YML
expect 1 "stage-gate demands grounding once sealed" -- \
  python3 "${S}/stage-gate.py" --repo "$RG_REPO" --feature login --stage req-review
contains "not-grounded" "names the ungrounded sealed baseline"
rm -rf "$RG_REPO"

say "23 rootcause guards: an answer must be verifiable"

# The dangerous outcome is not "no answer", it is an answer that sounds
# reasonable and cannot be checked. Each guard blocks one way of sounding
# reasonable.
RC_REPO2="$(mktemp -d)"
git init -q "$RC_REPO2" >/dev/null 2>&1 || true
RH2="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$RC_REPO2" --feature guards --key task 2>/dev/null)"
mkdir -p "${RH2:?guards ticket home unresolved}"
G() { python3 "${S}/hypothesis.py" --repo "$RC_REPO2" "$@"; }

expect 0 "add a hypothesis naming a middle service" -- G add --feature guards \
  --claim "商品服务返回空" --case "curl 复现"
expect 1 "one evidence kind is not enough to prove" -- G set --feature guards \
  --id H1 --evidence "src/item/service.py:88" --repro yes --status proven
contains "proven-needs-two-sources" "names the single-source finding"
contains "互相印证" "says the two sources must corroborate"
contains "report-missing-impact" "wants the impact answer"
contains "report-missing-remedy" "wants the what-to-do answer"

# A middle service relaying someone else's failure is the classic wrong
# root cause in a distributed system.
G_OUT="$(G check --feature guards 2>&1)"
if printf '%s' "$G_OUT" | grep -q "root-cause-not-terminal"; then
  ok "warns that a middle service cannot be the whole root cause"
else
  bad "no warning about a non-terminal root cause"
fi

expect 1 "a second evidence kind clears that guard" -- G set --feature guards \
  --id H1 --evidence "监控 p99 突增 grafana/item"
G_OUT="$(G check --feature guards 2>&1)"
if printf '%s' "$G_OUT" | grep -q "proven-needs-two-sources"; then
  bad "still complaining after a second evidence kind"
else
  ok "two corroborating kinds satisfy the double-evidence guard"
fi

# A time window with no stated origin is how unrelated evidence gets in.
expect 1 "a time window must say where it came from" -- G set --feature guards \
  --id H1 --window "2026-10-15T09:00..2026-10-15T09:30"
contains "window-without-source" "names the unsourced window"
contains "无关证据" "explains what an open window lets in"
expect 1 "sourcing the window clears it" -- G set --feature guards --id H1 \
  --window-source "告警时间"
G_OUT="$(G check --feature guards 2>&1)"
if printf '%s' "$G_OUT" | grep -q "window-without-source"; then
  bad "window still unsourced after --window-source"
else
  ok "a sourced window is accepted"
fi

# The report answers three questions, not one.
expect 1 "still needs the three-question report" -- G set --feature guards \
  --id H1 --impact "商品详情页空白,09:00-09:30 全量读请求受影响"
contains "report-missing-remedy" "still wants the remedy"
G blast --feature guards --id H1 --guard t_neighbour >/dev/null 2>&1 || true
expect 0 "a complete answer passes" -- G set --feature guards --id H1 \
  --remedy "回滚 release-2026-10-15;验证用例 c-item-read"

# Ruling something out without saying how sends the next round down the
# same path.
expect 0 "add a second candidate" -- G add --feature guards \
  --claim "数据库连接池耗尽" --case "看连接数"
expect 1 "ruling out without proof is refused" -- G set --feature guards \
  --id H2 --status disproven
contains "disproven-needs-proof" "names the unproven exclusion"
contains "下一轮会重走这条路" "explains why the reason matters"
expect 0 "a reason clears it" -- G set --feature guards --id H2 \
  --note "连接数峰值 12/200,见 logs/pool.log"

# FACTS must name where a service name came from.
cat > "${TMP}/ops-recall.yaml" <<YAML
step: classify-recall
kind: ops.classify
agent: idev-ops
brief:
  ticket_home: ${TICKET}
  repo: ${TMP}
  stage: ops
  must_read: ops/SKILL.md
  artifact: /tmp/app.jar
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TICKET}/review.md
    KIND: onboard
    FACTS: 商品服务的缓存层
    DOC_DRIFT: 无
    ASSUMED: 无
YAML
expect 1 "a service name from recall is refused" -- \
  python3 "${S}/delegation.py" --repo "$TMP" write --feature "$FEATURE" --file "${TMP}/ops-recall.yaml"
contains "facts-sourced" "names the unsourced facts line"
contains "禁止凭经验编造" "says what is forbidden"
rm -rf "$RC_REPO2"

say "24 lessons: experience must pass a gate before it is authority"

LS_REPO="$(mktemp -d)"
git init -q "$LS_REPO" >/dev/null 2>&1 || true
LS_HOME="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$LS_REPO" --feature lsn --key task 2>/dev/null)"
mkdir -p "${LS_HOME:?lsn ticket home unresolved}"
L() {
  local sub="$1"; shift
  python3 "${S}/lessons.py" --repo "$LS_REPO" --feature lsn "$sub" "$@"
}

# Six questions or it is a process log, not decision knowledge.
expect 2 "refuse a lesson that answers fewer than six questions" -- \
  L add --scope "库存" --symptom "回写延迟"
contains "not-when" "names the boundary question"
contains "过程日志" "says what an incomplete lesson actually is"

expect 0 "accept a complete lesson as a candidate" -- L add \
  --scope "商品链路/库存回写" --symptom "回写延迟,下游读到旧值" \
  --evidence "kafka-lag 指标 + 幂等表无新记录" \
  --action "先核对消息积压与幂等记录,再看消费者" \
  --outcome "积压在生产侧,消费者正常" \
  --not-when "消费位点连续推进时不适用"
contains "candidate" "enters as a candidate"
contains "候选 ≠ 权威" "says a candidate is not authority"

# A model confirming its own conclusion is not confirmation — the same
# blacklist that guards signoff.
expect 2 "refuse an agent confirming its own lesson" -- \
  L promote --id L1 --by agent --repro logs/r.log
contains "模型确认自己的结论不叫确认" "says why the agent is refused"
expect 2 "refuse promotion without a reproduction" -- \
  L promote --id L1 --by wangwei794 --repro ""
contains "旁路复现" "requires the lesson was replayed"
expect 0 "a human plus a reproduction promotes it" -- \
  L promote --id L1 --by wangwei794 --repro "logs/replay-L1.log"
contains "authoritative" "reaches authority"
contains "不是既定答案" "still only advises"

# Recall advises; it must not read as an answer.
expect 0 "recall returns relevant lessons" -- L recall --scope "库存回写"
contains "不是答案" "frames lessons as advice"
contains "不适用于" "always shows the boundary"
contains "生搬硬套" "names the risk of reusing a conclusion blindly"

expect 0 "add a second, unconfirmed lesson" -- L add --event user-correction \
  --scope "商品链路/库存回写" --symptom "疑似消费者停滞" \
  --evidence "位点连续推进" --action "不要判为消费者停滞" \
  --outcome "实为生产侧突增" --not-when "位点停滞时则确为消费者问题"
expect 0 "an unconfirmed lesson is marked as such on recall" -- \
  L recall --scope "库存回写"
contains "未经人确认" "marks the candidate as unconfirmed"
contains "待验假设" "says to treat it as a hypothesis"

expect 0 "the ledger is clean" -- L check

# The gate is re-checked on read: editing the file by hand must not be able
# to smuggle a lesson into authority.
python3 - "$LS_HOME" <<'PYX'
import pathlib, sys
sys.path.insert(0, "scripts/lib")
import safeyaml
p = pathlib.Path(sys.argv[1]) / "lessons.yaml"
d = safeyaml.mapping(p)
d["lessons"][1]["status"] = "authoritative"
p.write_text(safeyaml.dump(d), encoding="utf-8")
PYX
expect 1 "catch a hand-edited promotion" -- L check
contains "入库门禁被绕过了" "says the gate was bypassed"
contains "没复现过不算验证" "names the missing reproduction"

expect 2 "retire needs a reason" -- L retire --id L1 --why ""
expect 0 "retire with a reason" -- L retire --id L1 --why "错误码已重构,该路径不存在"
expect 0 "a retired lesson drops out of recall" -- L recall --scope "库存回写" --no-count
LS_OUT="$(L recall --scope "库存回写" --no-count 2>&1)"
if printf '%s' "$LS_OUT" | grep -q "L1"; then
  bad "a retired lesson is still being recalled"
else
  ok "retired lessons are not recalled"
fi

expect 0 "schema documents the six questions" -- \
  python3 "${S}/lessons.py" schema
contains "何时不适用" "the schema explains the boundary question"
rm -rf "$LS_REPO"

say "25 the check index must not drift from the code"

# Each definition carries a table of what delegation.py checks. A table
# nobody verifies becomes a promise the code does not keep — and the agent
# believes the table.
IDX_DIR="$(mktemp -d)"
cp "${REPO}/agents"/*.md "$IDX_DIR/"
expect 0 "the shipped definitions agree with the code" -- \
  python3 "${S}/agents-check.py" --agents-dir "$IDX_DIR"

python3 - "$IDX_DIR" <<'PYX'
import pathlib, sys
p = pathlib.Path(sys.argv[1]) / "idev-ops.md"
t = p.read_text(encoding="utf-8")
t = t.replace("| `artifact-verified` |", "| `totally-made-up` | 编造的 |\n| `artifact-verified` |", 1)
p.write_text(t, encoding="utf-8")
PYX
expect 1 "catch a check the code never emits" -- \
  python3 "${S}/agents-check.py" --agents-dir "$IDX_DIR"
contains "totally-made-up" "names the invented check"
contains "drifted" "says the table drifted"
rm -rf "$IDX_DIR"

say "26 replay carries why it failed, and eval counts it"

# An agent re-delegated after three failed checks must be told which three.
# Told only "last time: PASS" it repeats the same omission — which is the
# one thing re-delegating is supposed to prevent.
RP_REPO="$(mktemp -d)"
git init -q "$RP_REPO" >/dev/null 2>&1 || true
RP_HOME="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$RP_REPO" --feature rp --key task 2>/dev/null)"
mkdir -p "${RP_HOME:?rp ticket home unresolved}"
echo "review ok" > "${RP_HOME}/review.md"

cat > "${RP_REPO}/r1.yaml" <<YAML
step: code-pass
kind: deliver.code_pass
agent: idev-coder
brief:
  ticket_home: ${RP_HOME}
  repo: ${RP_REPO}
  stage: code
  must_read: conventions/coding.md
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${RP_HOME}/review.md
    FACTS: 源码 src/a.py:1
    DOC_DRIFT: 无
YAML
expect 1 "a report missing fields is refused" -- \
  python3 "${S}/delegation.py" --repo "$RP_REPO" write --feature rp --file "${RP_REPO}/r1.yaml"

expect 0 "replay reproduces the brief" -- \
  python3 "${S}/delegation.py" --repo "$RP_REPO" replay --feature rp --step code-pass
contains "本次必须修掉的" "tells the agent what to fix"
contains "s0-declared" "names the failed check"
contains "assumption-declared" "names every failed check"
RP_OUT="$(python3 "${S}/delegation.py" --repo "$RP_REPO" replay --feature rp --step code-pass 2>&1)"
if printf '%s' "$RP_OUT" | grep -qE "prior_failure: PASS —"; then
  bad "replay reported a clean PASS after checks failed"
else
  ok "replay does not report a failed round as clean"
fi

# rejected must be derived: it used to read an `outcome` field nothing ever
# wrote, so it was permanently 0 — which reads as "never rejected" rather
# than "never measured".
expect 0 "eval reports the counts" -- \
  python3 "${S}/delegation.py" --repo "$RP_REPO" eval --feature rp
contains "rejected: 1" "counts the round whose checks failed"
contains "不打分" "stays a count, not a score"
rm -rf "$RP_REPO"

say "27 suggest reaches the people who can act on it"

# SUGGEST is how an agent says "your definition is unclear here" — the input
# to improving it. It was written in the report body and read from a
# top-level key nothing ever set, so every suggestion was silently dropped.
SG_REPO="$(mktemp -d)"
git init -q "$SG_REPO" >/dev/null 2>&1 || true
SG_HOME="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$SG_REPO" --feature sg --key task 2>/dev/null)"
mkdir -p "${SG_HOME:?sg ticket home unresolved}"
echo "review ok" > "${SG_HOME}/review.md"
cat > "${SG_REPO}/r.yaml" <<YAML
step: s1
kind: review.report
agent: idev-reviewer
brief:
  ticket_home: ${SG_HOME}
  repo: ${SG_REPO}
  stage: code
  must_read: conventions/coding.md
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${SG_HOME}/review.md
    FACTS: 源码 scripts/delegation.py:1
    DOC_DRIFT: 无
    ASSUMED: 无
    CHECKS: evidence-present
    SUGGEST: 定义里「认语言」那一步没说清多语言仓怎么办
YAML
expect 0 "record a report carrying a suggestion" -- \
  python3 "${S}/delegation.py" --repo "$SG_REPO" write --feature sg --file "${SG_REPO}/r.yaml"

expect 0 "eval counts the suggestion" -- \
  python3 "${S}/delegation.py" --repo "$SG_REPO" eval --feature sg
contains "suggest: 1" "the suggestion is counted, not dropped"

expect 0 "timeline shows what was suggested" -- \
  python3 "${S}/delegation.py" --repo "$SG_REPO" timeline --feature sg
contains "多语言仓" "the suggestion text survives to the timeline"

# A report with no suggestion must not be counted as having one.
python3 - "${SG_REPO}" <<'PYX'
import pathlib, sys
p = pathlib.Path(sys.argv[1]) / "r.yaml"
t = p.read_text(encoding="utf-8")
p.write_text(t.replace("SUGGEST: 定义里「认语言」那一步没说清多语言仓怎么办", "SUGGEST: 无")
             .replace("step: s1", "step: s2"), encoding="utf-8")
PYX
expect 0 "record a report with no suggestion" -- \
  python3 "${S}/delegation.py" --repo "$SG_REPO" write --feature sg --file "${SG_REPO}/r.yaml"
SG_OUT="$(python3 "${S}/delegation.py" --repo "$SG_REPO" eval --feature sg 2>&1)"
if printf '%s' "$SG_OUT" | grep -q "suggest: 1"; then
  ok "an empty suggestion is not counted"
else
  bad "the empty suggestion was counted, or the real one was lost"
fi
rm -rf "$SG_REPO"

say "28 paired definitions must not drift apart"

# hypothesis.py once carried two lists of evidence kinds: TIERS stopped at
# four while EVIDENCE_KINDS grew to eight, so monitoring, traces, config,
# release records and artifact identity were all silently collapsed into
# "log" — five different strengths reported as the weakest one.
python3 - <<'PYX'
import importlib.util, sys
sys.path.insert(0, "scripts/lib")
spec = importlib.util.spec_from_file_location("h", "scripts/hypothesis.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
problems = m.tier_check()
if problems:
    print("\n".join(problems))
    sys.exit(1)
# And the ranking must actually discriminate, not just exist.
cases = [(["监控 p99 突增 grafana"], "metric"),
         (["artifact-match 判定 AHEAD"], "artifact"),
         (["src/a.py:10"], "code"),
         (["README.md 里写的"], "doc")]
bad = [(e, want, m.tier_of(e)) for e, want in cases if m.tier_of(e) != want]
if bad:
    print("tier_of misranks:", bad)
    sys.exit(1)
PYX
if [ $? -eq 0 ]; then
  ok "evidence kinds, ranks and explanations agree"
else
  bad "the evidence-kind lists drifted apart"
fi

# lessons.py and stage-gate.py carry the same shape of pairing.
python3 - <<'PYX'
import importlib.util, sys
sys.path.insert(0, "scripts/lib")
out = []
for mod, path, fn in (("l", "scripts/lessons.py", "pair_check"),
                      ("sg", "scripts/stage-gate.py", "gate_check")):
    spec = importlib.util.spec_from_file_location(mod, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    out += getattr(m, fn)()
if out:
    print("\n".join(out))
    sys.exit(1)
PYX
if [ $? -eq 0 ]; then
  ok "lessons and stage-gate pairings are complete"
else
  bad "a paired definition drifted"
fi

# The guards must actually fire — a self-check that cannot fail is decoration.
python3 - <<'PYX'
import importlib.util, sys
sys.path.insert(0, "scripts/lib")
spec = importlib.util.spec_from_file_location("h", "scripts/hypothesis.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.EVIDENCE_KINDS["invented"] = m.re.compile("x")
sys.exit(0 if m.tier_check() else 1)
PYX
if [ $? -eq 0 ]; then
  ok "adding an unranked evidence kind is caught"
else
  bad "tier_check does not notice a new unranked kind"
fi

say "29 one blacklist, and a hit declaration people can actually write"

# check-feature.py carried its own copy of the agent-name blacklist and it
# had already drifted: a blank name passed there and was rejected by
# workflow_spec. Every call site happened to add `not who` as a backstop —
# correctness that depends on each caller remembering.
python3 - <<'PYX'
import importlib.util, sys
sys.path.insert(0, "scripts"); sys.path.insert(0, "scripts/lib")
spec = importlib.util.spec_from_file_location("cf", "scripts/check-feature.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
import workflow_spec as w
bad = [n for n in ("agent", "AI", "Cursor", "assistant", "", "  ", "wangwei794", "claude")
       if m.agent_signoff(n) != (not w.is_human(n))]
sys.exit(1 if bad else 0)
PYX
if [ $? -eq 0 ]; then
  ok "check-feature and workflow_spec agree on who may sign"
else
  bad "the two signoff blacklists disagree"
fi
if grep -q "AGENT_BY" "${REPO}/scripts/check-feature.py"; then
  bad "check-feature still carries its own blacklist"
else
  ok "there is only one blacklist"
fi

# 「无」 is the natural way to write a zero hit; requiring exactly 「零命中」
# turned a wording difference into a failure, with a bare FAIL that did not
# say which of the two problems it was.
TH_REPO="$(mktemp -d)"
git init -q "$TH_REPO" >/dev/null 2>&1 || true
TH_HOME="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$TH_REPO" --feature th --key task 2>/dev/null)"
mkdir -p "${TH_HOME:?th ticket home unresolved}"
echo "零命中" > "${TH_HOME}/review.md"
th_report() {  # th_report <TABLE_HIT value> <step>
  cat > "${TH_REPO}/r.yaml" <<YAML
step: $2
kind: deliver.code_pass
agent: idev-coder
brief:
  ticket_home: ${TH_HOME}
  repo: ${TH_REPO}
  stage: code
  must_read: conventions/coding.md
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${TH_HOME}/review.md
    CHANGE_KIND: 追加行为
    CANON_TRIGGER: 无
    TABLE_HIT: $1
    FACTS: 源码 a.py:1
    DOC_DRIFT: 无
    ASSUMED: 无
    SCOPE: a.py:f
YAML
}
th_report "无" "s1"
expect 0 "「无」 counts as a zero hit" -- \
  python3 "${S}/delegation.py" --repo "$TH_REPO" write --feature th --file "${TH_REPO}/r.yaml"
th_report "零命中" "s2"
expect 0 "「零命中」 counts too" -- \
  python3 "${S}/delegation.py" --repo "$TH_REPO" write --feature th --file "${TH_REPO}/r.yaml"
th_report "§1.3 预置模式" "s3"
expect 1 "a real hit with no sign of being applied is refused" -- \
  python3 "${S}/delegation.py" --repo "$TH_REPO" write --feature th --file "${TH_REPO}/r.yaml"
contains "命中必须当轮改掉" "says what to do about a real hit"
contains "若其实是零命中" "says how to declare it if there was no hit"
rm -rf "$TH_REPO"

say "30 every failure must say what to do about it"

# A bare "FAIL" tells the agent it was wrong without telling it which of
# several things to change. These three were the most important checks in
# the file and said exactly that for a long time.
python3 - <<'PYX'
import pathlib, re, sys
t = pathlib.Path("scripts/delegation.py").read_text(encoding="utf-8")
bare = re.findall(r'=\s*"(FAIL|WARN)"\s*$', t, re.M)
if bare:
    print(f"{len(bare)} bare FAIL/WARN with no explanation")
    sys.exit(1)
PYX
if [ $? -eq 0 ]; then
  ok "no check answers with a bare FAIL"
else
  bad "a check answers with a bare FAIL"
fi

# And the messages must be actionable, not just longer.
FM_REPO="$(mktemp -d)"
git init -q "$FM_REPO" >/dev/null 2>&1 || true
FM_HOME="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$FM_REPO" --feature fm --key task 2>/dev/null)"
mkdir -p "${FM_HOME:?fm ticket home unresolved}"
cat > "${FM_REPO}/r.yaml" <<YAML
step: s1
kind: deliver.code_pass
agent: idev-coder
brief:
  ticket_home: ${FM_HOME}
  repo: ${FM_REPO}
  stage: code
  must_read: conventions/coding.md
  idev_root: ${REPO}
report:
  raw: |
    STATUS: PASS
    CHANGE_KIND: 追加
    CANON_TRIGGER: 无
    TABLE_HIT: 无
    SCOPE: a.py:f
    READ: a.py:f
    CHANGED: a.py:f, b.py:g
    REVERT: abc123
YAML
expect 1 "a report with several problems is refused" -- \
  python3 "${S}/delegation.py" --repo "$FM_REPO" write --feature fm --file "${FM_REPO}/r.yaml"
contains "写产出文件的路径" "evidence-present says what to write"
contains "第一手材料" "facts-first says what counts"
contains "没遇到就写「无」" "drift-declared says what to do when there is none"
contains "另开一轮" "scope-held says how to resolve it"
contains "先读再改" "read-before-change says the order"

# brief-complete must point at the conductor, not leave the agent guessing.
cat > "${FM_REPO}/r2.yaml" <<YAML
step: s2
kind: deliver.code_pass
agent: idev-coder
brief:
  repo: ${FM_REPO}
report:
  raw: |
    STATUS: PASS
    EVIDENCE: ${FM_HOME}
YAML
expect 1 "an incomplete brief is refused" -- \
  python3 "${S}/delegation.py" --repo "$FM_REPO" write --feature fm --file "${FM_REPO}/r2.yaml"
contains "这是导体的问题" "brief-complete names who must fix it"
contains "replay" "tells the conductor how to rebuild the brief"
rm -rf "$FM_REPO"

say "31 realign and ui-playbook tell you how to fix it"

# realign is read by someone who has just had a requirement corrected and
# is looking at a dozen drifts. "Here is what is wrong" without "here is
# what to do" leaves them to work out the order and the edits themselves.
RA2="$(mktemp -d)"
git init -q "$RA2" >/dev/null 2>&1 || true
RA2_HOME="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$RA2" --feature ra --key task 2>/dev/null)"
mkdir -p "${RA2_HOME:?ra ticket home unresolved}/verify"
printf 'revision: 2\nsealed: false\nitems: [{id: B3, must: x, acceptance: 3 秒}]\n' > "${RA2_HOME}/baseline.yaml"
printf 'stage: req-review\nreopen_baseline: true\nlast_rewind: {origin: req}\n' > "${RA2_HOME}/deliver.yaml"
printf 'baseline_revision: 1\naccepted: true\nslices: [{id: S1, baseline_item_id: B1}]\n' > "${RA2_HOME}/req.yaml"
printf 'cases: [{id: c1, baseline_item_id: B1, status: PASS, evidence: x.log}]\n' > "${RA2_HOME}/verify/plan.yaml"
# arch is after the rewind origin, so its accepted is void by schema — that
# is the case this assertion is about.
printf 'baseline_revision: 1\naccepted: true\ncase_intents: [{id: CI1, baseline_item_id: B1}]\n' > "${RA2_HOME}/arch.yaml"

expect 1 "realign finds the drift" -- python3 "${S}/realign.py" --repo "$RA2" --feature ra
contains "改法:" "every drift class carries a fix"
contains "不要只改这个数字" "warns against the shortcut that silences the check"
contains "人手清掉这些字段" "says who clears a stale signoff"
contains "证据保留" "says the old evidence is kept, not deleted"
rm -rf "$RA2"

# Same standard for the playbook checks.
PB2="$(mktemp -d)"
mkdir -p "${PB2}/e2e/flows"
cat > "${PB2}/e2e/flows/x.spec.ts" <<'TSX'
import { test } from '@playwright/test';
const TAG = 'AUTOTEST_x';
test('无断言且清理不保证', async ({ page }) => {
  // @phase: create
  await page.fill('.n', TAG);
  // @phase: read
  await page.goto('/x');
  // @phase: change
  await page.click('.s');
  // @phase: restore
  await page.click('.undo');
  // @phase: cleanup
  await page.click('.del');
});
TSX
expect 1 "the playbook checks fire" -- python3 "${S}/ui-playbook.py" --repo "$PB2"
contains "afterEach" "says where cleanup belongs"
contains "每个阶段至少断言一件可观察的事" "says what to assert"
rm -rf "$PB2"

say "32 behave sanely against a repo that has no ticket yet"

# Every tool must refuse the same way when the ticket does not exist.
# lessons.py used to compute the path and carry on, so `check` answered
# "PASS 0 条" and `recall` answered "no matching lessons" — a typo in the
# feature name read as "the ledger is clean" / "nothing is known".
NT="$(mktemp -d)"
git init -q "$NT" >/dev/null 2>&1 || true
for tool in "stage-gate.py --feature nope --all" "realign.py --feature nope" \
            "req-ground.py --feature nope" "ui-spec.py --feature nope"; do
  # shellcheck disable=SC2086
  expect 2 "${tool%% *} refuses a feature with no ticket" -- \
    python3 "${S}"/${tool} --repo "$NT"
done
expect 2 "lessons.py refuses a feature with no ticket" -- \
  python3 "${S}/lessons.py" --repo "$NT" --feature nope check
contains "BLOCKED" "says it is blocked, not clean"
contains "feature 名打错了" "suggests the likely cause"

# The kernel-wide ledger still works without a feature.
expect 0 "the kernel ledger needs no ticket" -- python3 "${S}/lessons.py" check

# An artifact with no commit must not be told to check out "<its commit>".
if command -v zip >/dev/null 2>&1; then
  NB="$(mktemp -d)"
  mkdir -p "${NB}/META-INF"
  printf 'Manifest-Version: 1.0\nImplementation-Version: 9.9.9\n' > "${NB}/META-INF/MANIFEST.MF"
  echo x > "${NB}/A.class"
  # Backdate the class so the repo's HEAD is genuinely newer — the shape
  # seen on a real repo: built yesterday, committed to since.
  touch -t 202001010000 "${NB}/A.class"
  (cd "$NB" && zip -qrX "${NT}/nocommit.jar" .)
  (cd "$NT" && echo a > a.txt && git add -A \
    && git -c user.email=t@t -c user.name=t commit -qm one) >/dev/null 2>&1
  expect 1 "an artifact with no commit is still actionable" -- \
    python3 "${S}/artifact-match.py" --artifact "${NT}/nocommit.jar" --repo "$NT"
  contains "产物没带 commit" "says why option 1 cannot name a commit"
  contains "git -C" "still gives a command that can be run"
  AM_OUT="$(python3 "${S}/artifact-match.py" --artifact "${NT}/nocommit.jar" --repo "$NT" 2>&1)"
  if printf '%s' "$AM_OUT" | grep -q "checkout <产物的 commit>"; then
    bad "told the user to check out a placeholder"
  else
    ok "no placeholder is offered as an instruction"
  fi
  rm -rf "$NB"
fi
rm -rf "$NT"

say "33 concurrent writes must not lose entries"

# Ten parallel appends to one ledger used to leave one entry: every process
# read the same empty file, each wrote its own, last one won — and every
# call reported OK. Silent data loss in the ledger that root-cause analysis
# depends on.
CW="$(mktemp -d)"
git init -q "$CW" >/dev/null 2>&1 || true
CW_HOME="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$CW" --feature cw --key task 2>/dev/null)"
mkdir -p "${CW_HOME:?cw ticket home unresolved}"

for i in 1 2 3 4 5 6 7 8 9 10; do
  python3 "${S}/hypothesis.py" --repo "$CW" add --feature cw \
    --claim "假设 $i" --case "c$i" >/dev/null 2>&1 &
done
wait
python3 - "${CW_HOME}/hypotheses.yaml" <<'PYX'
import pathlib, sys
sys.path.insert(0, "scripts/lib")
import safeyaml
d = safeyaml.mapping(pathlib.Path(sys.argv[1])) or {}
items = d.get("items") or []
ids = [str(i.get("id")) for i in items]
if len(items) != 10 or len(set(ids)) != 10:
    print(f"kept {len(items)} of 10, {len(set(ids))} unique ids")
    sys.exit(1)
PYX
if [ $? -eq 0 ]; then
  ok "ten concurrent appends keep ten entries with unique ids"
else
  bad "concurrent appends lost entries or reused ids"
fi

# Concurrent edits to different entries must not drop each other's fields.
for i in 1 2 3 4 5; do
  python3 "${S}/hypothesis.py" --repo "$CW" set --feature cw \
    --id "H$i" --evidence "ev-$i.log" >/dev/null 2>&1 &
done
wait
python3 - "${CW_HOME}/hypotheses.yaml" <<'PYX'
import pathlib, sys
sys.path.insert(0, "scripts/lib")
import safeyaml
d = safeyaml.mapping(pathlib.Path(sys.argv[1])) or {}
by_id = {str(i.get("id")): i for i in (d.get("items") or [])}
missing = [f"H{n}" for n in range(1, 6)
           if not (by_id.get(f"H{n}", {}).get("evidence"))]
if len(by_id) != 10 or missing:
    print(f"{len(by_id)} entries; missing evidence on {missing}")
    sys.exit(1)
PYX
if [ $? -eq 0 ]; then
  ok "concurrent edits to different entries all survive"
else
  bad "a concurrent edit was overwritten"
fi

# Same ledger shape in lessons.py.
LW_HOME="$(python3 "${IDEV_LIB}/doc_home.py" --repo "$CW" --feature lw --key task 2>/dev/null)"
mkdir -p "$LW_HOME"
for i in 1 2 3 4 5 6 7 8; do
  python3 "${S}/lessons.py" --repo "$CW" --feature lw add \
    --scope "s$i" --symptom "y$i" --evidence e --action a \
    --outcome o --not-when n >/dev/null 2>&1 &
done
wait
python3 - "${LW_HOME}/lessons.yaml" <<'PYX'
import pathlib, sys
sys.path.insert(0, "scripts/lib")
import safeyaml
d = safeyaml.mapping(pathlib.Path(sys.argv[1])) or {}
ls = d.get("lessons") or []
ids = [str(x.get("id")) for x in ls]
if len(ls) != 8 or len(set(ids)) != 8:
    print(f"kept {len(ls)} of 8, {len(set(ids))} unique ids")
    sys.exit(1)
PYX
if [ $? -eq 0 ]; then
  ok "the lessons ledger survives concurrent appends too"
else
  bad "the lessons ledger lost entries"
fi

# A crash mid-write must not leave a half-written ledger behind: the write
# goes to a temp file and is renamed into place.
if ls "${CW_HOME}"/*.tmp >/dev/null 2>&1; then
  bad "temp files were left behind"
else
  ok "no temp files survive a completed write"
fi
rm -rf "$CW"

printf '\n== result\n'
printf '  pass %d   fail %d\n' "$PASS" "$FAIL"
if [ "$FAIL" -ne 0 ]; then
  echo "smoke FAIL"
  exit 1
fi
echo "smoke PASS"
exit 0
