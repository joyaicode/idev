#!/usr/bin/env bash
# Replay example fixtures through check-feature.py. Exit 0 only if positives
# pass and negatives fail as expected.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
KERNEL="$(cd "${ROOT}/.." && pwd)"
DELIVER="${KERNEL}/deliver/references"
VERIFY="${KERNEL}/verify/references"
OPS="${KERNEL}/ops/references"
CHECK=(python3 "${ROOT}/check-feature.py")
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/idev-selfcheck-run.XXXXXX")"
export TMPDIR="${SCRATCH}"
# The run's own store, and the python lane unless the caller pinned a binary:
# a selfcheck never writes the person's ~/.idev, and the same tree gives the
# same answers whether or not a build is lying around. The lanes that need Go
# build their own.
export IDEV_DATA="${SCRATCH}/idev-data"
export IDEV_BIN="${IDEV_BIN:-off}"
FIX="$(mktemp -d "${SCRATCH}/idev-selfcheck.XXXXXX")"
FEATURE=example-change
DST="${FIX}/docs/task/${FEATURE}"
mkdir -p "${DST}/verify"

FAILURES="${SCRATCH}/.selfcheck-failures"
: > "${FAILURES}"
DONE=""

cleanup() {
  local rc=$?
  if [ -z "${DONE}" ] && [ "$rc" -ne 0 ]; then
    echo "selfcheck stopped early (exit ${rc}); the locks after this point did not run" >&2
  fi
  if [ -s "${FAILURES}" ]; then
    echo "selfcheck FAIL: $(wc -l < "${FAILURES}" | tr -d ' ') failure(s)" >&2
    sed 's/^/  - /' "${FAILURES}" >&2
    [ "$rc" -ne 0 ] || rc=1
  fi
  rm -rf "${SCRATCH}"
  exit "$rc"
}
trap cleanup EXIT

