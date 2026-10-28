#!/usr/bin/env bash
# Snapshot a confirmed+run plan as the patrol pack. Does not move Java tests.
# Industry alignment: promote is irreversible registration — require proof artifacts.
set -euo pipefail

feature="${1:?usage: promote.sh <feature> [plan.yaml]}"
if [[ -n "${2:-}" ]]; then
  plan="$2"
else
  plan="$(python3 "$(cd "$(dirname "$0")/../.." && pwd)/scripts/lib/doc_home.py" --repo . --feature "$feature" --key plan)"
fi
dest="$(python3 "$(cd "$(dirname "$0")/../.." && pwd)/scripts/lib/doc_home.py" --repo . --feature "$feature" --key patrol)"

if [[ ! -f "$plan" ]]; then
  echo "promote: plan not found: $plan" >&2
  exit 1
fi

if ! grep -qE '^accepted:[[:space:]]*true[[:space:]]*$' "$plan"; then
  echo "promote: plan.accepted is not true" >&2
  exit 1
fi

# Prefer python for YAML counts; fall back to grep heuristics.
receipt_mode="unknown"
pass_n=0
fail_n=0
unproven_n=0
if command -v python3 >/dev/null 2>&1; then
  eval "$(python3 - <<PY
from pathlib import Path
try:
    import yaml
except ImportError:
    print('receipt_mode="nogyaml"; pass_n=0; fail_n=0; unproven_n=0')
    raise SystemExit(0)
data = yaml.safe_load(Path("$plan").read_text(encoding="utf-8")) or {}
mode = data.get("mode") or "unknown"
cases = data.get("cases") or []
pass_n = sum(1 for c in cases if isinstance(c, dict) and c.get("status") == "PASS")
fail_n = sum(1 for c in cases if isinstance(c, dict) and c.get("status") == "FAIL")
unproven_n = sum(1 for c in cases if isinstance(c, dict) and c.get("status") == "UNPROVEN")
# PASS must carry non-empty evidence
thin = [c.get("id") for c in cases if isinstance(c, dict) and c.get("status") == "PASS" and not str(c.get("evidence") or "").strip()]
print("receipt_mode=%r" % mode)
print("pass_n=%d" % pass_n)
print("fail_n=%d" % fail_n)
print("unproven_n=%d" % unproven_n)
print("thin_pass=%r" % (",".join(thin) if thin else ""))
PY
)"
else
  receipt_mode=$(grep -E '^mode:' "$plan" | head -1 | awk '{print $2}' | tr -d '"' || echo unknown)
  pass_n=$(grep -cE 'status:[[:space:]]*PASS' "$plan" || true)
  fail_n=$(grep -cE 'status:[[:space:]]*FAIL' "$plan" || true)
  unproven_n=$(grep -cE 'status:[[:space:]]*UNPROVEN' "$plan" || true)
  thin_pass=""
fi

if [[ "${fail_n:-0}" -gt 0 ]]; then
  echo "promote: refuse — plan has FAIL cases ($fail_n); fix before promote" >&2
  exit 1
fi
if [[ "${pass_n:-0}" -lt 1 ]]; then
  echo "promote: refuse — need at least one PASS case with run evidence" >&2
  exit 1
fi
if [[ -n "${thin_pass:-}" ]]; then
  echo "promote: refuse — PASS without evidence: $thin_pass" >&2
  exit 1
fi

if [[ "$receipt_mode" == "selftest" ]]; then
  echo "promote: WARN mode=selftest — patrol will snapshot selftest pack; prefer mode=test after 提测 (see operator-cheatsheet §3.5)" >&2
fi

IDEV_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
bash "$IDEV_ROOT/scripts/codegraph-sync.sh" --repo "$(pwd -P)" promote

mkdir -p "$(dirname "$dest")"
{
  echo "# promoted from ${plan}"
  echo "# do not invent cases at patrol time; replay this file"
  echo "# promote receipt: mode=${receipt_mode} PASS=${pass_n} FAIL=${fail_n} UNPROVEN=${unproven_n}"
  cat "$plan"
} > "$dest"

echo "promote: wrote $dest"
echo "promote receipt: feature=$feature mode=$receipt_mode PASS=$pass_n FAIL=$fail_n UNPROVEN=$unproven_n"
echo "promote: to keep generatedverify tests, move them into a real *Test/*IT package yourself"
