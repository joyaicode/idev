#!/usr/bin/env bash
# One-shot doctor for idev. Exit 0 if core OK.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
fail=0
warn=0
HC_TMP="$(mktemp -d "${TMPDIR:-/tmp}/idev-healthcheck.XXXXXX")"
trap 'rm -rf "$HC_TMP"' EXIT

echo "# idev healthcheck"
echo "root: $ROOT"
echo

TRUE="${HOME}/.cursor/skills/idev"
# "True source" means there is exactly ONE copy of the content — not that
# this particular path is a real directory. A symlink into a git checkout
# satisfies that and is the better shape (the content is versioned), so
# accept either and verify by physical path below.
if [[ ! -e "$TRUE" ]]; then
  echo "FAIL ~/.cursor/skills/idev missing"
  fail=1
elif [[ ! -f "$TRUE/SKILL.md" ]]; then
  echo "FAIL ~/.cursor/skills/idev has no SKILL.md (not an idev root)"
  fail=1
elif [[ -L "$TRUE" ]]; then
  echo "OK  true source ~/.cursor/skills/idev -> $(cd "$TRUE" && pwd -P) (checkout)"
else
  echo "OK  true source ~/.cursor/skills/idev (real directory)"
fi

# The checkout being healthchecked must be the same content as the true
# source — compared physically, so a symlink does not read as a second copy.
if [[ -e "$TRUE" ]] && [[ "$(cd "$ROOT" && pwd -P)" != "$(cd "$TRUE" && pwd -P)" ]]; then
  echo "FAIL this checkout ($ROOT) is not what ~/.cursor/skills/idev resolves to"
  echo "     that would be a second copy; there must be only one"
  fail=1
fi

if [[ -x "$ROOT/scripts/link-idev-aliases.sh" ]]; then
  set +e
  bash "$ROOT/scripts/link-idev-aliases.sh" >$HC_TMP/idev-aliases.out 2>&1
  alias_rc=$?
  set -e
  if [[ $alias_rc -eq 0 ]]; then
    echo "OK  idev aliases (~/.agents + ~/.joycode -> true source)"
    grep '^OK  ' $HC_TMP/idev-aliases.out || true
  else
    echo "FAIL idev aliases"
    cat $HC_TMP/idev-aliases.out || true
    fail=1
  fi
fi

if bash "$ROOT/scripts/workflow-check.sh" >$HC_TMP/idev-wf-check.out 2>&1; then
  echo "OK  workflow-check"
else
  echo "FAIL workflow-check"
  tail -20 $HC_TMP/idev-wf-check.out || true
  fail=1
fi

if bash "$ROOT/scripts/lite-change-smoke.sh" >$HC_TMP/idev-lite-smoke.out 2>&1; then
  echo "OK  lite-change smoke"
  grep -E 'SMOKE_OK|real-ticket|WARN' $HC_TMP/idev-lite-smoke.out || true
  if grep -q '^WARN ' $HC_TMP/idev-lite-smoke.out; then
    warn=$((warn + 1))
  fi
else
  echo "FAIL lite-change smoke"
  tail -40 $HC_TMP/idev-lite-smoke.out || true
  fail=1
fi

if bash "$ROOT/scripts/late-lifecycle-smoke.sh" >$HC_TMP/idev-late-smoke.out 2>&1; then
  echo "OK  late-lifecycle smoke"
  grep -E 'LATE_LIFECYCLE_SMOKE_OK|OK  ' $HC_TMP/idev-late-smoke.out | tail -8 || true
else
  echo "FAIL late-lifecycle smoke"
  tail -50 $HC_TMP/idev-late-smoke.out || true
  fail=1
fi

if bash "$ROOT/scripts/second-product-smoke.sh" >$HC_TMP/idev-second.out 2>&1; then
  echo "OK  second-product smoke"
else
  echo "FAIL second-product smoke"
  cat $HC_TMP/idev-second.out || true
  fail=1
fi


# S8 preflight script must exist and fail-closed on missing ticket
if [[ -x "$ROOT/scripts/s8-preflight.sh" ]]; then
  set +e
  bash "$ROOT/scripts/s8-preflight.sh" >$HC_TMP/idev-s8-pf-usage.out 2>&1
  u_rc=$?
  bash "$ROOT/scripts/s8-preflight.sh" "__idev_hc_missing__" lite-change >$HC_TMP/idev-s8-pf-block.out 2>&1
  b_rc=$?
  set -e
  if [[ $u_rc -eq 1 ]] && grep -q 'usage:' $HC_TMP/idev-s8-pf-usage.out \
     && [[ $b_rc -eq 2 ]] && grep -q 'BLOCKED' $HC_TMP/idev-s8-pf-block.out; then
    echo "OK  s8-preflight (usage=1, missing-ticket=BLOCKED/2)"
  else
    echo "FAIL s8-preflight self-check (usage_rc=$u_rc block_rc=$b_rc)"
    tail -20 $HC_TMP/idev-s8-pf-usage.out $HC_TMP/idev-s8-pf-block.out 2>/dev/null || true
    fail=1
  fi