python3 - <<PY
from pathlib import Path
import shutil
base = Path("${DELIVER}")
dst = Path("${DST}")
b = (base / "baseline.example.yaml").read_text()
b = b.replace("sealed: false", "sealed: true")
(dst / "baseline.yaml").write_text(b)
shutil.copy(base / "req.example.yaml", dst / "req.yaml")
shutil.copy(base / "arch.example.yaml", dst / "arch.yaml")
shutil.copy(base / "design.example.md", dst / "design.md")
shutil.copy(base / "deliver.example.yaml", dst / "deliver.yaml")
shutil.copy(base / "review.example.md", dst / "review.md")
shutil.copy(base / "deliver-eval.example.md", dst / "deliver-eval.md")
(dst / "grill.md").write_text(
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
spec = Path("${FIX}") / "docs" / "spec"
spec.mkdir(parents=True)
(spec / "${FEATURE}.md").write_text("restates the sealed baseline\n")
shutil.copy(Path("${VERIFY}") / "plan.example.yaml", dst / "verify" / "plan.yaml")
shutil.copy(Path("${OPS}") / "ops.example.yaml", dst / "ops.yaml")
PY

# One broken lock must not hide the rest, so the main shell records and goes
# on. Inside ( ) or $( ) a failure still exits that subshell: the caller's
# `|| fail` and set -e depend on seeing it.
fail() {
  echo "selfcheck FAIL: $*" >&2
  printf '%s\n' "$*" >> "${FAILURES}"
  [ "${BASH_SUBSHELL}" -eq 0 ] || exit 1
}

run() {
  local stage="$1"
  "${CHECK[@]}" --repo "${FIX}" --feature "${FEATURE}" --stage "${stage}"
}

echo "=== positive stages ==="
for s in req-review req arch verify-plan code ops; do
  echo "--- $s ---"
  run "$s" || fail "expected PASS on $s"
done

echo "=== negative: arch without the design write-up ==="
python3 - <<PY
from pathlib import Path
Path("${DST}/design.md").rename(Path("${DST}/design.md.bak"))
PY
if run arch; then fail "expected FAIL when design.md is missing"; fi
python3 - <<PY
from pathlib import Path
Path("${DST}/design.md.bak").rename(Path("${DST}/design.md"))
PY

echo "=== negative: test stage with mode=selftest ==="
if run test; then fail "expected FAIL on test stage when plan.mode is selftest"; fi

echo "=== positive: test stage with mode=test ==="
python3 - <<PY
from pathlib import Path
import shutil
p = Path("${DST}/verify/plan.yaml")
p.write_text(p.read_text().replace("mode: selftest", "mode: test", 1))
shutil.copy(Path("${VERIFY}") / "unproven.example.md", Path("${DST}") / "unproven.md")
PY
run test || fail "expected PASS on test"
python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${VERIFY}") / "plan.example.yaml", Path("${DST}/verify/plan.yaml"))
up = Path("${DST}/unproven.md")
if up.exists():
    up.unlink()
PY

echo "=== negative: test mode missing unproven surfaces ==="
python3 - <<PY
from pathlib import Path
p = Path("${DST}/verify/plan.yaml")
p.write_text(p.read_text().replace("mode: selftest", "mode: test", 1))
PY
if run test; then fail "expected FAIL when unproven surfaces missing"; fi
python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${VERIFY}") / "plan.example.yaml", Path("${DST}/verify/plan.yaml"))
PY

echo "=== negative: invalid ticket YAML ==="
python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${DST}/baseline.yaml"), Path("${DST}/baseline.yaml.bak"))
Path("${DST}/baseline.yaml").write_text("sealed: [\n")
PY
if run req-review; then fail "expected FAIL on invalid baseline YAML"; fi
python3 - <<PY
from pathlib import Path
Path("${DST}/baseline.yaml").write_text(Path("${DST}/baseline.yaml.bak").read_text())
Path("${DST}/baseline.yaml.bak").unlink()
PY

echo "=== negative: missing deliver-eval ==="
python3 - <<PY
from pathlib import Path
Path("${DST}/deliver-eval.md").unlink()
PY
if run code; then fail "expected FAIL when deliver-eval.md missing"; fi
python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${DELIVER}") / "deliver-eval.example.md", Path("${DST}/deliver-eval.md"))
PY

echo "=== negative: review.md missing 编码规范 ==="
python3 - <<PY
from pathlib import Path
p = Path("${DST}/review.md")
text = p.read_text()
start = text.find("## 编码规范")
end = text.find("## 本轮允许改的路径")
if start >= 0 and end > start:
    p.write_text(text[:start] + text[end:])
else:
    raise SystemExit("selfcheck fixture missing 编码规范 section")
PY
if run code; then fail "expected FAIL when review.md missing 编码规范"; fi
python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${DELIVER}") / "review.example.md", Path("${DST}/review.md"))
PY


echo "=== negative: review coding placeholders P? ==="
python3 - <<PY
from pathlib import Path
Path("${DST}/review.md").write_text("# R\n\n## 编码规范\n\n- 场景命中: P?\n- 气味命中: C?\n- 纠正:\n\n## 本轮允许改的路径\n\n")
PY
if run code; then fail "expected FAIL on P?/C? placeholders"; fi
python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${DELIVER}") / "review.example.md", Path("${DST}/review.md"))
PY

echo "=== negative: refactor without guard ==="
python3 - <<PY
from pathlib import Path
p = Path("${DST}/review.md")
t = p.read_text()
p.write_text(t.replace("- 重构: 无", "- 重构: 有（预备式）", 1))
PY
if run code; then fail "expected FAIL on refactor without guard"; fi
python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${DELIVER}") / "review.example.md", Path("${DST}/review.md"))
PY

echo "=== negative: drop B3 slice ==="
python3 - <<PY
from pathlib import Path
p = Path("${DST}/req.yaml")
p.write_text(p.read_text().split("  - id: no-replay-change")[0])
PY
if run req; then fail "expected FAIL after dropping B3"; fi

python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${DELIVER}") / "req.example.yaml", Path("${DST}/req.yaml"))
PY

echo "=== negative: plan.goal rewritten ==="
python3 - <<PY
from pathlib import Path
p = Path("${DST}/verify/plan.yaml")
p.write_text(p.read_text().replace(
    'goal: "When approval.enabled is false, annotated methods run without creating a ticket."',
    'goal: "rewritten"',
    1,
))
PY
if run verify-plan; then fail "expected FAIL on rewritten plan.goal"; fi

python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${VERIFY}") / "plan.example.yaml", Path("${DST}/verify/plan.yaml"))
text = Path("${DST}/verify/plan.yaml").read_text()
text = text.replace("status: UNPROVEN", "status: PASS", 1)
Path("${DST}/verify/plan.yaml").write_text(text)
PY

echo "=== negative: PASS with evidence not run ==="
if run verify-plan; then fail "expected FAIL on PASS + not run"; fi

python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${VERIFY}") / "plan.example.yaml", Path("${DST}/verify/plan.yaml"))
shutil.copy(Path("${OPS}") / "ops.example.yaml", Path("${DST}/ops.yaml"))
p = Path("${DST}/ops.yaml")
p.write_text(p.read_text().replace("kind: feature", "kind: unknown", 1))
PY

echo "=== negative: ops kind unknown ==="
if run ops; then fail "expected FAIL on kind=unknown"; fi

python3 - <<PY
from pathlib import Path
text = Path("${OPS}/ops.example.yaml").read_text()
text = text.replace("kind: feature", "kind: onboard")
Path("${DST}/ops.yaml").write_text(text)
PY

echo "=== negative: onboard without handoff ==="
if run ops; then fail "expected FAIL on onboard without handoff"; fi

python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${DELIVER}") / "req.example.yaml", Path("${DST}/req.yaml"))
shutil.copy(Path("${DELIVER}") / "deliver.example.yaml", Path("${DST}/deliver.yaml"))
shutil.copy(Path("${OPS}") / "ops.example.yaml", Path("${DST}/ops.yaml"))
PY

echo "=== negative: slice must drift ==="
python3 - <<PY
from pathlib import Path
p = Path("${DST}/req.yaml")
p.write_text(p.read_text().replace(
    'must: "enabled=false → method body executes; no ticket side effect."',
    'must: "also emit a metric when disabled"',
    1,
))
PY
if run req; then fail "expected FAIL on slice must drift"; fi
python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${DELIVER}") / "req.example.yaml", Path("${DST}/req.yaml"))
PY

echo "=== negative: missing semantic_gate ==="
python3 - <<PY
from pathlib import Path
p = Path("${DST}/deliver.yaml")
text = p.read_text()
start = text.find("semantic_gate:")
end = text.find("last_rewind:")
if start < 0 or end < start:
    raise SystemExit("selfcheck fixture missing semantic_gate")
p.write_text(text[:start] + text[end:])
PY
if run req; then fail "expected FAIL when semantic_gate missing"; fi
python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${DELIVER}") / "deliver.example.yaml", Path("${DST}/deliver.yaml"))
PY

echo "=== negative: test surfaces missing boundary ==="
python3 - <<PY
from pathlib import Path
p = Path("${DST}/verify/plan.yaml")
p.write_text(p.read_text().replace("mode: selftest", "mode: test", 1))
Path("${DST}/unproven.md").write_text(
    "# UNPROVEN 面\n- dimension: concurrency\n  reason: none\n"
    "- dimension: performance\n  reason: none\n"
    "- dimension: ui-prototype\n  reason: none\n"
)
PY
if run test; then fail "expected FAIL when boundary surface missing"; fi
python3 - <<PY
from pathlib import Path
import shutil
shutil.copy(Path("${VERIFY}") / "plan.example.yaml", Path("${DST}/verify/plan.yaml"))
up = Path("${DST}/unproven.md")
if up.exists():
    up.unlink()
PY

echo "=== negative: ops missing the product handoff skill ==="
mkdir -p "${FIX}/.idev"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: acme' 'evolve: pilot' > "${FIX}/.idev/marker.yaml"
printf '%s\n' 'id: acme' 'required:' '  - {label: onboard, names: [acme-onboard]}' > "${FIX}/.idev/handoff.yaml"
rm -rf "${FIX}/.cursor/skills/acme-onboard"
if IDEV_OUTBOUND_NO_HOME=1 run ops; then fail "expected FAIL when the product handoff skill is missing"; fi
rm -f "${FIX}/.idev/handoff.yaml" "${FIX}/.idev/marker.yaml"

echo "=== positive: product without handoff does not require another product's skills ==="
IDEV_OUTBOUND_NO_HOME=1 bash "${ROOT}/outbound-skills-check.sh" --repo "${FIX}" \
  || fail "expected PASS when the product has no handoff"

echo "=== positive: outbound-skills-check with repo stubs ==="
bash "${ROOT}/outbound-skills-check.sh" --repo "${FIX}" \
  || fail "expected PASS on outbound-skills-check with stubs"

echo "=== negative: outbound-skills-check without the product skill ==="
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: acme' 'evolve: pilot' > "${FIX}/.idev/marker.yaml"
printf '%s\n' 'id: acme' 'required:' '  - {label: onboard, names: [acme-onboard]}' > "${FIX}/.idev/handoff.yaml"
if IDEV_OUTBOUND_NO_HOME=1 bash "${ROOT}/outbound-skills-check.sh" --repo "${FIX}"; then
  fail "expected FAIL when the product handoff skill is missing"
fi
rm -f "${FIX}/.idev/handoff.yaml" "${FIX}/.idev/marker.yaml"

TRACE=(python3 "${ROOT}/trace.py")
TRACE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/idev-trace-selfcheck.XXXXXX")"
BAD="${SCRATCH}/idev-trace-bad.yaml"
export IDEV_TRACE_DIR="${TRACE_DIR}"

echo "=== positive: trace example ==="
"${TRACE[@]}" check "${KERNEL}/references/trace.example.yaml" \
  || fail "expected PASS on trace.example.yaml"

echo "=== negative: trace missing route.why ==="
python3 - <<PY
from pathlib import Path
text = Path("${KERNEL}/references/trace.example.yaml").read_text()
text = text.replace('why: "deliver.yaml.stage=code; user asked to implement include paths, not a phenomenon."', "why: \"\"", 1)
Path("${BAD}").write_text(text)
PY
if "${TRACE[@]}" check "${BAD}"; then fail "expected FAIL on empty route.why"; fi

echo "=== negative: v2 missing thinking.summary ==="
python3 - <<PY2
from pathlib import Path
text = Path("${KERNEL}/references/trace.example.yaml").read_text()
text = text.replace('summary: "看到 stage=code 与「补测试」诉求；排除 ops（无现象）与直接 verify（plan 未 accepted）；先走 deliver/code，并打开 java 规约。"', 'summary: ""', 1)
Path("${BAD}").write_text(text)
PY2
if "${TRACE[@]}" check "${BAD}"; then fail "expected FAIL on empty thinking.summary"; fi

echo "=== positive: trace append + last ==="
"${TRACE[@]}" append "${KERNEL}/references/trace.example.yaml" >/dev/null \
  || fail "expected append to succeed"
"${TRACE[@]}" last >/dev/null || fail "expected last after append"

echo "=== positive: S2 short render ==="
SHORT="${SCRATCH}/idev-trace-short.yaml"
python3 - <<PY3
from pathlib import Path
text = Path("${KERNEL}/references/trace.example.yaml").read_text()
text = text.replace("  risk_tier: P1\n", "  risk_tier: P1\n  scenario: S2\n", 1)
Path("${SHORT}").write_text(text)
PY3
OUT="$("${TRACE[@]}" render "${SHORT}")" || fail "expected S2 render to succeed"
echo "${OUT}" | grep -q '| trigger |' || fail "S2 render missing trigger"
if echo "${OUT}" | grep -q '| thinking |'; then fail "S2 render should omit thinking"; fi
rm -f "${SHORT}"

echo "=== positive: workflow recipes ==="
WF_ARGS=(--recipes-dir "${KERNEL}/workflows")
PROD_ROOT="$(python3 -c "import json;from pathlib import Path;p=Path('${KERNEL}/state/outbound-config.json');d=json.loads(p.read_text()) if p.is_file() else {};print(d.get('product_root') or '')")"
if [ -n "${PROD_ROOT}" ] && [ -d "${PROD_ROOT}/.idev/workflows" ] \
  && [ -n "$(python3 "${ROOT}/lib/product_marker.py" --check "${PROD_ROOT}")" ]; then
  WF_ARGS+=(--product-recipes "${PROD_ROOT}/.idev/workflows")
fi
WF_CHECK=(python3 "${ROOT}/workflow-check.py" "${WF_ARGS[@]}")
"${WF_CHECK[@]}" || fail "expected PASS on workflow recipes"
echo "=== lock: entry lists kernel recipes, not product aliases ==="
DISC="$(mktemp -d "${TMPDIR:-/tmp}/idev-disc.XXXXXX")"
mkdir -p "$DISC/prod"
printf '%s\n' 'schema_version: 1' 'id: sample-ui' 'aliases: [UI自动化]' 'steps:' '  - {id: s, kind: human.gate, with: {will_write: []}}' \
  > "$DISC/prod/sample-ui.yaml"
python3 "${ROOT}/workflow-check.py" --recipes-dir "${KERNEL}/workflows" --product-recipes "$DISC/prod" \
  >"${SCRATCH}"/idev-disc-clean.out 2>&1 || { cat "${SCRATCH}"/idev-disc-clean.out; rm -rf "$DISC"; fail "entry should not name a product alias"; }
cp -R "${KERNEL}/workflows" "$DISC/workflows"
sed 's/适用所有端到端交付产品/UI自动化 适用所有端到端交付产品/' "${KERNEL}/SKILL.md" > "$DISC/SKILL.md"
if python3 "${ROOT}/workflow-check.py" --recipes-dir "$DISC/workflows" --product-recipes "$DISC/prod" >"${SCRATCH}"/idev-disc-leak.out 2>&1; then
  rm -rf "$DISC"; fail "product alias in the entry description should fail workflow-check"
fi
grep -q "names product recipe 'UI自动化'" "${SCRATCH}"/idev-disc-leak.out || { cat "${SCRATCH}"/idev-disc-leak.out; rm -rf "$DISC"; fail "leak message missing"; }
sed 's/path-view、//' "${KERNEL}/SKILL.md" > "$DISC/SKILL.md"
if python3 "${ROOT}/workflow-check.py" --recipes-dir "$DISC/workflows" >"${SCRATCH}"/idev-disc-miss.out 2>&1; then
  rm -rf "$DISC"; fail "entry missing a kernel recipe id should fail workflow-check"
fi
rm -rf "$DISC"
if rg -q 'outbound-config' "${ROOT}/ticket_metrics.py"; then
  fail "ticket_metrics must not pick the session repo from the install ledger"
fi
if rg -q 'framework/config' "${KERNEL}/workflows/lite-change.yaml"; then
  fail "lite-change recipe still carries product pitfalls"
fi
echo "OK  entry discovery"
echo "=== lock: execution pages resolve ticket paths through doc_home ==="
IDEV_HOME="${KERNEL}"
if rg -n 'docs/test-case/<(feature|f)>|docs/task/\*/' "$IDEV_HOME/ops" "$IDEV_HOME/verify" "$IDEV_HOME/deliver" \
  "$IDEV_HOME/workflows" "$IDEV_HOME/conventions" "$IDEV_HOME/references/operator-cheatsheet.md" \
  "$IDEV_HOME/references/chat-confirm-signoff.md"; then
  fail "execution pages must name doc_home.py --key instead of a fixed docs/ path"
fi
echo "OK  ticket paths via doc_home"
echo "=== positive: workflow run example ==="
python3 "${ROOT}/workflow-check.py" --run "${KERNEL}/references/workflow-run.example.yaml" \
  || fail "expected PASS on workflow-run.example.yaml"

echo "=== positive: S8 short render ==="
SHORT8="${SCRATCH}/idev-trace-short8.yaml"
python3 - <<PY8
from pathlib import Path
text = Path("${KERNEL}/references/trace.example.yaml").read_text()
text = text.replace("  risk_tier: P1\n", "  risk_tier: P1\n  scenario: S8\n", 1)
Path("${SHORT8}").write_text(text)
PY8
OUT8="$("${TRACE[@]}" render "${SHORT8}")" || fail "expected S8 render to succeed"
echo "${OUT8}" | grep -q '| trigger |' || fail "S8 render missing trigger"
if echo "${OUT8}" | grep -q '| thinking |'; then fail "S8 render should omit thinking"; fi
if echo "${OUT8}" | grep -q '| hops |'; then fail "S8 render should omit hops"; fi
rm -f "${SHORT8}"

echo "=== positive: observation fields on the path ==="
OBS_PATH="$("${TRACE[@]}" path "${KERNEL}/references/trace.example.yaml")" \
  || fail "expected path of the example to succeed"
echo "${OBS_PATH}" | grep -q 'skills:' || fail "path missing skills"
echo "${OBS_PATH}" | grep -q 'explicit: idev' || fail "path missing skill how"
echo "${OBS_PATH}" | grep -q 'delegate→none' || fail "path missing delegate choice"
echo "${OBS_PATH}" | grep -q 'model→inherit' || fail "path missing model choice"
echo "${OBS_PATH}" | grep -q 'user→skill:idev' || fail "path missing skill hop"
echo "${OBS_PATH}" | grep -q 'model=inherit' || fail "path missing model on the hop"
echo "${OBS_PATH}" | grep -q '4s' || fail "path missing duration"

echo "=== positive: old trace without observation fields still passes ==="
PLAIN="${SCRATCH}/idev-trace-plain.yaml"
cat > "${PLAIN}" <<'EOF'
schema_version: 2
at: "2026-10-23T00:00:00+08:00"
feature: example-change
intent: "keep old traces valid"
invoke:
  trigger: "继续"
  matched: "S2"
thinking:
  summary: "仍在当前阶段"
route:
  module: deliver
  scenario: S2
  why: "stage pointer"
check_feature: skipped
EOF
"${TRACE[@]}" check "${PLAIN}" || fail "expected PASS on a v2 trace without observation fields"
rm -f "${PLAIN}"

echo "=== negative: observation fields must be well formed ==="
python3 - <<PYOBS
from pathlib import Path
src = Path("${KERNEL}/references/trace.example.yaml").read_text()
bad = Path("${SCRATCH}")
bad.joinpath("idev-trace-how.yaml").write_text(src.replace("how: explicit", "how: guessed", 1))
bad.joinpath("idev-trace-edge.yaml").write_text(src.replace("    to: skill:idev\n", "", 1))
bad.joinpath("idev-trace-duration.yaml").write_text(src.replace("duration_s: 4", "duration_s: soon", 1))
bad.joinpath("idev-trace-delegate.yaml").write_text(
    src.replace("    chose: none\n", "    chose: idev-nobody\n", 1)
)
skill = src.replace(
    "    - name: idev\n      path: \"~/.cursor/skills/idev/SKILL.md\"\n      why: \"用户要求补完剩余测试\"\n",
    "    - idev\n",
    1,
)
bad.joinpath("idev-trace-skill.yaml").write_text(skill)
PYOBS
if "${TRACE[@]}" check "${SCRATCH}/idev-trace-how.yaml"; then fail "expected FAIL on invoke.how"; fi
if "${TRACE[@]}" check "${SCRATCH}/idev-trace-edge.yaml"; then fail "expected FAIL on one-sided hop"; fi
if "${TRACE[@]}" check "${SCRATCH}/idev-trace-duration.yaml"; then fail "expected FAIL on duration_s"; fi
if "${TRACE[@]}" check "${SCRATCH}/idev-trace-delegate.yaml"; then fail "expected FAIL on unknown delegate"; fi
if "${TRACE[@]}" check "${SCRATCH}/idev-trace-skill.yaml"; then fail "expected FAIL on skill item without name"; fi

echo "=== positive: observation coverage is not a hard alarm ==="
OBS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/idev-trace-obs.XXXXXX")"
cp "${KERNEL}/references/trace.example.yaml" "${OBS_DIR}/20261023-001.yaml"
python3 "${ROOT}/audit_traces_lib.py" "${OBS_DIR}" 5 >"${SCRATCH}"/idev-trace-obs.out
grep -q '观察覆盖' "${SCRATCH}"/idev-trace-obs.out || fail "audit missing observation coverage"
grep -q '写了组件跳 | 1 |' "${SCRATCH}"/idev-trace-obs.out || fail "audit did not count the hop"
grep -q '写了委派决定 | 1 |' "${SCRATCH}"/idev-trace-obs.out || fail "audit did not count delegate"
HC_OBS="$(sed -n 's/^HARD_COUNT=//p' "${SCRATCH}"/idev-trace-obs.out)"
[ "${HC_OBS:-x}" = "0" ] || { cat "${SCRATCH}"/idev-trace-obs.out; fail "observation fields raised HARD_COUNT"; }
rm -rf "${OBS_DIR}"

echo "=== write-config persists pilot and extra keys ==="
WCFG="${SCRATCH}/idev-outbound-cfg.json"
printf '%s\n' '{"pilot":"joypaas","custom":"keep","joypaas_root":"/old","required":["stale"]}' > "${WCFG}"
python3 "${ROOT}/lib/outbound_registry.py" write-config \
  --root "${KERNEL}" \
  --cfg "${WCFG}" \
  --product-root "/tmp/jp-root" \
  --pack joypaas >/dev/null \
  || fail "write-config should succeed"
python3 - "${WCFG}" <<'PY' || { rm -f "${WCFG}"; fail "write-config dropped pilot or extra key"; }
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
assert d.get("pilot")=="joypaas", d
assert d.get("custom")=="keep", d
assert d.get("product_root")=="/tmp/jp-root", d
assert d.get("joypaas_root")=="/old", d
assert d.get("required")==["stale"], d
PY

echo "=== write-config keeps other pilot unless --force-pack ==="
printf '%s\n' '{"pilot":"example","custom":"keep","joypaas_root":"/old"}' > "${WCFG}"
python3 "${ROOT}/lib/outbound_registry.py" write-config \
  --root "${KERNEL}" \
  --cfg "${WCFG}" \
  --product-root "/tmp/jp-root" \
  --pack joypaas >/dev/null \
  || fail "write-config keep-pilot should succeed"
python3 - "${WCFG}" <<'PY' || { rm -f "${WCFG}"; fail "write-config overwrote other pilot"; }
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
assert d.get("pilot")=="example", d
assert d.get("custom")=="keep", d
assert d.get("joypaas_root")=="/old", d
PY
python3 "${ROOT}/lib/outbound_registry.py" write-config \
  --root "${KERNEL}" \
  --cfg "${WCFG}" \
  --product-root "/tmp/jp-forced" \
  --pack joypaas \
  --force-pack >/dev/null \
  || fail "write-config --force-pack should succeed"
python3 - "${WCFG}" <<'PY' || { rm -f "${WCFG}"; fail "write-config --force-pack did not switch"; }
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
assert d.get("pilot")=="joypaas", d
assert d.get("product_root")=="/tmp/jp-forced", d
assert d.get("joypaas_root")=="/old", d
PY
rm -f "${WCFG}"

echo "=== resolve: current product is the pilot, install ledger is not ==="
RTMP="$(mktemp -d "${TMPDIR:-/tmp}/idev-registry-root.XXXXXX")"
mkdir -p "${RTMP}/handoffs" "${RTMP}/state"
cp "${KERNEL}/handoffs/registry.yaml" "${RTMP}/handoffs/registry.yaml"
printf '%s\n' '{"pilot":"joypaas"}' > "${RTMP}/state/outbound-config.json"
pack_of() {
  python3 "${ROOT}/lib/outbound_registry.py" resolve --root "${RTMP}" "$@" \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('pack') or '')"
}
PACK="$(pack_of --discovered)"
[ -z "$PACK" ] || { rm -rf "${RTMP}"; fail "install ledger must not select the session pack, got ${PACK}"; }
PACK="$(pack_of --install)"
[ -z "$PACK" ] || { rm -rf "${RTMP}"; fail "install ledger must not become the session pack, got ${PACK}"; }
OTHER="$(mktemp -d "${TMPDIR:-/tmp}/idev-other-product.XXXXXX")"
PACK="$(pack_of --repo "${OTHER}")"
[ -z "$PACK" ] || { rm -rf "${RTMP}" "${OTHER}"; fail "a product without handoff must not inherit the ledger, got ${PACK}"; }
HIT="$(mktemp -d "${TMPDIR:-/tmp}/idev-handoff-product.XXXXXX")"
mkdir -p "${HIT}/.idev"
printf '%s\n' 'id: acme' 'required:' '  - {label: onboard, names: [acme-onboard]}' > "${HIT}/.idev/handoff.yaml"
PACK="$(pack_of --repo "${HIT}")"
[ -z "$PACK" ] || { rm -rf "${RTMP}" "${OTHER}" "${HIT}"; fail "handoff without marker must not select a pack, got ${PACK}"; }
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: acme' 'evolve: pilot' > "${HIT}/.idev/marker.yaml"
PACK="$(pack_of --repo "${HIT}")"
[ "$PACK" = "acme" ] || { rm -rf "${RTMP}" "${OTHER}" "${HIT}"; fail "marked product handoff should select its pack, got ${PACK}"; }
rm -rf "${RTMP}" "${OTHER}" "${HIT}"

echo "=== discover: marker admits an evolve pilot ==="
DTMP="$(mktemp -d "${TMPDIR:-/tmp}/idev-discover.XXXXXX")"
mkdir -p "${DTMP}/acme/.git" "${DTMP}/acme/.idev" "${DTMP}/bare/.git" "${DTMP}/bare/.idev" "${DTMP}/quiet/.idev"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: acme' 'evolve: pilot' > "${DTMP}/acme/.idev/marker.yaml"
printf '%s\n' 'id: bare' > "${DTMP}/bare/.idev/handoff.yaml"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: quiet' 'evolve: off' > "${DTMP}/quiet/.idev/marker.yaml"
DISC="$(IDEV_DISCOVER_ROOTS="${DTMP}" python3 "${ROOT}/lib/product_marker.py" --depth 2)"
python3 - "${DISC}" <<'PY' || { rm -rf "${DTMP}"; fail "discover should list only the evolve pilot"; }
import json, sys
rows = json.loads(sys.argv[1])
ids = sorted(row["id"] for row in rows)
assert ids == ["acme"], rows
PY
rm -rf "${DTMP}"

