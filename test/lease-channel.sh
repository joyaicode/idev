#!/usr/bin/env bash
# Write leases end to end: workflow.py delegate takes one from the arch.yaml
# includes, record checks the agent's CHANGED list against it and releases
# it, and a second writer on the same ticket is refused. Red first, then
# green.
#
#   bash test/lease-channel.sh
set -uo pipefail

IDEV="$(cd "$(dirname "$0")/.." && pwd -P)"
W="${IDEV}/scripts/workflow.py"
T="$(mktemp -d "${TMPDIR:-/tmp}/idev-lease.XXXXXX")"
trap 'rm -rf "$T"' EXIT
T="$(cd "$T" && pwd -P)"

pass=0
fail=0
ok() { echo "OK   $1"; pass=$((pass + 1)); }
bad() { echo "FAIL $1"; fail=$((fail + 1)); }

(cd "$IDEV" && go build -o "$T/bin/idev" ./cmd/idev) || { echo "FAIL go build"; exit 1; }
export IDEV_BIN="$T/bin/idev" IDEV_DATA="$T/data"
unset IDEV_ENGINE

checkout() {
  local dir="$1"
  mkdir -p "$dir/.idev/task/demo/workflow/delegations" "$dir/.idev/workflows"
  (cd "$dir" && git init -q)
  printf 'schema_version: 1\nmarker: idev\nid: demo\nevolve: false\n' > "$dir/.idev/marker.yaml"
  printf 'stage: code\nrisk_tier: P1\n' > "$dir/.idev/task/demo/deliver.yaml"
  printf '%s\n' 'schema_version: 1' 'id: demo-code' 'summary: x' 'params:' '  - {name: feature, required: true, from: user}' \
    'steps:' '  - {id: c, kind: deliver.code_pass}' '  - {id: r, kind: verify.run}' > "$dir/.idev/workflows/demo-code.yaml"
  printf 'reviewed\n' > "$dir/review.md"
  printf '%s\n' 'step: review' 'attempt: 1' 'kind: review.report' 'agent: idev-reviewer' 'report:' \
    '  raw: "STATUS: PASS\nEVIDENCE: review.md\n"' > "$dir/.idev/task/demo/workflow/delegations/review-1.yaml"
}

# report STEP CHANGED: a delegation record whose report names what it changed.
report() {
  printf '%s\n' 'step: c' 'attempt: 1' 'kind: deliver.code_pass' 'agent: idev-coder' 'report:' \
    "  raw: \"STATUS: PASS\\nCHANGED: $1\\n\"" > .idev/task/demo/workflow/delegations/c-1.yaml
}

P="$T/one"
checkout "$P"
cd "$P"
RUN=.idev/task/demo/workflow/run.yaml
VER=(--verified-by idev-reviewer --verify-evidence review.md)

out="$("$W" start demo-code --feature demo 2>&1)"
[[ "$out" == *"workflow.py delegate c"* ]] && ok "next names delegate for a code step" || bad "next: $out"

out="$("$W" record c PASS --feature demo --evidence r.md "${VER[@]}" 2>&1)" \
  && bad "PASS with no lease" || { [[ "$out" == *"never given a write lease"* ]] && ok "PASS without a lease refused" || bad "no lease: $out"; }

out="$("$W" delegate c --feature demo 2>&1)" \
  && bad "a lease with no arch includes" || { [[ "$out" == *"include: true"* ]] && ok "no arch includes, no lease" || bad "no includes: $out"; }

printf '%s\n' 'impact_candidates:' '  - {path: src/app.py, hop: 0, include: true}' '  - {path: src/other.py, hop: 1, include: false}' \
  > .idev/task/demo/arch.yaml
out="$("$W" delegate c --feature demo 2>&1)"
LID="$(printf '%s\n' "$out" | sed -n 's/^LEASE \([0-9A-Z]\{26\}\) fencing=1 .*/\1/p')"
[ -n "$LID" ] && ok "delegate took write lease $LID (fencing 1)" || bad "delegate: $out"

