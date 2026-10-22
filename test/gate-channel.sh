#!/usr/bin/env bash
# The gate channel: a chat reply of 确认 is the signoff. The terminal
# `idev gate approve` path still works and is not required. Each case is
# red first (the refusal) and then green.
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
[[ "$out" == *'--quote "<their words>"'* ]] && ok "next names the chat reply as the signoff" || bad "next line: $out"

out="$("$W" record g PASS --feature demo --by tester --quote 继续 2>&1)" \
  && bad "继续 signed the gate" || { [[ "$out" == *"confirm words"* ]] && ok "继续 is not a signoff" || bad "继续: $out"; }

out="$("$W" record g PASS --feature demo --by idev-coder --quote 确认 2>&1)" \
  && bad "an agent signed the gate" || { [[ "$out" == *"person's name"* ]] && ok "agent name refused" || bad "agent: $out"; }

out="$("$W" record g PASS --feature demo 2>&1)" \
  && bad "PASS with no reply" || { [[ "$out" == *"confirm words"* ]] && ok "PASS with no reply refused" || bad "unquoted: $out"; }

out="$(IDEV_BIN="$T/nope" "$W" ask g --feature demo 2>&1)" \
  && bad "asked with no binary" || { [[ "$out" == *"IDEV_ENGINE=python"* ]] && ok "missing binary names the fallback" || bad "no binary: $out"; }

out="$("$W" ask g --feature demo 2>&1)" || bad "ask: $out"
GID="$(printf '%s\n' "$out" | sed -n 's/^GATE \([0-9A-Z]\{26\}\) asked.*/\1/p')"
[ -n "$GID" ] && ok "ask opened gate $GID" || bad "ask printed: $out"
SHORT="${GID: -4}"

# The question is in sqlite. Dropping it from the run must not open a second
# one, and must not hold the yaml lock across the request.
python3 - "$RUN" <<'PY'
import sys, yaml
run = yaml.safe_load(open(sys.argv[1]))
next(s for s in run["steps"] if s["id"] == "g").pop("gate", None)
yaml.safe_dump(run, open(sys.argv[1], "w"), allow_unicode=True, sort_keys=False)
PY
printf '%s\n' "$GID" > .idev/task/demo/workflow/gate-g.id
cat > "$T/bin/idev-no-request" <<EOF
#!/bin/bash
if [[ "\$1" == "gate" && "\$2" == "request" ]]; then
  echo "request should not run" >&2
  exit 1
fi
exec "$IDEV_BIN" "\$@"
EOF
chmod +x "$T/bin/idev-no-request"
out="$(IDEV_BIN="$T/bin/idev-no-request" "$W" ask g --feature demo 2>&1)" || bad "sidecar ask: $out"
again="$(printf '%s\n' "$out" | sed -n 's/^GATE \([0-9A-Z]\{26\}\) asked.*/\1/p')"
{ [ "$again" = "$GID" ] && printf '%s\n' "$out" | grep -q "already open"; } \
  && ok "a lost id is restored from the sidecar without a second question" || bad "sidecar: $out"
[ ! -e .idev/task/demo/workflow/gate-g.id ] && ok "the sidecar is removed once the id is in the run" || bad "sidecar left behind"

python3 - "$RUN" <<'PY'
import sys, yaml
run = yaml.safe_load(open(sys.argv[1]))
next(s for s in run["steps"] if s["id"] == "g").pop("gate", None)
yaml.safe_dump(run, open(sys.argv[1], "w"), allow_unicode=True, sort_keys=False)
PY
out="$("$W" ask g --feature demo 2>&1)" || bad "reask: $out"
again="$(printf '%s\n' "$out" | sed -n 's/^GATE \([0-9A-Z]\{26\}\) asked.*/\1/p')"
{ [ "$again" = "$GID" ] && printf '%s\n' "$out" | grep -q "already open"; } \
  && ok "a lost id is restored from the pending question" || bad "reask: $out"

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

"$W" abort --feature demo --note "terminal path proven" >/dev/null || bad "abort after terminal path"
out="$("$W" start demo-gate --feature demo 2>&1)" || bad "restart: $out"
out="$("$W" record g PASS --feature demo --by tester --quote 确认 2>&1)"
[[ "$out" == *"NEXT r "* ]] && ok "chat 确认 signs the gate" || bad "chat record: $out"
python3 - "$RUN" <<'PY' && ok "chat signoff keeps the person's words" || bad "chat signoff in run.yaml"
import sys, yaml
run = yaml.safe_load(open(sys.argv[1]))
s = next(step for step in run["steps"] if step["id"] == "g")["signoff"]
assert s["by"] == "tester" and s["quote"] == "确认" and s["assurance"] == "chat", s
assert "approval_id" not in s, s
PY

out="$(IDEV_ENGINE=python "$W" ask g --feature demo 2>&1)" \
  && bad "python engine asked" || ok "IDEV_ENGINE=python has no ask"

# ask must release the run lock before idev gate request. A request that
# sleeps is the wait; a non-blocking lock during that sleep is the proof.
SLOW="$T/slow"
mkdir -p "$SLOW/.idev/task/demo/verify" "$SLOW/.idev/workflows"
(cd "$SLOW" && git init -q)
printf 'schema_version: 1\nmarker: idev\nid: demo\nevolve: false\n' > "$SLOW/.idev/marker.yaml"
printf 'stage: test\nrisk_tier: P1\n' > "$SLOW/.idev/task/demo/deliver.yaml"
printf 'cases: []\n' > "$SLOW/.idev/task/demo/verify/plan.yaml"
cp "$P/.idev/workflows/demo-gate.yaml" "$SLOW/.idev/workflows/demo-gate.yaml"
cat > "$T/bin/idev-slow-request" <<EOF
#!/bin/bash
if [[ "\$1" == "gate" && "\$2" == "request" ]]; then
  sleep 2
fi
exec "$IDEV_BIN" "\$@"
EOF
chmod +x "$T/bin/idev-slow-request"
(cd "$SLOW" && "$W" start demo-gate --feature demo >/dev/null \
  && IDEV_BIN="$T/bin/idev-slow-request" "$W" ask g --feature demo >"$T/slow.out" 2>&1) &
slow_pid=$!
python3 - "$SLOW/.idev/task/demo/workflow/run.yaml.lock" <<'PY'
import fcntl, sys, time
from pathlib import Path
p = Path(sys.argv[1])
deadline = time.time() + 3
while time.time() < deadline and not p.exists():
    time.sleep(0.05)
if not p.exists():
    raise SystemExit("lock file never appeared")
with p.open("a+") as fh:
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (11, 35):
            raise SystemExit("held") from exc
        raise
    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
PY
held=$?
wait "$slow_pid"
slow_rc=$?
{ [ "$held" -eq 0 ] && [ "$slow_rc" -eq 0 ]; } \
  && ok "ask does not hold the run lock across gate request" || bad "lock during ask (held=$held ask=$slow_rc)"

echo "gate channel: ${pass} OK, ${fail} FAIL"
[ "$fail" -eq 0 ]