echo "=== link-outbound keeps other pilot ==="
LTMP="$(mktemp -d "${TMPDIR:-/tmp}/idev-link-root.XXXXXX")"
mkdir -p "${LTMP}/state"
printf '%s\n' '{"pilot":"example","joypaas_root":"/old"}' > "${LTMP}/state/outbound-config.json"
IDEV_ROOT="${LTMP}" bash "${ROOT}/link-outbound-skills.sh" >"${SCRATCH}"/idev-link-keep.out \
  || { rm -rf "${LTMP}"; fail "link-outbound should exit 0 when keeping other pilot"; }
grep -q 'KEEP existing pilot example' "${SCRATCH}"/idev-link-keep.out \
  || { rm -rf "${LTMP}"; fail "link-outbound should announce KEEP"; }
python3 - "${LTMP}/state/outbound-config.json" <<'PY' || { rm -rf "${LTMP}"; fail "link-outbound rewrote other pilot"; }
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
assert d.get("pilot")=="example", d
assert d.get("joypaas_root")=="/old", d
PY
rm -rf "${LTMP}"

echo "=== heal does not silent-bind empty config ==="
HTMP="$(mktemp -d "${TMPDIR:-/tmp}/idev-heal-root.XXXXXX")"
mkdir -p "${HTMP}/state"
IDEV_ROOT="${HTMP}" bash "${ROOT}/link-outbound-skills.sh" --heal >"${SCRATCH}"/idev-link-heal.out \
  || { rm -rf "${HTMP}"; fail "heal on empty config should exit 0"; }
grep -q 'SKIP heal' "${SCRATCH}"/idev-link-heal.out \
  || { rm -rf "${HTMP}"; fail "heal on empty config should SKIP"; }
if [ -f "${HTMP}/state/outbound-config.json" ]; then
  rm -rf "${HTMP}"
  fail "heal must not write outbound-config.json"
fi
rm -rf "${HTMP}"

echo "=== pack-link without --pack does not guess a product ==="
set +e
python3 "${ROOT}/lib/outbound_registry.py" pack-link \
  --root "${KERNEL}" >"${SCRATCH}"/idev-pack-link-nopack.out 2>&1
pack_rc=$?
set -e
[ "$pack_rc" -ne 0 ] || fail "pack-link without --pack should fail"
if grep -q 'joypaas-onboard-diagnose' "${SCRATCH}"/idev-pack-link-nopack.out; then
  fail "pack-link without --pack listed a product skill"
fi

echo "=== opt-in without pack does not write config ==="
OTMP="$(mktemp -d "${TMPDIR:-/tmp}/idev-link-nopack.XXXXXX")"
mkdir -p "${OTMP}/state"
set +e
IDEV_ROOT="${OTMP}" bash "${ROOT}/link-outbound-skills.sh" >"${SCRATCH}"/idev-link-nopack.out 2>&1
opt_rc=$?
set -e
[ "$opt_rc" -ne 0 ] || { rm -rf "${OTMP}"; fail "link-outbound without --pack should fail closed"; }
grep -q 'name --pack' "${SCRATCH}"/idev-link-nopack.out \
  || { rm -rf "${OTMP}"; fail "link-outbound without --pack should ask for --pack"; }
if [ -f "${OTMP}/state/outbound-config.json" ]; then
  rm -rf "${OTMP}"
  fail "link-outbound without --pack must not write outbound-config.json"
fi
if grep -q 'joypaas-onboard-diagnose' "${SCRATCH}"/idev-link-nopack.out; then
  rm -rf "${OTMP}"
  fail "link-outbound without --pack listed a product skill"
fi
rm -rf "${OTMP}"

echo "=== lock: S8 requires one product name; no three-product aliases ==="
if [ -e "${KERNEL}/workflows/ui-lifecycle-batch.yaml" ]; then
  fail "ui-lifecycle-batch recipe must stay deleted"
fi
if [ -e "${KERNEL}/references/workflow-ui-lifecycle-batch.md" ]; then
  fail "workflow-ui-lifecycle-batch.md must stay deleted"
fi
if rg -q '三产品UI自动化|依次UI自动化' \
  "${KERNEL}/SKILL.md" \
  "${KERNEL}/references/invoke.md"; then
  fail "live invoke still has three-product aliases"
fi

echo "=== lock: core pages have no JoyPaaS proprietary tokens ==="
if ! bash "${ROOT}/core-strip-check.sh" >"${SCRATCH}"/idev-core-strip.out 2>&1; then
  cat "${SCRATCH}"/idev-core-strip.out || true
  fail "core-strip-check"
fi

echo "=== lock: ops-schema is not the only handoff ==="
if rg -q '`kind=onboard` → `joypaas-onboard-diagnose`' "${OPS}/ops-schema.md"; then
  fail "ops-schema still maps onboard uniquely to joypaas-onboard-diagnose"
fi
if rg -q '交给 onboard / jmiss' "${KERNEL}/deliver/references/deliver-schema.md"; then
  fail "deliver-schema still says 交给 onboard / jmiss"
fi
if rg -q '不要写回 joypaas 仓|不要 PR 进 joypaas|不写回 joypaas 仓' \
  "${KERNEL}/verify/SKILL.md" \
  "${KERNEL}/verify/references/evolve.md" \
  "${KERNEL}/verify/references/0007-verify-conductor-evolve.md" \
  "${KERNEL}/ops/references/0010-ops-conductor.md"; then
  fail "verify/ops live docs still say write back to joypaas repo"
fi
if rg -q '先走仓库 `joypaas-frontend-test`' \
  "${KERNEL}/verify/references/plan-schema.md"; then
  fail "plan-schema still treats joypaas-frontend-test as the only cookie skill"
fi

echo "=== lock: no module-level ledgers (only entry state/ledger.yaml) ==="
for m in deliver verify ops docs; do
  [ ! -e "${KERNEL}/${m}/state/ledger.yaml" ] || fail "module ledger must not exist: ${m}/state/ledger.yaml"
done
[ -f "${KERNEL}/state/ledger.yaml" ] || fail "missing entry ledger state/ledger.yaml"

echo "=== positive: unknown IDEV_PILOT does not require a kernel pack ==="
IDEV_PILOT=example IDEV_OUTBOUND_NO_HOME=1 bash "${ROOT}/outbound-skills-check.sh" --repo "${FIX}" \
  || fail "expected PASS when IDEV_PILOT is not a registered pack"


echo "=== lock: path-view runtime path ==="
bash "${KERNEL}/scripts/path-view.sh" >"${SCRATCH}"/idev-path.out 2>&1 \
  || fail "path-view failed"
grep -q '运行路径' "${SCRATCH}"/idev-path.out || fail "path-view missing 运行路径 header"
bash "${KERNEL}/scripts/trace.sh" path-stats -n 5 >"${SCRATCH}"/idev-path-stats.out 2>&1 \
  || fail "path-stats failed"
grep -q 'path-stats' "${SCRATCH}"/idev-path-stats.out || fail "path-stats missing header"
# no score language
if rg -qi '总分|score|百分' "${SCRATCH}"/idev-path.out "${SCRATCH}"/idev-path-stats.out; then
  fail "path-view must not emit scores"
fi
[ -x "${KERNEL}/scripts/path-view.sh" ] || fail "path-view.sh not executable"
[ -f "${KERNEL}/workflows/path-view.yaml" ] || fail "missing path-view workflow"
echo "OK  path-view lock"

echo "=== lock: single authority for routing / ticket / H-rules ==="
BRIEF="${KERNEL}/references/agent-brief.md"
SKILL="${KERNEL}/SKILL.md"
CHEAT="${KERNEL}/references/operator-cheatsheet.md"
INVOKE="${KERNEL}/references/invoke.md"
if rg -q '都没有则' "$BRIEF"; then
  fail "agent-brief still inlines a shortened ticket-binding algorithm"
fi
if ! rg -q '认票' "$INVOKE"; then
  fail "invoke.md missing 认票 authority"
fi
if ! rg -q '最近一条 trace' "$INVOKE"; then
  fail "invoke.md 认票 missing recent-trace step"
fi
if rg -q '再没有用最近一条 trace' "$CHEAT"; then
  fail "cheatsheet still copies the 认票 algorithm"
fi
if rg -q '全文 \[cheatsheet §7\]' "$SKILL"; then
  fail "SKILL.md still points H1-H6 at cheatsheet §7"
fi
if ! rg -q 'invoke.md' "$SKILL"; then
  fail "SKILL.md missing invoke.md pointer for 认票 / H1-H6"
fi
if rg -q '^\| S1 \|' "$INVOKE"; then
  fail "invoke.md still has a second S1-S8 scene table"
fi
for wf in localdev-start localdev-stop ui-lifecycle-full ui-automation-build multi-agent-coord; do
  if [ -e "${KERNEL}/workflows/${wf}.yaml" ]; then
    fail "product pipeline ${wf} still sits in the idev kernel"
  fi
done
if [ -e "${KERNEL}/packs/joypaas" ] || [ -d "${KERNEL}/packs" ]; then
  fail "product pack directory still sits in the idev kernel"
fi
if [ -e "${KERNEL}/joypaas-ui-lifecycle" ]; then
  fail "product overlay symlink still sits in the idev kernel"
fi
if rg -q '^joypaas:' "${KERNEL}/handoffs/registry.yaml"; then
  fail "kernel registry still names a product"
fi
if rg -q 'npm run lint-fix' "${KERNEL}/scripts/coding-scan.sh"; then
  fail "coding-scan still hardcodes npm run lint-fix"
fi
if [ -n "${PROD_ROOT}" ] && [ -f "${PROD_ROOT}/.idev/extensions.yaml" ]; then
  python3 "${KERNEL}/scripts/stage-extensions.py" --repo "${PROD_ROOT}" --check-all \
    >"${SCRATCH}"/idev-stage-ext-prod.out || { cat "${SCRATCH}"/idev-stage-ext-prod.out; fail "installed product extensions.yaml has a missing page"; }
fi
if [ -n "${PROD_ROOT}" ] && [ -d "${PROD_ROOT}/.idev/checks" ]; then
  bash "${KERNEL}/scripts/product-checks.sh" "${PROD_ROOT}" \
    >"${SCRATCH}"/idev-prod-checks.out || { cat "${SCRATCH}"/idev-prod-checks.out; fail "installed product checks failed"; }
fi
echo "OK  routing authority + product pipelines stay out of the kernel"

echo "=== lock: product intermediates stay out of the kernel ==="
SINK="${KERNEL}/scripts/lib/product_sink.py"
PROMO="${KERNEL}/scripts/kernel-promote-check.sh"
HERE="$(python3 "$SINK" traces)"
# product_sink.kernel_root() resolves symlinks, so when ~/.cursor/skills/idev
# is a symlink into a checkout this comes back as the physical path and never
# contains ".cursor/skills/idev". Accept either shape — what this lock is
# really asserting is that a conductor cwd sinks into the kernel's own
# state/traces rather than into a product repo.
case "$HERE" in
  */.cursor/skills/idev/state/traces) ;;
  */idev/state/traces) ;;
  *) fail "conductor cwd should sink traces to kernel state/traces, got $HERE" ;;
esac
PREPO="$(mktemp -d "${TMPDIR:-/tmp}/idev-product.XXXXXX")"
git -C "$PREPO" init -q
PREPO="$(cd "$PREPO" && pwd -P)"
PDIR="$(cd "$PREPO" && python3 "$SINK" traces)"
case "$PDIR" in
  "$PREPO/.idev/traces") ;;
  *) rm -rf "$PREPO"; fail "product repo should sink traces to .idev/traces, got $PDIR" ;;
esac
[ ! -f "$PREPO/.idev/marker.yaml" ] || { rm -rf "$PREPO"; fail "printing a sink must not create a marker"; }
(cd "$PREPO" && python3 "$SINK" traces --mkdir >/dev/null)
grep -q 'marker: idev' "$PREPO/.idev/marker.yaml" || { rm -rf "$PREPO"; fail "first save should write marker"; }
grep -q 'evolve: false' "$PREPO/.idev/marker.yaml" || { rm -rf "$PREPO"; fail "first marker must not enroll self-evolution"; }
grep -q 'stages:' "$PREPO/.idev/extensions.yaml" 2>/dev/null || { rm -rf "$PREPO"; fail "first save should write extensions.yaml with stages"; }
[ -f "$PREPO/.idev/checks/.gitkeep" ] || { rm -rf "$PREPO"; fail "first save should write checks/.gitkeep"; }
[ -f "$PREPO/.idev/strip-tokens.txt" ] || { rm -rf "$PREPO"; fail "first save should write strip-tokens.txt"; }
grep -qF '!.idev/memory.md' "$PREPO/.gitignore" 2>/dev/null || { rm -rf "$PREPO"; fail "first save should keep .idev/memory.md in .gitignore"; }
grep -qF '!.idev/task/' "$PREPO/.gitignore" 2>/dev/null || { rm -rf "$PREPO"; fail "first save should keep .idev/task/ in .gitignore"; }
grep -qF '!.idev/docs/' "$PREPO/.gitignore" 2>/dev/null || { rm -rf "$PREPO"; fail "first save should keep .idev/docs/ in .gitignore"; }
mkdir -p "$PREPO/.idev/task/demo" "$PREPO/.idev/docs/prd"
printf '%s\n' ticket > "$PREPO/.idev/task/demo/deliver.yaml"
printf '%s\n' spec > "$PREPO/.idev/docs/prd/demo.md"
if git -C "$PREPO" check-ignore -q "$PREPO/.idev/task/demo/deliver.yaml"; then
  rm -rf "$PREPO"
  fail "native ticket must stay visible to git"
fi
if git -C "$PREPO" check-ignore -q "$PREPO/.idev/docs/prd/demo.md"; then
  rm -rf "$PREPO"
  fail "native docs must stay visible to git"
fi
BARE="$(mktemp -d "${TMPDIR:-/tmp}/idev-bare-evolve.XXXXXX")"
mkdir -p "$BARE/.idev"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: bare' > "$BARE/.idev/marker.yaml"
python3 - "$BARE" "${KERNEL}/scripts/lib" <<'PY' || { rm -rf "$PREPO" "$BARE"; fail "missing evolve must stay off"; }
import sys
sys.path.insert(0, sys.argv[2])
from product_marker import load_marker
marker = load_marker(sys.argv[1])
assert marker.get("evolve_pilot") is False, marker
assert marker.get("evolve") == "off", marker
PY
rm -rf "$BARE"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: kept' 'evolve: pilot' > "$PREPO/.idev/marker.yaml"
(cd "$PREPO" && python3 "$SINK" traces --mkdir >/dev/null)
grep -q 'id: kept' "$PREPO/.idev/marker.yaml" || { rm -rf "$PREPO"; fail "later save must not rewrite marker id"; }
grep -q 'evolve: pilot' "$PREPO/.idev/marker.yaml" || { rm -rf "$PREPO"; fail "later save must not rewrite evolve"; }
rm -rf "$PREPO"
printf '%s\n' 'routes stay generic' > "${TMPDIR:-/tmp}/idev-promote-ok.md"
bash "$PROMO" "${TMPDIR:-/tmp}/idev-promote-ok.md" >/dev/null \
  || fail "kernel-promote-check should pass a generic draft"