"$W" delegate c --feature demo >/dev/null 2>&1 && bad "a second lease on a held step" || ok "a held step is not delegated twice"

# A second conductor on the same ticket: a copy of the run under another id.
python3 - "$RUN" "$T/rival.yaml" <<'PY'
import sys, yaml
run = yaml.safe_load(open(sys.argv[1]))
run["run_id"] = "01RIVALRUN0000000000000000"
yaml.safe_dump(run, open(sys.argv[2], "w"), allow_unicode=True)
PY
out="$("$IDEV_BIN" lease acquire --run "$T/rival.yaml" --step c --feature-id "$(cd .idev/task/demo && pwd -P)" --write-path src/app.py 2>&1)" \
  && bad "a second writer on one ticket" || { [[ "$out" == *"lease_held"* ]] && ok "second writer on the ticket refused" || bad "rival: $out"; }

Q="$T/two"
checkout "$Q"
(cd "$Q" && printf '%s\n' 'impact_candidates:' '  - {path: src/app.py, hop: 0, include: true}' > .idev/task/demo/arch.yaml \
  && "$W" start demo-code --feature demo >/dev/null && "$W" delegate c --feature demo >/dev/null 2>&1) \
  && ok "another checkout's demo ticket is its own feature" || bad "two checkouts named demo share a lease"

report "src/app.py, src/other.py"
out="$("$W" record c PASS --feature demo --evidence r.md "${VER[@]}" 2>&1)" \
  && bad "PASS with changes outside the lease" || { [[ "$out" == *"outside its lease"*"src/other.py"* ]] && ok "change outside the lease refused" || bad "outside: $out"; }

report "src/app.py:main"
out="$("$W" record c PASS --feature demo --evidence r.md "${VER[@]}" 2>&1)"
[[ "$out" == *"LEASE $LID released"* && "$out" == *"NEXT r "* ]] && ok "PASS inside the lease releases it" || bad "record: $out"
python3 - "$RUN" <<'PY' && ok "run.yaml keeps the lease id, not its token" || bad "lease in run.yaml"
import sys, yaml
c = next(s for s in yaml.safe_load(open(sys.argv[1]))["steps"] if s["id"] == "c")
assert c["lease"]["id"] and "token" not in c["lease"] and c["lease"]["released_at"], c
PY

# The verifier step r writes only ticket artifacts: it needs a verify lease
# fenced to the ticket directory, not a write lease over product code.
vreport() {
  printf '%s\n' 'step: r' 'attempt: 1' 'kind: verify.run' 'agent: idev-verifier' 'report:' \
    "  raw: \"STATUS: PASS\\nCHANGED: $1\\n\"" > .idev/task/demo/workflow/delegations/r-1.yaml
}

vreport "src/app.py"
out="$("$W" record r PASS --feature demo --evidence v.md 2>&1)" \
  && bad "verifier PASS with no lease" || { [[ "$out" == *"never given a verify lease"* ]] && ok "verifier PASS without a lease refused" || bad "verifier no lease: $out"; }

out="$("$W" delegate r --feature demo 2>&1)"
VID="$(printf '%s\n' "$out" | sed -n 's/^LEASE \([0-9A-Z]\{26\}\) fencing=2 .*/\1/p')"
{ [ -n "$VID" ] && printf '%s\n' "$out" | grep -qF 'paths .idev/task/demo/**'; } \
  && ok "delegate took verify lease $VID fenced to the ticket" || bad "verify delegate: $out"

vreport "src/app.py, src/other.py"
out="$("$W" record r PASS --feature demo --evidence v.md 2>&1)" \
  && bad "verifier PASS with changes outside the ticket" || { [[ "$out" == *"outside its lease"*"src/app.py"* ]] && ok "verifier change outside the ticket refused" || bad "verify outside: $out"; }

vreport ".idev/task/demo/report/v.md"
out="$("$W" record r PASS --feature demo --evidence v.md 2>&1)"
[[ "$out" == *"LEASE $VID released"* && "$out" == *"RUN DONE"* ]] && ok "verifier PASS inside the ticket releases it" || bad "verify record: $out"

