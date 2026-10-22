#!/usr/bin/env bash
# check-feature by risk tier: P1/P2 seal the baseline together with req,
# and plan / resolved may pass on machine checks; P0 keeps every signoff.
#
#   bash test/check-feature-tiers.sh
set -uo pipefail

IDEV="$(cd "$(dirname "$0")/.." && pwd -P)"
S="$(mktemp -d "${TMPDIR:-/tmp}/idev-tiers.XXXXXX")"
trap 'rm -rf "$S"' EXIT
W="$S/w"
EX="$W/.idev/task/ex"
mkdir -p "$EX/verify" "$W/.idev/docs/spec" "$W/.git"
fails=0

python3 - "$IDEV" "$EX" "$W" <<'PY'
import shutil, sys
from pathlib import Path
idev, ex, work = map(Path, sys.argv[1:4])
base = idev / "deliver" / "references"
for src, dst in (("baseline.example.yaml", "baseline.yaml"), ("req.example.yaml", "req.yaml"),
                 ("arch.example.yaml", "arch.yaml"), ("deliver.example.yaml", "deliver.yaml"),
                 ("review.example.md", "review.md"), ("deliver-eval.example.md", "deliver-eval.md")):
    shutil.copy(base / src, ex / dst)
shutil.copy(idev / "verify" / "references" / "plan.example.yaml", ex / "verify" / "plan.yaml")
shutil.copy(idev / "ops" / "references" / "ops.example.yaml", ex / "ops.yaml")
(ex / "grill.md").write_text("convention: grilling\nfrontier: empty\nshared_understanding: true\n\n"
                             "❓ **Q1** - **scope**: x\n➡️ keep\n")
(work / ".idev" / "docs" / "spec" / "ex.md").write_text("x\n")
PY

# edit <file> <python expression over d>: rewrite one ticket YAML in place.
edit() {
  python3 - "$1" "$2" <<'PY'
import sys, yaml
path, expr = sys.argv[1], sys.argv[2]
d = yaml.safe_load(open(path, encoding="utf-8"))
exec(expr)
yaml.safe_dump(d, open(path, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
PY
}

# expect <name> <stage> <exit> <regex>: one case, red or green.
expect() {
  local name="$1" stage="$2" want="$3" pattern="$4" out rc
  out="$(python3 "$IDEV/scripts/check-feature.py" --repo "$W" --feature ex --stage "$stage" 2>&1)"; rc=$?
  if [ "$rc" = "$want" ] && printf '%s\n' "$out" | grep -qE "$pattern"; then
    echo "OK   $name"
  else
    echo "FAIL $name (exit $rc, want $want, pattern $pattern)"
    printf '%s\n' "$out" | grep -E "FAIL|SIGNAL|seal" | sed 's/^/     /'
    fails=$((fails + 1))
  fi
}

D="$EX/deliver.yaml"
edit "$D" 'd["semantic_gate"] = {"req-review": {"passed": False}}'

expect "P1 req on an unsealed, ready baseline" req 0 "baseline seals with req at P1"
printf 'convention: grilling\nfrontier: open\nshared_understanding: false\n\n❓ **Q1** - **scope**: x\n➡️ keep\n' > "$EX/grill.md"
expect "P1 req with grill frontier open" req 1 "frontier is not closed"
printf 'convention: grilling\nfrontier: empty\nshared_understanding: true\n\n❓ **Q1** - **scope**: x\n➡️ keep\n' > "$EX/grill.md"
edit "$EX/baseline.yaml" 'd["objections"] = ["scope unclear"]'
expect "P1 req with an objection on the baseline" req 1 "objections not empty"
edit "$EX/baseline.yaml" 'd["objections"] = []'
edit "$D" 'd["risk_tier"] = "P0"'
expect "P0 req on an unsealed baseline" req 1 "baseline.sealed is not true"
edit "$D" 'd["risk_tier"] = "P1"'
expect "P1 arch still needs the seal" arch 1 "baseline.sealed is not true"

edit "$EX/baseline.yaml" 'd["sealed"] = True'
edit "$EX/arch.yaml" 'd["open_questions"] = ["which cache"]'
expect "arch open question is a signal" arch 1 "SIGNAL arch open_questions still open"
edit "$EX/arch.yaml" 'd["open_questions"] = []'
expect "verify-plan with runners on every case: no signal" verify-plan 0 "every correctness case is runnable"
edit "$EX/verify/plan.yaml" 'd["cases"][1].pop("runner")'
expect "verify-plan with a case that can never run" verify-plan 0 "SIGNAL plan leaves UNPROVEN.*compat-enabled-unchanged"
edit "$EX/verify/plan.yaml" 'd["cases"][1]["runner"] = {"kind": "maven-failsafe"}; d["cases"][2]["baseline_item_id"] = "B9"'
expect "verify-plan with a case outside the baseline" verify-plan 1 "SIGNAL cases not derived 1:1.*compat-replay-untouched"
edit "$EX/verify/plan.yaml" 'd["cases"][2]["baseline_item_id"] = "B3"'

edit "$EX/verify/plan.yaml" 'd["accepted"] = True; d["auto"] = "verify/plan-check.log"; d["mode"] = "test"'
expect "plan.auto with no saved check output" test 1 "plan.auto evidence not found"
printf '0 FAIL\n' > "$EX/verify/plan-check.log"
expect "plan.auto at P1 with the check output" test 1 "plan passed on machine checks"
edit "$D" 'd["risk_tier"] = "P0"'
expect "plan.auto at P0" test 1 "plan.auto at P0: this tier needs a person"
edit "$D" 'd["risk_tier"] = "P1"'

edit "$D" 'd["semantic_gate"]["arch"] = {"passed": True, "auto": "verify/arch-check.log"}'
printf '0 FAIL\n' > "$EX/verify/arch-check.log"
expect "arch auto does not replace a person" test 1 "semantic_gate.arch requires human by"
edit "$D" 'd["semantic_gate"]["arch"] = {"passed": True, "by": "wangwei794"}'

O="$EX/ops.yaml"
edit "$O" 'd["resolved"] = True; d["auto"] = "hypotheses.yaml"; d["by"] = ""'
expect "ops.auto with no ledger" ops 1 "ops.auto needs the hypothesis ledger|ops.auto evidence not found"
cat > "$EX/hypotheses.yaml" <<'YAML'
feature: ex
items:
  - {id: H1, claim: "cache key collides", status: open, case: "c1"}
YAML
expect "ops.auto with an open hypothesis" ops 1 "hypotheses still open: H1"
cat > "$EX/hypotheses.yaml" <<'YAML'
feature: ex
items:
  - id: H1
    claim: "cache key collides in the database index"
    status: proven
    repro: "yes"
    case: "c1"
    evidence: ["src/cache.go:42", "logs/app.log"]
    impact: "orders written in the window 10:00-10:05"
    remedy: "key on tenant + id; replay the window"
    blast: {guard: ["c2"]}
  - {id: H2, claim: "network flap", status: disproven, note: "no packet loss in the window"}
YAML
expect "ops.auto on a settled ledger" ops 0 "hypothesis ledger settled"
edit "$D" 'd["risk_tier"] = "P0"'
expect "ops.auto at P0" ops 1 "ops.auto at P0: this tier needs a person"

echo
[ "$fails" = 0 ] && { echo "check-feature tiers PASS"; exit 0; }
echo "check-feature tiers FAIL ($fails)"; exit 1
