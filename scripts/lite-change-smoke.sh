#!/usr/bin/env bash
# Smoke: lite-change recipe validates + key aliases + step shape.
# Soft-check: a trace in this session's trace directory records a lite-change run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WF="$ROOT/workflows/lite-change.yaml"

echo "# idev lite-change smoke"

if [ ! -f "$WF" ]; then
  echo "FAIL missing $WF"
  exit 1
fi

OUT="$(mktemp "${TMPDIR:-/tmp}/idev-lite-wf.XXXXXX")"
trap 'rm -f "$OUT"' EXIT
if ! bash "$ROOT/scripts/workflow-check.sh" >"$OUT" 2>&1; then
  echo "FAIL workflow-check"
  tail -40 "$OUT" || true
  exit 1
fi
echo "OK  workflow-check"

python3 - <<PY
import sys
from pathlib import Path
try:
    import yaml
except ImportError:
    print("FAIL need PyYAML"); sys.exit(1)
data = yaml.safe_load(Path(r"""$WF""").read_text(encoding="utf-8"))
assert data.get("id") == "lite-change", data.get("id")
aliases = set(data.get("aliases") or [])
need = {"轻量改动", "小改", "小修", "lite-change"}
missing = [a for a in need if a != "lite-change" and a not in aliases]
# id itself covers lite-change
if missing:
    print("FAIL aliases missing:", missing)
    sys.exit(1)
steps = data.get("steps") or []
if len(steps) < 5:
    print(f"FAIL expected >=5 steps, got {len(steps)}")
    sys.exit(1)
kinds = [s.get("kind") for s in steps]
gates = sum(1 for k in kinds if k == "human.gate")
if gates < 2:
    print(f"FAIL expected >=2 human.gate, got {kinds}")
    sys.exit(1)
forbidden = {"auto.seal", "auto.accepted", "skip.signoff", "multi.module.load"}
bad = forbidden.intersection(kinds)
if bad:
    print("FAIL forbidden kinds:", bad)
    sys.exit(1)
print(f"OK  recipe steps={len(steps)} human.gate={gates}")
for s in steps:
    print(f"    - {s.get('id')}: {s.get('kind')} — {s.get('label','')}")
print("SMOKE_OK")
PY

TRACES="$(python3 "$ROOT/scripts/lib/product_sink.py" traces 2>/dev/null || true)"
ev=()
if [ -n "$TRACES" ] && [ -d "$TRACES" ]; then
  while IFS= read -r f; do ev+=("$f"); done \
    < <(grep -l -E '^[[:space:]]*(alias|matched):.*lite-change' "$TRACES"/*.yaml 2>/dev/null || true)
fi
if [ ${#ev[@]} -gt 0 ]; then
  echo "OK  real-ticket evidence:"
  for f in "${ev[@]}"; do echo "    $f"; done
else
  echo "WARN no trace under ${TRACES:-<none>} records a lite-change run yet"
fi
exit 0
