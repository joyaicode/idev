#!/usr/bin/env bash
# Late-lifecycle smoke: exercise test → promote → ops → aligned forge reject.
# Uses temp fixtures only — never writes product-ticket signoff.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECK=(python3 "$ROOT/scripts/check-feature.py")
DELIVER="$ROOT/deliver/references"
VERIFY="$ROOT/verify/references"
OPS="$ROOT/ops/references"
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/idev-late-life.XXXXXX")"
FEATURE=late-life-smoke
DST="$SCRATCH/docs/task/$FEATURE"
trap 'rm -rf "$SCRATCH"' EXIT

echo "# idev late-lifecycle smoke"

mkdir -p "$DST/verify" "$SCRATCH/docs/spec" "$SCRATCH/docs/test-case"
python3 - <<PY
from pathlib import Path
import shutil
base = Path("$DELIVER")
dst = Path("$DST")
b = (base / "baseline.example.yaml").read_text()
b = b.replace("sealed: false", "sealed: true")
(dst / "baseline.yaml").write_text(b)
shutil.copy(base / "req.example.yaml", dst / "req.yaml")
shutil.copy(base / "arch.example.yaml", dst / "arch.yaml")
shutil.copy(base / "review.example.md", dst / "review.md")
shutil.copy(base / "deliver-eval.example.md", dst / "deliver-eval.md")
(dst / "grill.md").write_text(
    "convention: grilling\n"
    "frontier: empty\n"
    "shared_understanding: true\n"
    "\n"
    "❓ **Q1** - **scope**: settled for late-lifecycle smoke\n"
    "➡️ keep the sealed baseline\n"
)
(Path("$SCRATCH") / "docs" / "spec" / "${FEATURE}.md").write_text(
    "restates the sealed baseline for late-lifecycle smoke\n"
)
# deliver at test, not yet aligned
d = (base / "deliver.example.yaml").read_text()
d = d.replace("stage: req-review", "stage: test")
(dst / "deliver.yaml").write_text(d)
plan = (Path("$VERIFY") / "plan.example.yaml").read_text()
plan = plan.replace("mode: selftest", "mode: test", 1)
plan = plan.replace("accepted: false", "accepted: true", 1)
# give one PASS with evidence so promote can snapshot
plan = plan.replace("status: UNPROVEN", "status: PASS", 1)
plan = plan.replace('evidence: "not run"', 'evidence: "late-lifecycle-smoke fixture"', 1)
(dst / "verify" / "plan.yaml").write_text(plan)
shutil.copy(Path("$VERIFY") / "unproven.example.md", dst / "unproven.md")
shutil.copy(Path("$OPS") / "ops.example.yaml", dst / "ops.yaml")
PY

fail() { echo "FAIL late-lifecycle: $*" >&2; exit 1; }

echo "--- test stage ---"
"${CHECK[@]}" --repo "$SCRATCH" --feature "$FEATURE" --stage test \
  || fail "expected PASS on test"

echo "--- promote refuse empty PASS ---"
BAD="$SCRATCH/docs/task/promo-bad"
mkdir -p "$BAD/verify"
cat > "$BAD/verify/plan.yaml" <<'YAML'
schema_version: 1
feature: promo-bad
mode: test
accepted: true
goal: g
non_goal: n
baseline_revision: 1
cases:
  - id: a
    slice_id: s
    baseline_item_id: B1
    dimension: correctness
    accepted: true
    status: FAIL
    evidence: x
YAML
if (cd "$SCRATCH" && bash "$ROOT/verify/scripts/promote.sh" promo-bad); then
  fail "promote should refuse FAIL"
fi
echo "OK  promote refuse FAIL"

echo "--- promote snapshot ---"
(cd "$SCRATCH" && bash "$ROOT/verify/scripts/promote.sh" "$FEATURE") \
  || fail "promote should accept PASS with evidence"
test -f "$SCRATCH/docs/test-case/${FEATURE}-patrol.yaml" \
  || fail "missing patrol pack"
grep -q 'promote receipt\|promoted from' "$SCRATCH/docs/test-case/${FEATURE}-patrol.yaml" \
  || fail "patrol pack missing promote marker"
echo "OK  promote snapshot"

echo "--- ops stage ---"
"${CHECK[@]}" --repo "$SCRATCH" --feature "$FEATURE" --stage ops \
  || fail "expected PASS on ops"

echo "--- aligned forge reject ---"
python3 - "$DST" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1]) / "deliver.yaml"
text = p.read_text()
text = text.replace("stage: test", "stage: done")
text = text.replace("aligned: false", "aligned: true")
text = text.replace('by: ""', "by: agent")
p.write_text(text)
PY
FORGE_OUT="$SCRATCH/aligned-forge.out"
if "${CHECK[@]}" --repo "$SCRATCH" --feature "$FEATURE" --stage test >"$FORGE_OUT" 2>&1; then
  fail "aligned with by: agent should FAIL"
fi
grep -qE 'aligned/done requires human by|agent filled signoff' "$FORGE_OUT" \
  || fail "expected aligned forge message"
grep -q '^HINT:' "$FORGE_OUT" || fail "expected FAIL HINT"
echo "OK  aligned forge rejected + HINT"

echo "--- aligned human by PASS ---"
python3 - "$DST" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1]) / "deliver.yaml"
text = p.read_text()
text = text.replace("by: agent", "by: example-owner")
p.write_text(text)
PY
PEOPLE_ROOT="$SCRATCH/people-root"
mkdir -p "$PEOPLE_ROOT/config"
printf 'schema_version: 1\npeople:\n  - example-owner\n' > "$PEOPLE_ROOT/config/people.yaml"
IDEV_ROOT="$PEOPLE_ROOT" "${CHECK[@]}" --repo "$SCRATCH" --feature "$FEATURE" --stage test \
  || fail "aligned with human by should PASS structure"
echo "OK  aligned human by"

echo "LATE_LIFECYCLE_SMOKE_OK"