printf '%s\n' 'call JoypaasAppService here' > "${TMPDIR:-/tmp}/idev-promote-bad.md"
if bash "$PROMO" "${TMPDIR:-/tmp}/idev-promote-bad.md" >/dev/null; then
  fail "kernel-promote-check should reject an unstripped product draft"
fi
echo "OK  product .idev sink + kernel promote gate"

echo "=== lock: stage extensions follow the marker ==="
EXT="$(mktemp -d "${TMPDIR:-/tmp}/idev-ext.XXXXXX")"
git -C "$EXT" init -q
EXT="$(cd "$EXT" && pwd -P)"
python3 "${KERNEL}/scripts/stage-extensions.py" code --repo "$EXT" \
  >"${SCRATCH}"/idev-ext-none.out || { rm -rf "$EXT"; fail "unmarked repo should not fail stage-extensions"; }
if grep -q '^OPEN ' "${SCRATCH}"/idev-ext-none.out; then
  rm -rf "$EXT"
  fail "unmarked repo must not open product pages"
fi
mkdir -p "$EXT/.idev"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: acme' 'evolve: false' > "$EXT/.idev/marker.yaml"
printf '%s\n' 'schema_version: 1' 'stages:' '  code:' '    - pack/note.md' > "$EXT/.idev/extensions.yaml"
if python3 "${KERNEL}/scripts/stage-extensions.py" code --repo "$EXT" >"${SCRATCH}"/idev-ext-miss.out 2>&1; then
  rm -rf "$EXT"
  fail "missing declared page should fail"
fi
grep -q 'missing .idev/pack/note.md' "${SCRATCH}"/idev-ext-miss.out || { rm -rf "$EXT"; cat "${SCRATCH}"/idev-ext-miss.out; fail "missing page message"; }
mkdir -p "$EXT/.idev/pack"
printf '%s\n' 'note' > "$EXT/.idev/pack/note.md"
python3 "${KERNEL}/scripts/stage-extensions.py" code --repo "$EXT" \
  >"${SCRATCH}"/idev-ext-ok.out || { rm -rf "$EXT"; cat "${SCRATCH}"/idev-ext-ok.out; fail "present page should pass"; }
grep -q "^OPEN $EXT/.idev/pack/note.md" "${SCRATCH}"/idev-ext-ok.out || { rm -rf "$EXT"; fail "OPEN line missing"; }
mkdir -p "$EXT/.idev/checks"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$EXT/.idev/checks/ok.sh"
bash "${KERNEL}/scripts/product-checks.sh" "$EXT" >"${SCRATCH}"/idev-ext-checks.out \
  || { rm -rf "$EXT"; cat "${SCRATCH}"/idev-ext-checks.out; fail "product check script should pass"; }
grep -q 'product-checks PASS' "${SCRATCH}"/idev-ext-checks.out || { rm -rf "$EXT"; fail "product-checks summary"; }
rm -rf "$EXT"

SX="${KERNEL}/scripts/stage-extensions.py"
EXTP="$(mktemp -d "${TMPDIR:-/tmp}/idev-extroot.XXXXXX")"
EXTP="$(cd "$EXTP" && pwd -P)"
PLAT="$EXTP/platform"
CHILD="$EXTP/child"
mkdir -p "$PLAT/.idev/pack" "$CHILD/.idev"
git -C "$PLAT" init -q
git -C "$CHILD" init -q
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: plat' 'evolve: false' > "$PLAT/.idev/marker.yaml"
printf '%s\n' 'schema_version: 1' 'stages:' '  code:' '    - pack/note.md' '  test:' \
  '    - {path: pack/es.md, products: [elasticsearch]}' > "$PLAT/.idev/extensions.yaml"
printf '%s\n' 'note' > "$PLAT/.idev/pack/note.md"
printf '%s\n' 'es' > "$PLAT/.idev/pack/es.md"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: kafka' 'evolve: false' 'extension_root: ../platform' > "$CHILD/.idev/marker.yaml"
python3 "$SX" code --repo "$CHILD" >"${SCRATCH}"/idev-extroot-code.out \
  || { rm -rf "$EXTP"; cat "${SCRATCH}"/idev-extroot-code.out; fail "child should resolve extension_root pages"; }
grep -q "^OPEN $PLAT/.idev/pack/note.md" "${SCRATCH}"/idev-extroot-code.out \
  || { rm -rf "$EXTP"; cat "${SCRATCH}"/idev-extroot-code.out; fail "child code stage should open the platform page"; }
python3 "$SX" test --repo "$CHILD" >"${SCRATCH}"/idev-extroot-test.out \
  || { rm -rf "$EXTP"; cat "${SCRATCH}"/idev-extroot-test.out; fail "child test stage should pass"; }
if grep -q 'es.md' "${SCRATCH}"/idev-extroot-test.out; then
  rm -rf "$EXTP"
  fail "product-scoped page must not open for another product id"
fi
python3 "$SX" test --repo "$CHILD" --product elasticsearch >"${SCRATCH}"/idev-extroot-es.out \
  || { rm -rf "$EXTP"; cat "${SCRATCH}"/idev-extroot-es.out; fail "child test stage with --product should pass"; }
grep -q "^OPEN $PLAT/.idev/pack/es.md" "${SCRATCH}"/idev-extroot-es.out \
  || { rm -rf "$EXTP"; cat "${SCRATCH}"/idev-extroot-es.out; fail "--product elasticsearch should open es.md"; }
python3 "${KERNEL}/scripts/session-context.py" --repo "$CHILD" --scenario S8 --stage test \
  >"${SCRATCH}"/idev-ctx-marker.out || { rm -rf "$EXTP"; cat "${SCRATCH}"/idev-ctx-marker.out; fail "session-context should pass for marker id"; }
if grep -q 'es.md' "${SCRATCH}"/idev-ctx-marker.out; then
  rm -rf "$EXTP"
  fail "session-context without --product must not open another product page"
fi
python3 "${KERNEL}/scripts/session-context.py" --repo "$CHILD" --scenario S8 --stage test --product elasticsearch \
  >"${SCRATCH}"/idev-ctx-named.out || { rm -rf "$EXTP"; cat "${SCRATCH}"/idev-ctx-named.out; fail "session-context --product should pass"; }
grep -q "^OPEN $PLAT/.idev/pack/es.md" "${SCRATCH}"/idev-ctx-named.out \
  || { rm -rf "$EXTP"; cat "${SCRATCH}"/idev-ctx-named.out; fail "session-context --product should open es.md"; }
grep -q '^PRODUCT elasticsearch' "${SCRATCH}"/idev-ctx-named.out \
  || { rm -rf "$EXTP"; cat "${SCRATCH}"/idev-ctx-named.out; fail "session-context should record the named product"; }
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: kafka' 'evolve: false' "extension_root: $PLAT" > "$CHILD/.idev/marker.yaml"
if python3 "$SX" code --repo "$CHILD" >/dev/null 2>"${SCRATCH}"/idev-extroot-abs.err; then
  rm -rf "$EXTP"
  fail "absolute extension_root should fail"
fi
grep -q 'extension_root must be a relative path' "${SCRATCH}"/idev-extroot-abs.err \
  || { rm -rf "$EXTP"; cat "${SCRATCH}"/idev-extroot-abs.err; fail "absolute extension_root message"; }

mkdir -p "$PLAT/.idev/checks"
printf '%s\n' '# idev-stages: code' 'exit 1' > "$PLAT/.idev/checks/code-only.sh"
bash "${KERNEL}/scripts/product-checks.sh" --stage req --repo "$PLAT" >"${SCRATCH}"/idev-extroot-req.out \
  || { rm -rf "$EXTP"; cat "${SCRATCH}"/idev-extroot-req.out; fail "code-only check should not run for req"; }
grep -q 'skipped' "${SCRATCH}"/idev-extroot-req.out || { rm -rf "$EXTP"; cat "${SCRATCH}"/idev-extroot-req.out; fail "req stage should report skipped"; }
if bash "${KERNEL}/scripts/product-checks.sh" --stage code --repo "$PLAT" >/dev/null 2>&1; then
  rm -rf "$EXTP"
  fail "code-only failing check should fail the code stage"
fi
rm -rf "$EXTP"

AUD="$(mktemp -d "${TMPDIR:-/tmp}/idev-audext.XXXXXX")"
mkdir -p "$AUD/miss" "$AUD/hit"
printf '%s\n' 'scenario: S2' 'feature: demo' 'opened:' '  - deliver/SKILL.md' \
  'extensions:' '  - /repo/.idev/pack/note.md' 'calls:' '  - name: deliver/code' > "$AUD/miss/t1.yaml"
printf '%s\n' 'scenario: S2' 'feature: demo' 'opened:' '  - deliver/SKILL.md' > "$AUD/miss/t2.yaml"
python3 "${KERNEL}/scripts/audit_traces_lib.py" "$AUD/miss" 5 >"${SCRATCH}"/idev-audext-miss.out \
  || { rm -rf "$AUD"; fail "audit_traces_lib should run on the miss dir"; }
grep -q 'extensions-not-opened' "${SCRATCH}"/idev-audext-miss.out \
  || { rm -rf "$AUD"; cat "${SCRATCH}"/idev-audext-miss.out; fail "unopened extension page should be flagged"; }
HC="$(sed -n 's/^HARD_COUNT=//p' "${SCRATCH}"/idev-audext-miss.out)"
[ "${HC:-0}" -ge 1 ] || { rm -rf "$AUD"; cat "${SCRATCH}"/idev-audext-miss.out; fail "unopened extension page should raise HARD_COUNT"; }
printf '%s\n' 'scenario: S2' 'feature: demo' 'opened:' '  - deliver/SKILL.md' '  - /repo/.idev/pack/note.md' \
  'extensions:' '  - /repo/.idev/pack/note.md' 'calls:' '  - name: deliver/code' > "$AUD/hit/t1.yaml"
printf '%s\n' 'scenario: S2' 'feature: demo' 'opened:' '  - deliver/SKILL.md' 'calls:' '  - name: deliver/code' > "$AUD/hit/t2.yaml"
python3 "${KERNEL}/scripts/audit_traces_lib.py" "$AUD/hit" 5 >"${SCRATCH}"/idev-audext-hit.out \
  || { rm -rf "$AUD"; fail "audit_traces_lib should run on the hit dir"; }
if grep -q 'extensions-not-opened' "${SCRATCH}"/idev-audext-hit.out; then
  rm -rf "$AUD"
  fail "opened extension page must not be flagged"
fi
rm -rf "$AUD"
MARK="$(mktemp -d "${TMPDIR:-/tmp}/idev-audmark.XXXXXX")"
mkdir -p "$MARK/.idev/traces"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: aud' 'evolve: false' > "$MARK/.idev/marker.yaml"
printf '%s\n' 'scenario: S2' 'feature: demo' 'opened:' '  - deliver/SKILL.md' 'calls:' '  - name: deliver/code' > "$MARK/.idev/traces/bare.yaml"
python3 "${KERNEL}/scripts/audit_traces_lib.py" "$MARK/.idev/traces" 5 >"${SCRATCH}"/idev-audmark-miss.out \
  || { rm -rf "$MARK"; fail "audit of marked traces should run"; }
grep -q 'extensions-missing' "${SCRATCH}"/idev-audmark-miss.out \
  || { rm -rf "$MARK"; cat "${SCRATCH}"/idev-audmark-miss.out; fail "marked product trace without extensions should be flagged"; }
printf '%s\n' 'scenario: S2' 'feature: demo' 'opened:' '  - deliver/SKILL.md' 'extensions: []' 'calls:' '  - name: deliver/code' > "$MARK/.idev/traces/bare.yaml"
python3 "${KERNEL}/scripts/audit_traces_lib.py" "$MARK/.idev/traces" 5 >"${SCRATCH}"/idev-audmark-empty.out \
  || { rm -rf "$MARK"; fail "audit of empty extensions should run"; }
if grep -q 'extensions-missing' "${SCRATCH}"/idev-audmark-empty.out; then
  rm -rf "$MARK"
  fail "extensions: [] must satisfy the marked-trace field"
fi
rm -rf "$MARK"

S8R="$(mktemp -d "${TMPDIR:-/tmp}/idev-s8wf.XXXXXX")"
git -C "$S8R" init -q
S8R="$(cd "$S8R" && pwd -P)"
mkdir -p "$S8R/.idev/workflows"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: s8probe' 'evolve: false' > "$S8R/.idev/marker.yaml"
printf '%s\n' 'schema_version: 1' 'id: no-ticket' 'needs_ticket: false' 'summary: probe' 'steps:' \
  '  - id: run' '    kind: shell.confirmed' '    with:' '      cmd: "true"' > "$S8R/.idev/workflows/no-ticket.yaml"
printf '%s\n' 'schema_version: 1' 'id: wants-ticket' 'summary: probe' 'steps:' \
  '  - id: run' '    kind: shell.confirmed' '    with:' '      cmd: "true"' > "$S8R/.idev/workflows/wants-ticket.yaml"
(cd "$S8R" && IDEV_REPO="$S8R" bash "${KERNEL}/scripts/s8-preflight.sh" some-feature no-ticket) \
  >"${SCRATCH}"/idev-s8wf-ok.out || { rm -rf "$S8R"; cat "${SCRATCH}"/idev-s8wf-ok.out; fail "needs_ticket: false recipe should pass without docs/task"; }
grep -q 'RESULT OK' "${SCRATCH}"/idev-s8wf-ok.out || { rm -rf "$S8R"; cat "${SCRATCH}"/idev-s8wf-ok.out; fail "no-ticket preflight should report RESULT OK"; }
grep -q "OK  recipe $S8R/.idev/workflows/no-ticket.yaml" "${SCRATCH}"/idev-s8wf-ok.out \
  || { rm -rf "$S8R"; cat "${SCRATCH}"/idev-s8wf-ok.out; fail "preflight should pick the product .idev/workflows recipe"; }
if (cd "$S8R" && IDEV_REPO="$S8R" bash "${KERNEL}/scripts/s8-preflight.sh" some-feature wants-ticket) \
  >"${SCRATCH}"/idev-s8wf-block.out; then
  rm -rf "$S8R"
  fail "recipe without needs_ticket: false should block without deliver.yaml"
fi
grep -q 'BLOCKED missing .*deliver.yaml' "${SCRATCH}"/idev-s8wf-block.out \
  || { rm -rf "$S8R"; cat "${SCRATCH}"/idev-s8wf-block.out; fail "blocked preflight should name deliver.yaml"; }