out="$("$IDEV_BIN" lease acquire --run "$T/rival.yaml" --step c --feature-id "$(cd .idev/task/demo && pwd -P)" --write-path src/app.py 2>&1)"
[[ "$out" == *'"fencing":3'* ]] && ok "the released slot goes to the next writer with a higher fencing token" || bad "after release: $out"

(cd "$Q" && "$W" abort --note test --feature demo 2>&1 | grep -q "released") \
  && ok "abort releases the lease it held" || bad "abort kept its lease"

# A release that fails must not throw the token away. Dropping it first
# locks the feature until the TTL: the lease stays held and nobody can
# present the token again.
cat > "$T/bin/idev-release-once" <<'EOF'
#!/bin/bash
if [[ "$1" == "lease" && "$2" == "release" && ! -f "$LEASE_FAIL_ONCE" ]]; then
  mkdir -p "$(dirname "$LEASE_FAIL_ONCE")"
  : > "$LEASE_FAIL_ONCE"
  echo "injected release failure" >&2
  exit 1
fi
exec "$IDEV_REAL" "$@"
EOF
chmod +x "$T/bin/idev-release-once"
S="$T/three"
checkout "$S"
(
  cd "$S"
  printf '%s\n' 'impact_candidates:' '  - {path: src/app.py, hop: 0, include: true}' > .idev/task/demo/arch.yaml
  "$W" start demo-code --feature demo >/dev/null
  "$W" delegate c --feature demo
) > "$T/three-delegate.out"
L3="$(sed -n 's/^LEASE \([0-9A-Z]\{26\}\) fencing=.*/\1/p' "$T/three-delegate.out")"
printf '%s\n' 'step: c' 'attempt: 1' 'kind: deliver.code_pass' 'agent: idev-coder' 'report:' \
  '  raw: "STATUS: PASS\nCHANGED: src/app.py\n"' > "$S/.idev/task/demo/workflow/delegations/c-1.yaml"
out="$(cd "$S" && LEASE_FAIL_ONCE="$T/release-failed" IDEV_REAL="$IDEV_BIN" IDEV_BIN="$T/bin/idev-release-once" \
  "$W" record c PASS --feature demo --evidence r.md "${VER[@]}" 2>&1)"
[[ "$out" == *"WARN lease $L3 not released"* && "$out" == *"token stays"* ]] \
  && ok "a failed release keeps the token" || bad "failed release: $out"
python3 - "$S/.idev/task/demo/workflow/run.yaml" "$L3" <<'PY' && ok "run.yaml still has the token after a failed release" || bad "token dropped on failed release"
import sys, yaml
c = next(s for s in yaml.safe_load(open(sys.argv[1]))["steps"] if s["id"] == "c")
assert c["lease"]["id"] == sys.argv[2] and c["lease"].get("token"), c
PY
out="$(cd "$S" && "$W" delegate r --feature demo 2>&1)"
[[ "$out" == *"LEASE $L3 released"* && "$out" == *"LEASE paths .idev/task/demo/**"* ]] \
  && ok "the next delegate retries the release that failed" || bad "retry release: $out"
python3 - "$S/.idev/task/demo/workflow/run.yaml" <<'PY' && ok "the retried release drops the token" || bad "token left after retry"
import sys, yaml
c = next(s for s in yaml.safe_load(open(sys.argv[1]))["steps"] if s["id"] == "c")
assert "token" not in c["lease"] and c["lease"].get("released_at"), c
PY

out="$(cd "$Q" && IDEV_ENGINE=python "$W" start demo-code --feature demo >/dev/null 2>&1 \
  && IDEV_ENGINE=python "$W" record c PASS --feature demo --evidence r.md "${VER[@]}" 2>&1)" \
  && ok "IDEV_ENGINE=python records without a lease" || bad "python engine: $out"

echo "lease channel: ${pass} OK, ${fail} FAIL"
[ "$fail" -eq 0 ]