else
  echo "FAIL s8-preflight.sh missing or not executable"
  fail=1
fi

if bash "$ROOT/scripts/refs-check.sh" >$HC_TMP/idev-refs.out 2>&1; then
  echo "OK  refs-check"
else
  echo "FAIL refs-check"
  grep -E 'MISS|FAIL' $HC_TMP/idev-refs.out || tail -20 $HC_TMP/idev-refs.out || true
  fail=1
fi

if bash "$ROOT/scripts/product-checks.sh" >$HC_TMP/idev-product-checks.out 2>&1; then
  echo "OK  product-checks"
else
  echo "FAIL product-checks"
  cat $HC_TMP/idev-product-checks.out || true
  fail=1
fi

if python3 "$ROOT/scripts/product-layout-check.py" --from-install >$HC_TMP/idev-product-layout.out 2>&1; then
  if grep -q '^WARN ' $HC_TMP/idev-product-layout.out; then
    echo "WARN product-layout"
    cat $HC_TMP/idev-product-layout.out || true
    warn=$((warn + 1))
  else
    echo "OK  product-layout"
  fi
else
  echo "FAIL product-layout"
  cat $HC_TMP/idev-product-layout.out || true
  fail=1
fi

if bash "$ROOT/scripts/core-strip-check.sh" >$HC_TMP/idev-core-strip.out 2>&1; then
  echo "OK  core-strip-check"
else
  echo "FAIL core-strip-check"
  cat $HC_TMP/idev-core-strip.out || true
  fail=1
fi

# Companion grilling: true source is ~/.cursor/skills/grilling (real dir).
GRILL="${HOME}/.cursor/skills/grilling"
if [[ -L "$GRILL" ]]; then
  echo "FAIL ~/.cursor/skills/grilling is a symlink (must be the real directory) -> $(readlink "$GRILL")"
  fail=1
elif [[ ! -d "$GRILL" ]]; then
  echo "WARN companion grilling true source missing ($GRILL)"
  warn=$((warn + 1))
elif [[ -x "$ROOT/scripts/link-companion-skills.sh" ]]; then
  set +e
  bash "$ROOT/scripts/link-companion-skills.sh" grilling >$HC_TMP/idev-companion.out 2>&1
  comp_rc=$?
  set -e
  if [[ $comp_rc -eq 0 ]]; then
    echo "OK  companion grilling true source + aliases"
    grep '^OK  ' $HC_TMP/idev-companion.out || true
  else
    echo "FAIL companion grilling aliases"
    cat $HC_TMP/idev-companion.out || true
    fail=1
  fi
fi

DOCS_SKILL="${HOME}/.cursor/skills/setup-agents-docs/SKILL.md"
if [[ ! -f "$DOCS_SKILL" ]]; then
  echo "WARN companion setup-agents-docs missing ($DOCS_SKILL)"
  warn=$((warn + 1))
elif [[ -x "$ROOT/scripts/link-companion-skills.sh" ]]; then
  set +e
  bash "$ROOT/scripts/link-companion-skills.sh" setup-agents-docs >$HC_TMP/idev-docs-companion.out 2>&1
  docs_rc=$?
  set -e
  if [[ $docs_rc -eq 0 ]]; then
    echo "OK  companion setup-agents-docs + aliases"
    grep '^OK  ' $HC_TMP/idev-docs-companion.out || true
  else
    echo "FAIL companion setup-agents-docs aliases"
    cat $HC_TMP/idev-docs-companion.out || true
    fail=1
  fi
fi

if bash "$ROOT/scripts/audit-traces.sh" 50 >$HC_TMP/idev-audit.out 2>&1; then
  hard=$(sed -n 's/^HARD_COUNT=//p' $HC_TMP/idev-audit.out | tail -1)
  hard="${hard:-0}"
  echo "OK  audit-traces 50 (hard=$hard)"
  if [[ "$hard" != "0" ]]; then
    echo "WARN audit has hard alerts; re-run with --strict to fail CI"
    warn=$((warn + 1))
  fi
else
  echo "FAIL audit-traces"
  fail=1
fi

# Self-evolution and path-view are siblings. A missing evolve script must not skip path-view.
if [[ -x "$ROOT/scripts/evolve-review.sh" && -x "$ROOT/scripts/evolve-curator.sh" \
     && -f "$ROOT/workflows/self-evolve-review.yaml" && -f "$ROOT/references/self-evolution.md" ]]; then
  echo "OK  self-evolution tooling (evolve-review/curator/workflow/doc)"
else
  echo "WARN self-evolution tooling incomplete"
  warn=$((warn + 1))