mkdir -p "$S8R/.idev/task/some-feature" "$S8R/.idev/pack"
printf '%s\n' 'stage: code' > "$S8R/.idev/task/some-feature/deliver.yaml"
printf '%s\n' 'schema_version: 1' 'stages:' '  code:' '    - pack/note.md' > "$S8R/.idev/extensions.yaml"
printf '%s\n' note > "$S8R/.idev/pack/note.md"
(cd "$S8R" && IDEV_REPO="$S8R" bash "${KERNEL}/scripts/s8-preflight.sh" some-feature no-ticket) \
  >"${SCRATCH}"/idev-s8wf-stage.out || { rm -rf "$S8R"; cat "${SCRATCH}"/idev-s8wf-stage.out; fail "preflight should list the deliver stage page"; }
grep -q "^OPEN $S8R/.idev/pack/note.md" "${SCRATCH}"/idev-s8wf-stage.out \
  || { rm -rf "$S8R"; cat "${SCRATCH}"/idev-s8wf-stage.out; fail "S8 preflight should open the code-stage page"; }
rm -rf "$S8R"

DEF="$(mktemp -d "${TMPDIR:-/tmp}/idev-def.XXXXXX")"
git -C "$DEF" init -q
mkdir -p "$DEF/plat/.idev/workflows" "$DEF/child/.idev"
git -C "$DEF/plat" init -q
git -C "$DEF/child" init -q
DEF="$(cd "$DEF" && pwd -P)"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: platform' 'evolve: false' > "$DEF/plat/.idev/marker.yaml"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: kafka' 'evolve: false' 'extension_root: ../plat' > "$DEF/child/.idev/marker.yaml"
cat > "$DEF/plat/.idev/workflows/needs-defaults.yaml" <<'YAML'
schema_version: 1
id: needs-defaults
needs_ticket: false
summary: probe
params:
  - name: coding_root
    required: false
    from: product
    product_key: coding_root
steps:
  - id: start
    kind: localdev.start
YAML
if (cd "$DEF/child" && IDEV_REPO="$DEF/child" bash "${KERNEL}/scripts/s8-preflight.sh" probe needs-defaults) \
  >"${SCRATCH}"/idev-def-miss.out; then
  rm -rf "$DEF"
  fail "missing workflow-defaults on the extension root should block"
fi
grep -q 'BLOCKED workflow-defaults' "${SCRATCH}"/idev-def-miss.out \
  || { rm -rf "$DEF"; cat "${SCRATCH}"/idev-def-miss.out; fail "preflight should name the missing workflow-defaults file"; }
cat > "$DEF/plat/.idev/workflow-defaults.yaml" <<'YAML'
coding_root: "~/src"
commands:
  start: "./start.sh start {target}"
YAML
(cd "$DEF/child" && IDEV_REPO="$DEF/child" bash "${KERNEL}/scripts/s8-preflight.sh" probe needs-defaults) \
  >"${SCRATCH}"/idev-def-ok.out || { rm -rf "$DEF"; cat "${SCRATCH}"/idev-def-ok.out; fail "extension-root workflow-defaults should satisfy preflight"; }
grep -q "OK  defaults $DEF/plat/.idev/workflow-defaults.yaml" "${SCRATCH}"/idev-def-ok.out \
  || { rm -rf "$DEF"; cat "${SCRATCH}"/idev-def-ok.out; fail "preflight should print the extension-root defaults path"; }
grep -q 'doc_home.py' "${KERNEL}/deliver/SKILL.md" \
  || { rm -rf "$DEF"; fail "deliver must resolve ticket paths with doc_home.py"; }
rm -rf "$DEF"
echo "OK  stage extensions"

echo "=== lock: execution clean keeps tickets and the product line ==="
CLEAN="$(mktemp -d "${TMPDIR:-/tmp}/idev-clean.XXXXXX")"
git -C "$CLEAN" init -q
CLEAN="$(cd "$CLEAN" && pwd -P)"
mkdir -p "$CLEAN/.idev/traces" "$CLEAN/.idev/reviews" "$CLEAN/.idev/inbox" \
  "$CLEAN/.idev/proposals" "$CLEAN/.idev/pack" "$CLEAN/docs/task/demo"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: acme' 'evolve: false' > "$CLEAN/.idev/marker.yaml"
printf '%s\n' old > "$CLEAN/.idev/traces/old.yaml"
printf '%s\n' new > "$CLEAN/.idev/traces/new.yaml"
touch -t 202001010000 "$CLEAN/.idev/traces/old.yaml"
printf '%s\n' latest > "$CLEAN/.idev/reviews/evolve-review-latest.md"
printf '%s\n' old > "$CLEAN/.idev/reviews/old.md"
touch -t 202001010000 "$CLEAN/.idev/reviews/old.md"
printf '%s\n' 'status: consumed' > "$CLEAN/.idev/inbox/done.yaml"
touch -t 202001010000 "$CLEAN/.idev/inbox/done.yaml"
printf '%s\n' 'status: pending' > "$CLEAN/.idev/inbox/open.yaml"
touch -t 202001010000 "$CLEAN/.idev/inbox/open.yaml"
printf '%s\n' 'status: archived' > "$CLEAN/.idev/proposals/old.md"
touch -t 202001010000 "$CLEAN/.idev/proposals/old.md"
printf '%s\n' ticket > "$CLEAN/docs/task/demo/deliver.yaml"
printf '%s\n' pack > "$CLEAN/.idev/pack/README.md"
python3 "${KERNEL}/scripts/execution-clean.py" --repo "$CLEAN" --days 30 --keep 1 \
  >"${SCRATCH}"/idev-clean-dry.out || { rm -rf "$CLEAN"; fail "execution-clean dry-run failed"; }
grep -q 'DRY traces/old.yaml' "${SCRATCH}"/idev-clean-dry.out || { rm -rf "$CLEAN"; fail "dry-run should list old trace"; }
grep -q 'DRY inbox/done.yaml' "${SCRATCH}"/idev-clean-dry.out || { rm -rf "$CLEAN"; fail "dry-run should list consumed inbox"; }
if grep -q 'proposals/' "${SCRATCH}"/idev-clean-dry.out; then
  rm -rf "$CLEAN"
  fail "execution-clean must not list proposals"
fi
[ -f "$CLEAN/.idev/traces/old.yaml" ] || { rm -rf "$CLEAN"; fail "dry-run deleted a trace"; }
python3 "${KERNEL}/scripts/execution-clean.py" --repo "$CLEAN" --days 30 --keep 1 --apply \
  >"${SCRATCH}"/idev-clean-apply.out || { rm -rf "$CLEAN"; fail "execution-clean --apply failed"; }
[ ! -f "$CLEAN/.idev/traces/old.yaml" ] || { rm -rf "$CLEAN"; fail "old trace should be removed"; }
[ -f "$CLEAN/.idev/traces/new.yaml" ] || { rm -rf "$CLEAN"; fail "newest trace must stay"; }
[ -f "$CLEAN/.idev/reviews/evolve-review-latest.md" ] || { rm -rf "$CLEAN"; fail "latest review must stay"; }
[ ! -f "$CLEAN/.idev/reviews/old.md" ] || { rm -rf "$CLEAN"; fail "old review should be removed"; }
[ ! -f "$CLEAN/.idev/inbox/done.yaml" ] || { rm -rf "$CLEAN"; fail "consumed inbox should be removed"; }
[ -f "$CLEAN/.idev/inbox/open.yaml" ] || { rm -rf "$CLEAN"; fail "pending inbox must stay"; }
[ -f "$CLEAN/.idev/proposals/old.md" ] || { rm -rf "$CLEAN"; fail "proposal must stay"; }
[ -f "$CLEAN/.idev/marker.yaml" ] || { rm -rf "$CLEAN"; fail "marker must stay"; }
[ -f "$CLEAN/.idev/pack/README.md" ] || { rm -rf "$CLEAN"; fail "pack must stay"; }
[ -f "$CLEAN/docs/task/demo/deliver.yaml" ] || { rm -rf "$CLEAN"; fail "docs/task must stay"; }
rm -rf "$CLEAN"
echo "OK  execution clean"

echo "=== lock: compact summarizes before deleting ==="
COMPACT="$(mktemp -d "${TMPDIR:-/tmp}/idev-compact.XXXXXX")"
git -C "$COMPACT" init -q
COMPACT="$(cd "$COMPACT" && pwd -P)"
mkdir -p "$COMPACT/.idev/traces" "$COMPACT/.idev/reviews" "$COMPACT/.idev/proposals" \
  "$COMPACT/.idev/pack" "$COMPACT/docs/task/demo"
printf '%s\n' 'schema_version: 1' 'marker: idev' 'id: acme' 'evolve: false' > "$COMPACT/.idev/marker.yaml"
printf '%s\n' pack > "$COMPACT/.idev/pack/README.md"
printf '%s\n' ticket > "$COMPACT/docs/task/demo/deliver.yaml"
printf '%s\n' 'summary: stale-lesson' > "$COMPACT/.idev/traces/stale.yaml"
printf '%s\n' 'summary: fresh-lesson' > "$COMPACT/.idev/traces/fresh.yaml"
touch -t 202001010000 "$COMPACT/.idev/traces/stale.yaml"
printf '%s\n' 'see traces/stale.yaml' > "$COMPACT/.idev/reviews/a.md"
printf '%s\n' 'see traces/stale.yaml' > "$COMPACT/.idev/reviews/b.md"
python3 "${KERNEL}/scripts/execution-clean.py" --repo "$COMPACT" --compact --hot 1 \
  >"${SCRATCH}"/idev-compact-dry.out || { rm -rf "$COMPACT"; fail "compact dry-run failed"; }
grep -q 'FOLD traces/stale.yaml' "${SCRATCH}"/idev-compact-dry.out || { rm -rf "$COMPACT"; cat "${SCRATCH}"/idev-compact-dry.out; fail "dry-run should fold the cited trace"; }
if grep -q 'FOLD traces/fresh.yaml' "${SCRATCH}"/idev-compact-dry.out; then
  rm -rf "$COMPACT"
  fail "hot trace must stay"
fi
[ -f "$COMPACT/.idev/traces/stale.yaml" ] || { rm -rf "$COMPACT"; fail "dry-run deleted a trace"; }
[ ! -f "$COMPACT/.idev/memory.md" ] || { rm -rf "$COMPACT"; fail "dry-run wrote memory.md"; }
python3 "${KERNEL}/scripts/execution-clean.py" --repo "$COMPACT" --compact --hot 1 --apply \
  >"${SCRATCH}"/idev-compact-cite.out || { rm -rf "$COMPACT"; fail "compact cite apply failed"; }
[ ! -f "$COMPACT/.idev/traces/stale.yaml" ] || { rm -rf "$COMPACT"; fail "cited trace should be removed"; }
[ -f "$COMPACT/.idev/traces/fresh.yaml" ] || { rm -rf "$COMPACT"; fail "hot trace must stay after cite compact"; }
grep -q 'stale-lesson' "$COMPACT/.idev/memory.md" || { rm -rf "$COMPACT"; fail "memory.md should keep the cited lesson"; }
grep -q 'marker: idev-memory' "$COMPACT/.idev/memory.md" || { rm -rf "$COMPACT"; fail "memory.md marker"; }
printf '%s\n' 'summary: aged-lesson' > "$COMPACT/.idev/traces/aged.yaml"
touch -t 202001010000 "$COMPACT/.idev/traces/aged.yaml"
printf '%s\n' 'summary: keep-lesson' > "$COMPACT/.idev/traces/keep.yaml"
printf '%s\n' 'status: archived' 'summary: closed-lesson' > "$COMPACT/.idev/proposals/closed.md"
printf '%s\n' 'status: pending' 'summary: open-lesson' > "$COMPACT/.idev/proposals/open.md"
python3 "${KERNEL}/scripts/execution-clean.py" --repo "$COMPACT" --compact --hot 1 --apply --bump \
  >"${SCRATCH}"/idev-compact-g1.out || { rm -rf "$COMPACT"; fail "bump 1 failed"; }
python3 "${KERNEL}/scripts/execution-clean.py" --repo "$COMPACT" --compact --hot 1 --apply --bump \
  >"${SCRATCH}"/idev-compact-g2.out || { rm -rf "$COMPACT"; fail "bump 2 failed"; }
[ -f "$COMPACT/.idev/traces/aged.yaml" ] || { rm -rf "$COMPACT"; fail "generation 2 must not delete yet"; }
[ -f "$COMPACT/.idev/proposals/closed.md" ] || { rm -rf "$COMPACT"; fail "closed proposal must wait for generation 3"; }
python3 "${KERNEL}/scripts/execution-clean.py" --repo "$COMPACT" --compact --hot 1 --apply --bump \
  >"${SCRATCH}"/idev-compact-g3.out || { rm -rf "$COMPACT"; fail "bump 3 failed"; }
[ ! -f "$COMPACT/.idev/traces/aged.yaml" ] || { rm -rf "$COMPACT"; fail "aged trace should fold at generation 3"; }
[ ! -f "$COMPACT/.idev/proposals/closed.md" ] || { rm -rf "$COMPACT"; fail "closed proposal should fold at generation 3"; }
[ -f "$COMPACT/.idev/proposals/open.md" ] || { rm -rf "$COMPACT"; fail "open proposal must stay"; }
[ -f "$COMPACT/.idev/traces/keep.yaml" ] || { rm -rf "$COMPACT"; fail "newest trace must stay"; }
grep -q 'aged-lesson' "$COMPACT/.idev/memory.md" || { rm -rf "$COMPACT"; fail "memory.md should keep the aged lesson"; }
grep -q 'closed-lesson' "$COMPACT/.idev/memory.md" || { rm -rf "$COMPACT"; fail "memory.md should keep the closed proposal"; }
printf '%s\n' 'summary: once-lesson' > "$COMPACT/.idev/traces/once.yaml"
touch -t 202001010000 "$COMPACT/.idev/traces/once.yaml"
printf '%s\n' 'see traces/once.yaml' > "$COMPACT/.idev/reviews/once.md"
python3 "${KERNEL}/scripts/execution-clean.py" --repo "$COMPACT" --compact --hot 1 --apply \
  >"${SCRATCH}"/idev-compact-once.out || { rm -rf "$COMPACT"; fail "single cite compact failed"; }
grep -q 'compact SKIP' "${SCRATCH}"/idev-compact-once.out || { rm -rf "$COMPACT"; cat "${SCRATCH}"/idev-compact-once.out; fail "one citation must not compact"; }
[ -f "$COMPACT/.idev/traces/once.yaml" ] || { rm -rf "$COMPACT"; fail "one citation must keep the trace"; }
[ -f "$COMPACT/.idev/marker.yaml" ] || { rm -rf "$COMPACT"; fail "marker must stay"; }
[ -f "$COMPACT/.idev/memory.md" ] || { rm -rf "$COMPACT"; fail "memory.md must stay"; }
[ -f "$COMPACT/.idev/pack/README.md" ] || { rm -rf "$COMPACT"; fail "pack must stay"; }
[ -f "$COMPACT/docs/task/demo/deliver.yaml" ] || { rm -rf "$COMPACT"; fail "docs/task must stay"; }
rm -rf "$COMPACT"
echo "OK  compact memory"

echo "=== lock: ui/localdev kinds stay, product recipe pages stay out ==="
for f in \
  "${KERNEL}/scripts/ui-surface-scan.py" \
  "${KERNEL}/scripts/ui-coverage-check.py"
