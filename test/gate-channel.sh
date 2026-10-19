#!/usr/bin/env bash
# The gate channel end to end: workflow.py asks, a person answers from a
# terminal with `idev gate approve`, and record PASS reads the signed answer
# back. Each case is red first (the refusal) and then green.
#
#   bash test/gate-channel.sh
set -uo pipefail

IDEV="$(cd "$(dirname "$0")/.." && pwd -P)"
W="${IDEV}/scripts/workflow.py"
T="$(mktemp -d "${TMPDIR:-/tmp}/idev-gate.XXXXXX")"
trap 'rm -rf "$T"' EXIT
T="$(cd "$T" && pwd -P)"

pass=0
fail=0
ok() { echo "OK   $1"; pass=$((pass + 1)); }
bad() { echo "FAIL $1"; fail=$((fail + 1)); }

(cd "$IDEV" && go build -o "$T/bin/idev" ./cmd/idev) || { echo "FAIL go build"; exit 1; }
export IDEV_BIN="$T/bin/idev" IDEV_DATA="$T/data"
unset IDEV_ENGINE
# The binary looks for people.yaml next to itself (bin/../config).
mkdir -p "$T/config" "$T/data/secrets"
printf 'people:\n  - tester\n' > "$T/config/people.yaml"
printf 'handle: tester\ntoken: idv_h_test\n' > "$T/data/secrets/human.yaml"
chmod 600 "$T/data/secrets/human.yaml"

# in_pty CMD... runs CMD on a pseudo-terminal, feeding it this script's stdin.
in_pty() {
  if script -q /dev/null true >/dev/null 2>&1 </dev/null; then
    script -q /dev/null "$@"
  else
    script -qec "$(printf '%q ' "$@")" /dev/null
  fi
}

P="$T/product"
mkdir -p "$P/.idev/task/demo/verify" "$P/.idev/workflows"
cd "$P" && git init -q
printf 'schema_version: 1\nmarker: idev\nid: demo\nevolve: false\n' > .idev/marker.yaml
printf 'stage: test\nrisk_tier: P1\n' > .idev/task/demo/deliver.yaml
printf 'cases: []\n' > .idev/task/demo/verify/plan.yaml
printf '%s\n' 'schema_version: 1' 'id: demo-gate' 'summary: x' 'params:' '  - {name: feature, required: true, from: user}' \
  'steps:' '  - {id: g, kind: human.gate, with: {will_write: ["verify/plan.yaml accepted"]}}' '  - {id: r, kind: verify.run}' \
  > .idev/workflows/demo-gate.yaml
RUN=.idev/task/demo/workflow/run.yaml

out="$("$W" start demo-gate --feature demo 2>&1)"
[[ "$out" == *"workflow.py ask g"* ]] && ok "next names ask, not --by / --quote" || bad "next line: $out"

out="$("$W" record g PASS --feature demo --by tester --quote 确认 2>&1)" \
  && bad "a typed --by / --quote passed the gate" || { [[ "$out" == *"own terminal"* ]] && ok "typed signature refused" || bad "typed signature: $out"; }

out="$("$W" record g PASS --feature demo 2>&1)" \
  && bad "PASS before asking" || { [[ "$out" == *"has not been asked"* ]] && ok "PASS before ask refused" || bad "unasked: $out"; }

out="$(IDEV_BIN="$T/nope" "$W" ask g --feature demo 2>&1)" \
  && bad "asked with no binary" || { [[ "$out" == *"IDEV_ENGINE=python"* ]] && ok "missing binary names the fallback" || bad "no binary: $out"; }

out="$("$W" ask g --feature demo 2>&1)" || bad "ask: $out"
GID="$(printf '%s\n' "$out" | sed -n 's/^GATE \([0-9A-Z]\{26\}\) asked.*/\1/p')"
[ -n "$GID" ] && ok "ask opened gate $GID" || bad "ask printed: $out"
SHORT="${GID: -4}"

"$W" ask g --feature demo >/dev/null 2>&1 && bad "a second pending question on one step" || ok "one pending question per step"

out="$("$W" record g PASS --feature demo 2>&1)" \
  && bad "PASS while unanswered" || { [[ "$out" == *"waiting for the person"* ]] && ok "PASS while pending refused" || bad "pending: $out"; }

out="$(printf '%s\n' "$SHORT" | "$IDEV_BIN" gate approve "$GID" --quote 确认 2>&1)" \
  && bad "approved without a terminal" || { [[ "$out" == *"TTY"* ]] && ok "approve without a terminal refused" || bad "no tty: $out"; }

# The pause lets the prompt start reading before the line arrives, and keeps
# script's end-of-input ^D from landing in the middle of it.
out="$({ sleep 1; printf '%s\n' "$SHORT"; sleep 1; } | in_pty "$IDEV_BIN" gate approve "$GID" --quote 确认 2>&1)"
[[ "$out" == *"approved $GID by tester"* ]] && ok "the person approved from a terminal" || bad "approve: $out"

printf 'cases: [late-edit]\n' > .idev/task/demo/verify/plan.yaml
out="$("$W" record g PASS --feature demo 2>&1)" \
  && bad "PASS on content edited after approval" || { [[ "$out" == *"changed since"* ]] && ok "edited after approval refused" || bad "edited: $out"; }
printf 'cases: []\n' > .idev/task/demo/verify/plan.yaml

out="$("$W" record g PASS --feature demo 2>&1)"
[[ "$out" == *"NEXT r "* ]] && ok "PASS reads the signed answer back" || bad "record: $out"
python3 - "$RUN" "$GID" <<'PY' && ok "run.yaml carries the approval, not a typed name" || bad "signoff in run.yaml"
import sys, yaml
run = yaml.safe_load(open(sys.argv[1]))
g = next(s for s in run["steps"] if s["id"] == "g")
s = g["signoff"]
assert g["gate"]["id"] == sys.argv[2], g
assert s["by"] == "tester" and s["quote"] == "确认" and s["approval_id"] and s["assurance"] == "low", s
PY
python3 "${IDEV}/scripts/workflow-check.py" --run "$RUN" >/dev/null && ok "workflow-check accepts the run" || bad "workflow-check --run"

out="$(IDEV_ENGINE=python "$W" ask g --feature demo 2>&1)" \
  && bad "python engine asked" || ok "IDEV_ENGINE=python has no ask"

echo "gate channel: ${pass} OK, ${fail} FAIL"
[ "$fail" -eq 0 ]