fi
if bash "$ROOT/scripts/path-view.sh" >$HC_TMP/idev-path-hc.out 2>&1 && grep -q '运行路径' $HC_TMP/idev-path-hc.out; then
  echo "OK  path-view"
else
  echo "WARN path-view"
  warn=$((warn + 1))
fi

# hardcoded-path-check: live scripts/docs must not embed a user's absolute home path.
# state/ (generated logs, traces, outbound-config) and verify/state are machine-local records and are skipped.
# design/ is a verbatim copy of the external design doc (hashed at HEAD); its
# example payloads carry /Users/alice demo paths on purpose. Rewriting them
# would break the "byte-identical to the reviewed text" property the copy exists for.
hp_hits="$(grep -rInE '/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+/' "$ROOT" \
  --exclude-dir=state --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=design \
  --exclude-dir=testdata 2>/dev/null \
  | grep -v 'scripts/healthcheck.sh' || true)"
if [[ -z "$hp_hits" ]]; then
  echo "OK  hardcoded-path-check (no /Users/<name> or /home/<name> in live scripts/docs; state/, design/, testdata/ skipped)"
else
  echo "WARN hardcoded-path-check: residual hardcoded home paths (use \$HOME or ~):"
  printf '%s\n' "$hp_hits" | head -10
  warn=$((warn + 1))
fi

# Outbound handoffs: --heal refreshes the install ledger.
# The session pilot is the current product, not that ledger.
# Gaps remain WARN unless HEALTHCHECK_STRICT_OUTBOUND=1.
if [[ -x "$ROOT/scripts/outbound-skills-check.sh" ]]; then
  if [[ "${HEALTHCHECK_AUTO_OUTBOUND:-1}" == "1" ]]; then
    set +e
    bash "$ROOT/scripts/link-outbound-skills.sh" --heal >$HC_TMP/idev-outbound-link.out 2>&1
    link_rc=$?
    set -e
    if [[ $link_rc -eq 0 ]]; then
      echo "OK  outbound links ensured"
    else
      echo "WARN outbound link ensure skipped/failed"
      grep -E 'FAIL|MISS|HINT' $HC_TMP/idev-outbound-link.out | head -8 || true
      warn=$((warn + 1))
    fi
  fi
  set +e
  bash "$ROOT/scripts/outbound-skills-check.sh" --install >$HC_TMP/idev-outbound.out 2>&1
  oc=$?
  set -e
  if [[ $oc -eq 0 ]]; then
    echo "OK  outbound-skills-check"
    grep -E 'OK  |WARN |note:' $HC_TMP/idev-outbound.out || true
    if [[ -f "$ROOT/state/outbound-config.json" ]]; then
      echo "OK  outbound-config present"
    else
      echo "WARN outbound-config missing — run bootstrap-outbound.sh once"
      warn=$((warn + 1))
    fi
  else
    echo "WARN outbound handoff gaps (not idev-core)"
    grep -E 'MISS|FAIL|WARN|OK  |note:|HINT' $HC_TMP/idev-outbound.out || true
    warn=$((warn + 1))
    if [[ "${HEALTHCHECK_STRICT_OUTBOUND:-0}" == "1" ]]; then
      echo "FAIL outbound (HEALTHCHECK_STRICT_OUTBOUND=1)"
      fail=1
    fi
  fi
fi


# Weekly LaunchAgents (soft): audit + evolve-review
check_weekly_agent() {
  local plist="$1" hint="$2" default_label="$3"
  if [[ -f "$plist" ]]; then
    local label
    label="$(/usr/libexec/PlistBuddy -c 'Print :Label' "$plist" 2>/dev/null || true)"
    label="${label:-$default_label}"
    local uid; uid="$(id -u)"
    if launchctl list 2>/dev/null | grep -F "$label" >/dev/null \
      || launchctl print "gui/${uid}/${label}" >/dev/null 2>&1; then
      echo "OK  weekly LaunchAgent loaded ($label)"
    else
      echo "WARN weekly LaunchAgent plist present but not loaded ($label)"
      warn=$((warn + 1))
    fi
  else
    echo "WARN weekly LaunchAgent not installed ($hint)"
    warn=$((warn + 1))
  fi
}
check_weekly_agent \
  "${HOME}/Library/LaunchAgents/com.idev.weekly-trace-audit.plist" \
  "scripts/install-weekly-audit.sh" \
  "com.idev.weekly-trace-audit"
check_weekly_agent \
  "${HOME}/Library/LaunchAgents/com.idev.weekly-evolve-review.plist" \
  "scripts/install-weekly-evolve.sh" \
  "com.idev.weekly-evolve-review"

echo
if [[ "$fail" -eq 0 ]]; then
  echo "healthcheck PASS (warns=$warn)"
  exit 0
fi
echo "healthcheck FAIL (warns=$warn)"
exit 1