do
  [ -e "$f" ] || fail "missing $f"
done
for page in workflow-ui-lifecycle workflow-ui-playbook workflow-localdev; do
  if [ -e "${KERNEL}/references/${page}.md" ]; then
    fail "product recipe page ${page}.md still sits in the idev kernel"
  fi
done
if rg -n 'ui-automation-build|ui-lifecycle-full|localdev-st(art|op)|multi-agent-coord' \
  "${KERNEL}/SKILL.md" "${KERNEL}/references" \
  "${KERNEL}/conventions" "${KERNEL}/deliver" \
  "${KERNEL}/verify" "${KERNEL}/ops" \
  --glob '!changelog.md'; then
  fail "kernel pages name a product recipe id"
fi
echo "OK  product recipe pages"

echo "=== lock: recipe doc is opened by session-context ==="
RDOC="$(mktemp -d "${TMPDIR:-/tmp}/idev-recipe-doc.XXXXXX")"
RDOC="$(cd "$RDOC" && pwd -P)"
mkdir -p "$RDOC/.idev/workflows" "$RDOC/.idev/pack"
(cd "$RDOC" && git init -q)
printf '%s\n' 'marker: idev' 'id: demo' 'evolve: off' > "$RDOC/.idev/marker.yaml"
printf '%s\n' 'schema_version: 1' 'id: demo-run' 'needs_ticket: false' 'doc: pack/run.md' \
  'steps:' '  - {id: g, kind: human.gate, with: {will_write: []}}' > "$RDOC/.idev/workflows/demo-run.yaml"
printf 'how to run\n' > "$RDOC/.idev/pack/run.md"
python3 "${ROOT}/workflow-check.py" --recipes-dir "${KERNEL}/workflows" \
  --product-recipes "$RDOC/.idev/workflows" >/dev/null || { rm -rf "$RDOC"; fail "recipe with an existing doc should pass workflow-check"; }
python3 "${ROOT}/session-context.py" --repo "$RDOC" --scenario S8 --workflow demo-run >"${SCRATCH}"/idev-recipe-doc.out \
  || { cat "${SCRATCH}"/idev-recipe-doc.out; rm -rf "$RDOC"; fail "session-context should pass with a recipe doc"; }
grep -q "^OPEN $RDOC/.idev/pack/run.md" "${SCRATCH}"/idev-recipe-doc.out \
  || { cat "${SCRATCH}"/idev-recipe-doc.out; rm -rf "$RDOC"; fail "session-context should OPEN the recipe doc"; }
rm "$RDOC/.idev/pack/run.md"
if python3 "${ROOT}/workflow-check.py" --recipes-dir "${KERNEL}/workflows" \
  --product-recipes "$RDOC/.idev/workflows" >/dev/null 2>&1; then
  rm -rf "$RDOC"; fail "missing recipe doc should fail workflow-check"
fi
if python3 "${ROOT}/session-context.py" --repo "$RDOC" --scenario S8 --workflow demo-run >/dev/null 2>&1; then
  rm -rf "$RDOC"; fail "missing recipe doc should fail session-context"
fi
rm -rf "$RDOC"
echo "OK  recipe doc"

echo "=== lock: self-evolution scripts + workflow ==="
for f in \
  "${KERNEL}/references/self-evolution.md" \
  "${KERNEL}/scripts/evolve-review.sh" \
  "${KERNEL}/scripts/evolve-curator.sh" \
  "${KERNEL}/scripts/install-weekly-evolve.sh" \
  "${KERNEL}/workflows/self-evolve-review.yaml"
do
  [ -e "$f" ] || fail "missing $f"
done
[ -x "${KERNEL}/scripts/evolve-review.sh" ] || fail "evolve-review.sh not executable"
[ -x "${KERNEL}/scripts/evolve-curator.sh" ] || fail "evolve-curator.sh not executable"
# dry-run must not fail
bash "${KERNEL}/scripts/evolve-review.sh" --dry-run >"${SCRATCH}"/idev-evolve-dry.out 2>&1 \
  || fail "evolve-review --dry-run failed"
grep -q 'DRY-RUN\|signal=' "${SCRATCH}"/idev-evolve-dry.out || fail "evolve-review dry-run unexpected output"
# with consumed inbox and no HARD, signal must be 0 (reviews soft-only).
# Stale drafts are the third hard signal (self-evolution.md: 避免提案永久草稿),
# so exclude that case — otherwise this fails whenever a real proposal has
# been sitting unreviewed for 14 days, which is the signal working, not a bug.
if grep -q 'HARD_COUNT=0' "${SCRATCH}"/idev-evolve-dry.out \
  && grep -q 'hot_tags=(none)' "${SCRATCH}"/idev-evolve-dry.out \
  && grep -q 'stale_proposals=0' "${SCRATCH}"/idev-evolve-dry.out; then
  grep -q 'signal=0' "${SCRATCH}"/idev-evolve-dry.out || fail "expected signal=0 when HARD=0, no hot tags and no stale drafts"
fi
bash "${KERNEL}/scripts/evolve-curator.sh" --days 30 >"${SCRATCH}"/idev-curator.out 2>&1 \
  || fail "evolve-curator failed"
grep -q 'evolve-curator' "${SCRATCH}"/idev-curator.out || fail "evolve-curator missing header"
# docs must refuse auto-land language
if ! rg -q '不自动 land|绝不.*改 SKILL|未确认改 Skill' \
  "${KERNEL}/references/self-evolution.md"; then
  fail "self-evolution.md missing no-auto-land guard"
fi
if ! rg -q 'self-evolve-review' \
  "${KERNEL}/references/invoke.md" \
  "${KERNEL}/references/operator-cheatsheet.md"; then
  fail "invoke/cheatsheet missing self-evolve-review pointer"
fi
echo "OK  self-evolution lock"

echo "=== negative: promote refuses FAIL / empty PASS ==="
PROMOTE_FIX=$(mktemp -d)
mkdir -p "$PROMOTE_FIX/docs/task/promo/verify" "$PROMOTE_FIX/docs/test-case"
cat > "$PROMOTE_FIX/docs/task/promo/verify/plan.yaml" <<'YAML'
schema_version: 1
feature: promo
mode: selftest
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
if (cd "$PROMOTE_FIX" && bash "${ROOT}/../verify/scripts/promote.sh" promo); then
  fail "expected promote refuse on FAIL cases"
fi
cat > "$PROMOTE_FIX/docs/task/promo/verify/plan.yaml" <<'YAML'
schema_version: 1
feature: promo
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
    status: PASS
    evidence: "ran @ fixture"
YAML
(cd "$PROMOTE_FIX" && bash "${ROOT}/../verify/scripts/promote.sh" promo)
test -f "$PROMOTE_FIX/docs/test-case/promo-patrol.yaml"
grep -q 'promote receipt' "$PROMOTE_FIX/docs/test-case/promo-patrol.yaml"
rm -rf "$PROMOTE_FIX"
echo "OK  promote refuse FAIL + receipt on PASS"

echo "=== negative: aligned/done without human by ==="
ALIGN_FIX=$(mktemp -d)
mkdir -p "$ALIGN_FIX/docs/task/align-demo" "$ALIGN_FIX/docs/spec"
printf 'eval\n' > "$ALIGN_FIX/docs/task/align-demo/deliver-eval.md"
cat > "$ALIGN_FIX/docs/spec/align-demo.md" <<'EOF'
spec
EOF
cat > "$ALIGN_FIX/docs/task/align-demo/grill.md" <<'EOF'
convention: grilling
frontier: empty
shared_understanding: true

❓ **Q1** - **scope**: settled
➡️ keep
EOF
cat > "$ALIGN_FIX/docs/task/align-demo/baseline.yaml" <<'YAML'
schema_version: 2
feature: align-demo
revision: 1
sealed: true
goal: g
non_goal: n
items:
  - id: B1
    must: m
boundaries: []
details: []
review_questions: []
objections: []
YAML
cat > "$ALIGN_FIX/docs/task/align-demo/deliver.yaml" <<'YAML'
schema_version: 2
feature: align-demo
stage: done
risk_tier: P2
aligned: true
by: agent
YAML
if "${CHECK[@]}" --repo "$ALIGN_FIX" --feature align-demo --stage ops >/tmp/idev-align-neg.out 2>&1; then
  fail "expected FAIL when aligned by=agent"
fi
grep -qE 'aligned/done requires human by|agent filled signoff' /tmp/idev-align-neg.out \
  || fail "missing aligned forge fail"
grep -q '^HINT:' /tmp/idev-align-neg.out || fail "missing FAIL HINT"
rm -rf "$ALIGN_FIX"
echo "OK  aligned forge + HINT"

echo "=== late-lifecycle + second-product smoke ==="
bash "${ROOT}/late-lifecycle-smoke.sh" >/dev/null || fail "late-lifecycle-smoke"
bash "${ROOT}/second-product-smoke.sh" >/dev/null || fail "second-product-smoke"
echo "OK  late-lifecycle + second-product smoke"

echo "=== grill.md recognition ==="
GRILL=$(mktemp -d)
mkdir -p "$GRILL/docs/task/grill-demo"
printf 'eval\n' > "$GRILL/docs/task/grill-demo/deliver-eval.md"
cat > "$GRILL/docs/task/grill-demo/baseline.yaml" <<'YAML'
schema_version: 2
feature: grill-demo
revision: 1
sealed: true
goal: g
non_goal: n
items:
  - id: B1
    must: m
review_questions: []
objections: []
YAML
if (cd "$GRILL" && python3 "${ROOT}/check-feature.py" --repo "$GRILL" --feature grill-demo --stage req-review); then
  fail "expected sealed baseline without grill.md to fail"
fi
cat > "$GRILL/docs/task/grill-demo/grill.md" <<'EOF'
convention: grilling
frontier: empty
shared_understanding: true
EOF
if (cd "$GRILL" && python3 "${ROOT}/check-feature.py" --repo "$GRILL" --feature grill-demo --stage req-review); then
  fail "expected keyword-only grill.md to fail"
fi
cat > "$GRILL/docs/task/grill-demo/grill.md" <<'EOF'
convention: grilling
The phrase frontier: empty appears, and shared_understanding: true is quoted.

❓ **Q1** - **x**: y
➡️ z
EOF
if (cd "$GRILL" && python3 "${ROOT}/check-feature.py" --repo "$GRILL" --feature grill-demo --stage req-review); then
  fail "expected prose mentioning frontier to fail"
fi
cat > "$GRILL/docs/task/grill-demo/grill.md" <<'EOF'
convention: grilling
frontier: open
shared_understanding: false

❓ **Q1** - **x**: y
➡️ z
EOF
if (cd "$GRILL" && python3 "${ROOT}/check-feature.py" --repo "$GRILL" --feature grill-demo --stage req-review); then
  fail "expected open grill.md to block a sealed baseline"
fi
mkdir -p "$GRILL/docs/spec"
printf 'restates the sealed baseline\n' > "$GRILL/docs/spec/grill-demo.md"
cat > "$GRILL/docs/task/grill-demo/grill.md" <<'EOF'
convention: grilling
frontier: empty
shared_understanding: true

note ❓ then ➡️
EOF
if (cd "$GRILL" && python3 "${ROOT}/check-feature.py" --repo "$GRILL" --feature grill-demo --stage req-review); then
  fail "expected stray question marks to fail"
fi
cat > "$GRILL/docs/task/grill-demo/grill.md" <<'EOF'
convention: grilling
frontier: empty
shared_understanding: true
frontier: open

❓ **Q1** - **scope**: still asking
➡️ unsure
EOF
if (cd "$GRILL" && python3 "${ROOT}/check-feature.py" --repo "$GRILL" --feature grill-demo --stage req-review); then
  fail "expected a second frontier line to fail"
fi
cat > "$GRILL/docs/task/grill-demo/grill.md" <<'EOF'
convention: grilling
frontier: empty
shared_understanding: true

❓ **Q1** - **x**: y
➡️ z
EOF
(cd "$GRILL" && python3 "${ROOT}/check-feature.py" --repo "$GRILL" --feature grill-demo --stage req-review) \
  || fail "closed grill.md should pass req-review"
python3 - <<PY
from pathlib import Path
p = Path("$GRILL/docs/task/grill-demo/baseline.yaml")
p.write_text(p.read_text().replace("review_questions: []", "review_questions:\n  - id: Q1\n    status: open\n    text: still open"))
PY
if (cd "$GRILL" && python3 "${ROOT}/check-feature.py" --repo "$GRILL" --feature grill-demo --stage req-review); then
  fail "expected open baseline question to fail even when grill.md is closed"
fi
rm -rf "$GRILL"
echo "OK  grill.md"

echo "=== both spec copies collapse onto docs/spec ==="
BOTH=$(mktemp -d)
mkdir -p "$BOTH/docs/task/both-demo" "$BOTH/docs/spec" "$BOTH/docs/specs"
printf 'eval\n' > "$BOTH/docs/task/both-demo/deliver-eval.md"
cat > "$BOTH/docs/task/both-demo/baseline.yaml" <<'YAML'
schema_version: 2
feature: both-demo
revision: 1
sealed: true
goal: g
non_goal: n
items:
  - id: B1
    must: m
review_questions: []
objections: []
YAML
cat > "$BOTH/docs/task/both-demo/grill.md" <<'EOF'
convention: grilling
frontier: empty
shared_understanding: true

❓ **Q1** - **x**: y
➡️ z
EOF
printf 'canonical line\n' > "$BOTH/docs/spec/both-demo.md"
printf 'legacy only line\n' > "$BOTH/docs/specs/both-demo.md"
(cd "$BOTH" && python3 "${ROOT}/check-feature.py" --repo "$BOTH" --feature both-demo --stage req-review) \
  || { rm -rf "$BOTH"; fail "both spec copies should pass after collapse"; }
test ! -e "$BOTH/docs/specs/both-demo.md" || { rm -rf "$BOTH"; fail "legacy spec file should be removed"; }
grep -q 'canonical line' "$BOTH/docs/spec/both-demo.md" \
  || { rm -rf "$BOTH"; fail "conforming spec lost its own text"; }
grep -q 'legacy only line' "$BOTH/docs/spec/both-demo.md" \
  || { rm -rf "$BOTH"; fail "legacy spec text was not folded in"; }
rm -rf "$BOTH"
echo "OK  spec collapse"

echo "=== lock: repo that declares docs/specs keeps the plural directory ==="
PLURAL="$(mktemp -d "${TMPDIR:-/tmp}/idev-plural.XXXXXX")"
PLURAL="$(cd "$PLURAL" && pwd -P)"
mkdir -p "$PLURAL/docs/agents"
printf '%s\n' 'docs/prd/<feature>.md' '规格目录是 docs/specs/，不是技能模板里的 docs/spec/' 'docs/task/<feature>/' \
  'questions follow grilling' > "$PLURAL/docs/agents/issue-tracker.md"
NEW_SPEC="$(python3 "${KERNEL}/scripts/lib/doc_home.py" --repo "$PLURAL" --feature fresh --key spec)"
[ "$NEW_SPEC" = "$PLURAL/docs/specs/fresh.md" ] || { echo "$NEW_SPEC"; rm -rf "$PLURAL"; fail "declared docs/specs should hold new specs"; }
mkdir -p "$PLURAL/docs/spec" "$PLURAL/docs/specs"
printf 'plural line\n' > "$PLURAL/docs/specs/dup.md"
printf 'singular only line\n' > "$PLURAL/docs/spec/dup.md"
python3 - "$PLURAL" "${ROOT}/lib" <<'PY' || { rm -rf "$PLURAL"; fail "reconcile should fold into docs/specs"; }
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from doc_home import reconcile_spec
repo = Path(sys.argv[1])
kept = reconcile_spec(repo, "dup", "product")
assert kept == repo / "docs/specs/dup.md", kept
assert not (repo / "docs/spec/dup.md").exists()
text = kept.read_text()
assert "plural line" in text and "singular only line" in text, text
PY
rm -rf "$PLURAL"
echo "OK  declared spec directory"

echo "=== lock: doc home follows mattpocock and grilling ==="
DOC="$(mktemp -d "${TMPDIR:-/tmp}/idev-doc.XXXXXX")"
DOC="$(cd "$DOC" && pwd -P)"
TASK="$(python3 "${KERNEL}/scripts/lib/doc_home.py" --repo "$DOC" --feature demo --key task)"
case "$TASK" in
  "$DOC/.idev/task/demo") ;;
  *) rm -rf "$DOC"; echo "$TASK"; fail "a repo without mattpocock and grilling docs should use .idev/task" ;;
esac
SPEC="$(python3 "${KERNEL}/scripts/lib/doc_home.py" --repo "$DOC" --feature demo --key spec)"
case "$SPEC" in
  "$DOC/.idev/docs/spec/demo.md") ;;
  *) rm -rf "$DOC"; echo "$SPEC"; fail "idev spec path without product docs" ;;
esac
mkdir -p "$DOC/docs/agents"
printf '%s\n' 'docs/prd/<feature>.md' 'docs/spec/<feature>.md' 'docs/task/<feature>/' \
  > "$DOC/docs/agents/issue-tracker.md"
MATT_ONLY="$(python3 "${KERNEL}/scripts/lib/doc_home.py" --repo "$DOC" --feature matt-only --key task)"
case "$MATT_ONLY" in
  "$DOC/.idev/task/matt-only") ;;
  *) rm -rf "$DOC"; echo "$MATT_ONLY"; fail "mattpocock paths without grilling should stay under .idev" ;;
esac
printf '%s\n' 'questions follow grilling' >> "$DOC/docs/agents/issue-tracker.md"
PLACED="$(python3 "${KERNEL}/scripts/lib/doc_home.py" --repo "$DOC" --feature placed --key task)"
case "$PLACED" in
  "$DOC/docs/task/placed") ;;
  *) rm -rf "$DOC"; echo "$PLACED"; fail "mattpocock and grilling docs should use docs/task" ;;
esac
mkdir -p "$DOC/.idev/task/kept"
printf '%s\n' 'stage: req-review' > "$DOC/.idev/task/kept/deliver.yaml"
KEPT="$(python3 "${KERNEL}/scripts/lib/doc_home.py" --repo "$DOC" --feature kept --key deliver)"
case "$KEPT" in
  "$DOC/.idev/task/kept/deliver.yaml") ;;
  *) rm -rf "$DOC"; echo "$KEPT"; fail "an existing .idev ticket stays there" ;;
esac
mkdir -p "$DOC/docs/task/both" "$DOC/docs/spec" "$DOC/.idev/task/both" "$DOC/.idev/docs/spec"
printf '%s\n' 'stage: from-docs' > "$DOC/docs/task/both/deliver.yaml"
printf '%s\n' 'stage: from-idev' > "$DOC/.idev/task/both/deliver.yaml"
printf '%s\n' 'normative spec' > "$DOC/docs/spec/both.md"
printf '%s\n' 'idev copy' > "$DOC/.idev/docs/spec/both.md"
BOTH_DELIVER="$(python3 "${KERNEL}/scripts/lib/doc_home.py" --repo "$DOC" --feature both --key deliver)"
BOTH_SPEC="$(python3 "${KERNEL}/scripts/lib/doc_home.py" --repo "$DOC" --feature both --key spec)"
case "$BOTH_DELIVER" in
  "$DOC/docs/task/both/deliver.yaml") ;;
  *) rm -rf "$DOC"; echo "$BOTH_DELIVER"; fail "normative deliver.yaml should win" ;;
esac
case "$BOTH_SPEC" in
  "$DOC/docs/spec/both.md") ;;
  *) rm -rf "$DOC"; echo "$BOTH_SPEC"; fail "normative spec should win" ;;
esac
test -f "$DOC/.idev/task/both/deliver.yaml" || { rm -rf "$DOC"; fail "lower-priority copy should stay on disk"; }
mkdir -p "$DOC/.idev/task/native-demo"
printf '%s\n' eval > "$DOC/.idev/task/native-demo/deliver-eval.md"
cat > "$DOC/.idev/task/native-demo/baseline.yaml" <<'YAML'
schema_version: 2
feature: native-demo
revision: 1
sealed: true
goal: g
non_goal: n
items:
  - id: B1
    must: m
review_questions: []
objections: []
YAML
cat > "$DOC/.idev/task/native-demo/grill.md" <<'EOF'
convention: grilling
frontier: empty
shared_understanding: true

❓ **Q1** - **x**: y
➡️ z
EOF
# drop the product-doc marker so this feature is not pulled back to docs/task
rm -rf "$DOC/docs"
mkdir -p "$DOC/.idev/docs/spec"
printf '%s\n' 'restates the sealed baseline' > "$DOC/.idev/docs/spec/native-demo.md"
python3 "${KERNEL}/scripts/check-feature.py" --repo "$DOC" --feature native-demo --stage req-review \
  >"${SCRATCH}"/idev-doc-native.out || { rm -rf "$DOC"; cat "${SCRATCH}"/idev-doc-native.out; fail "native .idev ticket should pass req-review"; }
echo "=== lock: docs skill is the delivery entry ==="
DOC_SKILL="${KERNEL}/docs/SKILL.md"
test -f "$DOC_SKILL" || fail "missing docs/SKILL.md"
grep -q 'setup-agents-docs/SKILL.md' "$DOC_SKILL" || fail "docs skill must open setup-agents-docs"
grep -q 'grilling/SKILL.md' "$DOC_SKILL" || fail "docs skill must open grilling"
grep -q 'doc_home.py' "$DOC_SKILL" || fail "docs skill must resolve paths with doc_home"
for m in conventions deliver verify ops docs; do
  head -4 "${KERNEL}/${m}/SKILL.md" | grep -q '^parent: idev$' \
    || fail "${m}/SKILL.md must be an idev module (parent: idev)"
  if head -6 "${KERNEL}/${m}/SKILL.md" | grep -q '^name:'; then
    fail "${m}/SKILL.md must not declare a top-level skill name"
  fi
done
grep -q 'docs/SKILL.md' "${KERNEL}/SKILL.md" || fail "idev entry must open the docs skill"
grep -q 'setup-agents-docs' "${KERNEL}/scripts/link-companion-skills.sh" \
  || fail "companion linker must include setup-agents-docs"
grep -q 'docs/SKILL.md' "${KERNEL}/conventions/docs.md" \
  || fail "conventions/docs.md must point at the docs skill"
if grep -q '本页是 idev 的文件规范' "${KERNEL}/conventions/docs.md"; then
  fail "conventions/docs.md must not invent a second file convention"
fi
bash "${KERNEL}/scripts/link-companion-skills.sh" setup-agents-docs \
  >"${SCRATCH}"/idev-docs-link.out || { cat "${SCRATCH}"/idev-docs-link.out; fail "setup-agents-docs companion link"; }
grep -q 'link-companion-skills PASS' "${SCRATCH}"/idev-docs-link.out || fail "docs companion link did not pass"
rm -rf "$DOC"
echo "OK  doc home"

echo "=== lock: healthcheck counts smoke WARN and does not nest path-view ==="
IDEV_ROOT="${KERNEL}" python3 - <<'PY'
import os
from pathlib import Path
root = Path(os.environ["IDEV_ROOT"])
text = (root / "scripts/healthcheck.sh").read_text()
start = text.find("OK  lite-change smoke")
end = text.find("FAIL lite-change smoke", start)
window = text[start:end]
if "grep -q '^WARN '" not in window or "warn=$((warn + 1))" not in window:
    raise SystemExit("lite-change WARN is printed but does not increment warn")
lines = text.splitlines()
stack = []
seen = False
for line in lines:
    s = line.strip()
    if s.startswith("if "):
        stack.append(s)
    elif s == "fi" and stack:
        stack.pop()
    if "path-view.sh" in line:
        seen = True
        if any("evolve-review.sh" in c for c in stack):
            raise SystemExit("path-view check is still nested under self-evolution")
if not seen:
    raise SystemExit("path-view check missing")
coding = (root / "conventions/coding.md").read_text()
for token in ("tpaas", "账本", "PIN / SSO"):
    if token in coding:
        raise SystemExit("coding.md still has product shortcut: " + token)
print("OK  healthcheck structure")
PY

echo "=== lock: scripts with a shebang are executable ==="
for s in "${KERNEL}/scripts/"*.sh "${KERNEL}/scripts/"*.py; do
  head -1 "$s" | grep -q '^#!' || continue
  [ -x "$s" ] || fail "script has a shebang but is not executable: ${s##*/idev/}"
done
echo "OK  script exec bits"

echo "=== lock: published tree keeps no run residue or real home paths ==="
# Proposal 20261027 §6. Traces, reviews, promptfoo, proposals, lessons and the
# verify target stay on disk for audits; they must not be in the published tree.
# /Users/alice, /Users/x and /Users/USER in design/ and testdata are placeholders.
IDEV_ROOT_LOCK="${KERNEL}"
residue="$(git -C "${IDEV_ROOT_LOCK}" ls-files -- \
  'verify/target/' 'state/traces/' 'state/reviews/' 'state/promptfoo/' \
  'state/proposals/' 'state/lessons/' 'state/lessons.yaml' 'state/ledger.yaml' \
  'state/outbound-config.json' 2>/dev/null || true)"
if [ -n "${residue}" ]; then
  fail "tracked run residue (untrack; keep on disk): $(printf '%s' "${residue}" | head -3 | tr '\n' ' ')"
fi
homes="$(git -C "${IDEV_ROOT_LOCK}" grep -nEH '/Users/[A-Za-z0-9._-]+' -- \
  ':!state/' ':!design/' ':!api/schemas/testdata/' 2>/dev/null \
  | grep -Ev '/Users/(alice|x|USER)(/|:|[[:space:]]|$)' || true)"
if [ -n "${homes}" ]; then
  fail "tracked file names a real home directory: $(printf '%s' "${homes}" | head -1)"
fi
echo "OK  published tree has no run residue"

echo "=== lock: kernel pages do not invent doc dirs or module ledgers ==="
if rg -q 'docs/debt' "${KERNEL}/conventions/evidence.md"; then
  fail "evidence.md must not name docs/debt; setup-agents-docs Rule 10 has no such directory"
fi
if rg -q 'verify/state/ledger\.yaml|模块实验台账' "${KERNEL}/verify/references/evolve.md"; then
  fail "evolve.md must not imply module-level ledgers"
fi
echo "OK  doc dirs and ledgers"

echo "=== lock: unbound tickets count only outside the kernel ==="
[ ! -e "${KERNEL}/scripts/pin-summary-check.sh" ] || fail "pin-summary-check.sh must stay deleted"
UB="$(mktemp -d)"
mkdir -p "$UB/.idev/traces"
printf 'scenario: S8\nfeature: "-"\ncalls:\n  - name: deliver/SKILL.md\n' > "$UB/.idev/traces/t.yaml"
python3 "${KERNEL}/scripts/audit_traces_lib.py" "$UB/.idev/traces" 5 | grep -q '^| `feature: -` 未绑票 | 1 ' \
  || { rm -rf "$UB"; fail "product trace with feature - must count as unbound"; }
rm -rf "$UB"
python3 "${KERNEL}/scripts/audit_traces_lib.py" "${KERNEL}/state/traces" 50 | grep -q '^| `feature: -` 未绑票 | 0 ' \
  || fail "kernel conductor traces must not count as unbound"
echo "OK  unbound scope"

echo "=== lock: workflow syntax, checker and driver agree ==="
python3 - "${KERNEL}" <<'PY' || fail "workflow-schema.md kind table differs from workflow_spec.KINDS"
import re, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "scripts/lib"))
from workflow_spec import KINDS, FORBIDDEN
text = (root / "references/workflow-schema.md").read_text(encoding="utf-8")
table = text.split("## kind 登记表", 1)[1].split("\n## ", 1)[0]
doc = set(re.findall(r"(?m)^\| `([a-z]+\.[a-z_0-9]+)` \|", table))
forbid = set(re.findall(r"`([a-z_]+(?:\.[a-z_]+)+)`", table.split("禁止 kind", 1)[1].split("\n", 1)[0]))
if doc != set(KINDS) or forbid != FORBIDDEN:
    raise SystemExit("doc-only=%s code-only=%s forbidden=%s" % (sorted(doc - set(KINDS)), sorted(set(KINDS) - doc), sorted(forbid ^ FORBIDDEN)))
PY
WFT="$(mktemp -d)"
printf '%s\n' 'schema_version: 1' 'id: bad' 'summary: x' 'surprise: 1' 'steps:' '  - {id: a, kind: human.gate, with: {will_write: []}}' > "$WFT/bad.yaml"
python3 "${KERNEL}/scripts/workflow-check.py" "$WFT/bad.yaml" >/dev/null 2>&1 \
  && { rm -rf "$WFT"; fail "workflow-check must reject an unknown top-level field"; }
printf '%s\n' 'schema_version: 1' 'id: nogate' 'summary: x' 'steps:' '  - {id: a, kind: human.gate, label: 人确认}' > "$WFT/nogate.yaml"
gate_out="$(python3 "${KERNEL}/scripts/workflow-check.py" "$WFT/nogate.yaml" 2>&1 || true)"
[[ "$gate_out" == *"needs with.will_write"* ]] \
  || { rm -rf "$WFT"; fail "workflow-check must reject a human.gate without will_write or 将代写"; }
(
  export IDEV_ENGINE=python
  export IDEV_AGENT_FEEDBACK=off
  export IDEV_BIN=off
  export PATH="/usr/bin:/bin:/usr/sbin:/sbin"
  cd "$WFT" && git init -q && mkdir -p .idev/task/demo .idev/workflows
  printf 'people:\n  - tester\n' > .idev/people.yaml
  printf 'schema_version: 1\nmarker: idev\nid: demo\nevolve: false\n' > .idev/marker.yaml
  printf 'stage: code\n' > .idev/task/demo/deliver.yaml
  printf '%s\n' 'schema_version: 1' 'id: demo-flow' 'summary: x' 'params:' '  - {name: feature, required: true, from: user}' \
    'steps:' '  - {id: a, kind: deliver.code_pass}' '  - {id: g, kind: human.gate, label: "将代写: x"}' '  - {id: r, kind: verify.run}' \
    > .idev/workflows/demo-flow.yaml
  W="${KERNEL}/scripts/workflow.py"
  "$W" start demo-flow >/dev/null 2>&1 && exit 11
  "$W" start demo-flow --feature demo | grep -q '^NEXT a ' || exit 12
  "$W" record g PASS --feature demo >/dev/null 2>&1 && exit 13
  "$W" record a PASS --feature demo --evidence r.md >/dev/null 2>&1 && exit 14
  "$W" record a PASS --feature demo --evidence r.md --verified-by idev-reviewer --verify-evidence r.md >/dev/null 2>&1 && exit 141
  : > r.md
  "$W" record a PASS --feature demo --evidence r.md --verified-by idev-reviewer --verify-evidence r.md >/dev/null 2>&1 && exit 142
  printf 'reviewed\n' > r.md
  DEL="$(python3 "${KERNEL}/scripts/delegation.py" dir --feature demo)" || exit 140
  mkdir -p "$DEL"
  printf '%s\n' 'step: a' 'attempt: 1' 'kind: deliver.code_pass' 'agent: idev-coder' 'report:' \
    '  raw: "STATUS: PASS\nEVIDENCE: r.md\nFACTS: codegraph src/app.py:main and git diff\nDOC_DRIFT: none\nASSUMED: none\nSCOPE: src/app.py:main\nCHANGE_KIND: local\nCANON_TRIGGER: none\nTABLE_HIT: none\n"' \
    > "$DEL/a-1.yaml"
  "$W" record a PASS --feature demo --evidence r.md --verified-by idev-reviewer --verify-evidence r.md >/dev/null 2>&1 && exit 143
  printf '%s\n' 'step: review' 'attempt: 1' 'kind: review.report' 'agent: idev-reviewer' 'report:' \
    '  raw: "STATUS: PASS\nEVIDENCE: r.md\n"' > "$DEL/review-1.yaml"
  "$W" record a PASS --feature demo --evidence r.md --verified-by idev-reviewer --verify-evidence r.md >/dev/null || exit 144
  "$W" record g PASS --feature demo --by tester --quote 继续 >/dev/null 2>&1 && exit 15
  "$W" record g PASS --feature demo --by assistant --quote 确认 >/dev/null 2>&1 && exit 16
  "$W" record g PASS --feature demo --by tester --quote 确认 | grep -q '^NEXT r ' || exit 17
  "$W" record r FAIL --feature demo >/dev/null || exit 18
  "$W" start demo-flow --feature demo >/dev/null 2>&1 && exit 19
  "$W" record r PASS --feature demo | grep -q '^RUN DONE' || exit 20
  python3 "${KERNEL}/scripts/workflow-check.py" --run .idev/task/demo/workflow/run.yaml >/dev/null || exit 21
  grep -q 'FAIL -> PASS' .idev/task/demo/workflow/report.md || exit 22
) || { code=$?; rm -rf "$WFT"; fail "workflow.py driver rule broke (case $code)"; }
rm -rf "$WFT"
WFU="$(mktemp -d)"
(
  cd "$WFU" && git init -q && mkdir -p .idev/task/demo .idev/workflows
  printf 'schema_version: 1\nmarker: idev\nid: demo\nevolve: false\n' > .idev/marker.yaml
  printf 'stage: code\nrisk_tier: P2\n' > .idev/task/demo/deliver.yaml
  printf '%s\n' 'schema_version: 1' 'id: demo-auto' 'summary: x' 'params:' '  - {name: feature, required: true, from: user}' \
    'steps:' '  - {id: g, kind: human.gate, label: "将代写: x", with: {auto_tiers: [P1, P2]}}' '  - {id: r, kind: verify.run}' \
    > .idev/workflows/demo-auto.yaml
  W="${KERNEL}/scripts/workflow.py"
  out="$("$W" start demo-auto --feature demo 2>&1)" && exit 31
  printf '%s\n' "$out" | grep -q 'auto_tiers needs a gate a machine check can pass' || exit 32
) || { code=$?; rm -rf "$WFU"; fail "workflow.py AUTO gate broke (case $code)"; }
rm -rf "$WFU"
python3 "${KERNEL}/scripts/test_auto_gate.py" >/dev/null 2>&1 \
  || fail "record AUTO passed a gate on something other than the check it ran (python3 scripts/test_auto_gate.py)"
python3 "${KERNEL}/scripts/test_hooks.py" >/dev/null 2>&1 \
  || fail "client hooks install or the four oversteps broke (python3 scripts/test_hooks.py)"
# Fixture: missing log → 100%. Live ~/.idev is not consulted (may predate §4).
IDEV_DATA="$(mktemp -d "${TMPDIR:-/tmp}/idev-timing.XXXXXX")" \
  python3 "${KERNEL}/hooks/timing_coverage.py" >/dev/null 2>&1 \
  || fail "subagent-stops timing coverage lock broke (hooks/timing_coverage.py)"
python3 "${KERNEL}/scripts/test_delegation_return.py" >/dev/null 2>&1 \
  || fail "structured delegation-return schema check broke (python3 scripts/test_delegation_return.py)"
python3 "${KERNEL}/scripts/test_outcome_metrics.py" >/dev/null 2>&1 \
  || fail "outcome-metrics WIP/rework counts broke (python3 scripts/test_outcome_metrics.py)"
python3 "${KERNEL}/scripts/test_phase2.py" >/dev/null 2>&1 \
  || fail "phase 2 retain/eval/usage/budget broke (python3 scripts/test_phase2.py)"
WFA="$(mktemp -d)"
(
  cd "$WFA" && mkdir -p ext/.idev/workflows sess/.idev p/.idev/workflows
  for d in ext sess p; do (cd "$d" && git init -q); done
  printf 'schema_version: 1\nmarker: idev\nid: ext\nevolve: false\n' > ext/.idev/marker.yaml
  printf 'schema_version: 1\nmarker: idev\nid: sess\nevolve: false\nextension_root: ../ext\n' > sess/.idev/marker.yaml
  printf 'schema_version: 1\nmarker: idev\nid: p\nevolve: false\n' > p/.idev/marker.yaml
  printf '%s\n' 'schema_version: 1' 'id: broken' 'summary: x' 'steps:' '  - {id: a, kind: no.such.kind}' > ext/.idev/workflows/broken.yaml
  (cd sess && bash "${KERNEL}/scripts/workflow-check.sh" >/dev/null 2>&1) && exit 31
  for id in one two; do
    printf '%s\n' 'schema_version: 1' "id: $id" 'aliases: ["起服务"]' 'summary: x' 'steps:' '  - {id: a, kind: human.gate, with: {will_write: []}}' > "p/.idev/workflows/$id.yaml"
  done
  (cd p && bash "${KERNEL}/scripts/workflow-check.sh" >/dev/null 2>&1) && exit 32
  rm p/.idev/workflows/two.yaml
  cp "${KERNEL}/workflows/path-view.yaml" p/.idev/workflows/
  (cd p && bash "${KERNEL}/scripts/workflow-check.sh" >/dev/null) || exit 33
  mkdir -p p/.idev/task/demo && printf 'stage: code\n' > p/.idev/task/demo/deliver.yaml
  (cd p && "${KERNEL}/scripts/workflow.py" start dev-selftest --feature demo >/dev/null) || exit 34
  R=p/.idev/task/demo/workflow/run.yaml
  python3 -c "import sys,yaml;p=sys.argv[1];d=yaml.safe_load(open(p));d['steps'].pop(1);yaml.safe_dump(d,open(p,'w'),allow_unicode=True)" "$R"
  python3 "${KERNEL}/scripts/workflow-check.py" --run "$R" >/dev/null 2>&1 && exit 35
  exit 0
) || { code=$?; rm -rf "$WFA"; fail "workflow-check alignment broke (case $code)"; }
rm -rf "$WFA"
echo "OK  workflow syntax, checker, driver"

echo "=== lock: the kind table has one source and the copies are current ==="
# registry/kinds.yaml is the source; five copies are generated from it
# (two Python tables, one JSON enum, two prose tables). A stale copy is how
# the old five-way duplication came back, so check it here rather than
# trusting whoever added the kind to have run the generator.
python3 "${KERNEL}/scripts/gen-kinds.py" --check >/dev/null 2>&1 \
  || fail "kind generated files are stale; run python3 scripts/gen-kinds.py"
# The tables the rest of the kernel imports must come from the registry, not
# from a hand-written dict that happens to agree with it today.
for name in KINDS FORBIDDEN LEGACY_KINDS; do
  grep -qE "^${name}(: [^=]+)? = _gen\.${name}" "${KERNEL}/scripts/lib/workflow_spec.py" \
    || fail "workflow_spec.${name} no longer comes from the registry"
done
grep -q "^KIND_AGENTS: dict\[str, str\] = _gen.KIND_AGENTS" "${KERNEL}/scripts/lib/kind_agents.py" \
  || fail "kind_agents.KIND_AGENTS no longer comes from the registry"
grep -q "^KIND_COMMANDS = _gen.KIND_COMMANDS" "${KERNEL}/scripts/lib/workflow_defaults.py" \
  || fail "workflow_defaults.KIND_COMMANDS no longer comes from the registry"
echo "OK  one kind source"

echo "=== lock: signoffs follow the risk tier ==="
bash "${KERNEL}/test/check-feature-tiers.sh" >/dev/null 2>&1 \
  || fail "check-feature tier rules broke (bash test/check-feature-tiers.sh)"
python3 "${KERNEL}/scripts/test_signals.py" >/dev/null 2>&1 \
  || fail "signal / answer rules broke (python3 scripts/test_signals.py)"
python3 "${KERNEL}/scripts/test_staffing.py" >/dev/null 2>&1 \
  || fail "staffing mode or the role check on a gate broke (python3 scripts/test_staffing.py)"
python3 "${KERNEL}/scripts/test_concurrency.py" >/dev/null 2>&1 \
  || fail "concurrent start or decide lost the single-writer rule (python3 scripts/test_concurrency.py)"
python3 "${KERNEL}/scripts/test_record_paths.py" >/dev/null 2>&1 \
  || fail "a guard reads delegation records from somewhere the writer does not put them (python3 scripts/test_record_paths.py)"
python3 "${KERNEL}/scripts/test_record_findings.py" >/dev/null 2>&1 \
  || fail "record PASS ignored the delegation's machine checks, or a verification took an attempt (python3 scripts/test_record_findings.py)"
python3 "${KERNEL}/scripts/test_idev_bin.py" >/dev/null 2>&1 \
  || fail "the idev binary resolver ignored IDEV_BIN or ran a stale build (python3 scripts/test_idev_bin.py)"
python3 "${KERNEL}/scripts/test_report_lines.py" >/dev/null 2>&1 \
  || fail "a report field reader took its value from the next line (python3 scripts/test_report_lines.py)"
python3 "${KERNEL}/scripts/test_telemetry.py" >/dev/null 2>&1 \
  || fail "a record took another delegation's subagentStop row, or lost its duration and tool calls (python3 scripts/test_telemetry.py)"
python3 "${KERNEL}/scripts/test_suggest_review.py" >/dev/null 2>&1 \
  || fail "SUGGEST naming one kernel thing twice no longer raises a review signal (python3 scripts/test_suggest_review.py)"
python3 "${KERNEL}/scripts/test_trace_derive.py" >/dev/null 2>&1 \
  || fail "trace append no longer lists the round's delegations from the records, or the signoff check reads words again (python3 scripts/test_trace_derive.py)"
python3 "${KERNEL}/scripts/test_step_land.py" >/dev/null 2>&1 \
  || fail "workflow.py step / land no longer carry a delegated step from brief to record (python3 scripts/test_step_land.py)"
python3 "${KERNEL}/scripts/test_browser_program.py" >/dev/null 2>&1 \
  || fail "a browser program ran twice, or a click return counted as done (python3 scripts/test_browser_program.py)"
python3 "${KERNEL}/scripts/test_ui_spec.py" >/dev/null 2>&1 \
  || fail "a screen accepted two controls with the same name, or a click return stood in for the pending state (python3 scripts/test_ui_spec.py)"
python3 "${KERNEL}/scripts/test_context_stage.py" >/dev/null 2>&1 \
  || fail "a code preview included a function body, or a failed source erased the other (python3 scripts/test_context_stage.py)"
python3 "${KERNEL}/scripts/test_sediment.py" >/dev/null 2>&1 \
  || fail "one success was kept, or a registered script was executed (python3 scripts/test_sediment.py)"
echo "OK  tier signoffs and single writer"

echo "=== lock: a gate is answered by the person's 确认 ==="
if command -v go >/dev/null 2>&1; then
  bash "${KERNEL}/test/gate-channel.sh" >/dev/null 2>&1 \
    || fail "gate channel broke (bash test/gate-channel.sh)"
  bash "${KERNEL}/test/lease-channel.sh" >/dev/null 2>&1 \
    || fail "lease channel broke (bash test/lease-channel.sh)"
  echo "OK  gate and lease channels"
else
  echo "SKIP gate channel (no go toolchain)"
fi

echo "=== lock: a turn speaks before it stalls ==="
TB="${ROOT}/turn-budget.py"
FIX="${ROOT}/../test/fixtures/turn-budget"
must_fail() {
  local file="$1" needle="$2"
  local out
  if out="$(python3 "$TB" "${FIX}/${file}" 2>&1)"; then
    fail "${file} must fail"
  fi
  printf '%s\n' "$out" | grep -q "$needle" || fail "${file} must print ${needle}"
}
must_fail red.jsonl 'silent_before=9'
must_fail streak.jsonl 'streak=9'
must_fail ping.jsonl 'ping segment=1'
must_fail longblock.jsonl 'long_block=120000'
must_fail suite.jsonl 'suite_block=180000'
must_fail doctor.jsonl 'suite_block=120000'
python3 "$TB" "${FIX}/green.jsonl" >/dev/null || fail "green turn budget must pass"
python3 "$TB" "${FIX}/spoken-block.jsonl" >/dev/null || fail "a long command that already spoke must pass"
python3 "$TB" "${FIX}/suite-bg.jsonl" >/dev/null || fail "a suite started in the background must pass"
python3 "$TB" "${FIX}/doctor-bg.jsonl" >/dev/null || fail "a doctor started in the background must pass"
echo "OK  turn budget"

echo "=== lock: the conductor's cold start stays within budget ==="
python3 "${KERNEL}/scripts/test_cold_start.py" >/dev/null 2>&1 \
  || fail "cold-start-size no longer counts only the two cold-start pages, or reads more than opened (python3 scripts/test_cold_start.py)"
python3 "${KERNEL}/scripts/cold-start-size.py" --kernel "${KERNEL}" >"${SCRATCH}/idev-cold-start.out" 2>&1 \
  || { cat "${SCRATCH}/idev-cold-start.out"; fail "conductor cold start over budget (python3 scripts/cold-start-size.py)"; }
echo "OK  cold start"

DONE=1
[ ! -s "${FAILURES}" ] || exit 1
echo "selfcheck PASS"
