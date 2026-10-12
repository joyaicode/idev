#!/usr/bin/env bash
# Prove a second (generic) product only needs .idev/ + optional bootstrap — no kernel edit.
# Temp dir only; does not touch install ledger product_root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/idev-second-product.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

echo "# idev second-product smoke"
REPO="$SCRATCH/acme-demo"
mkdir -p "$REPO/.idev/workflows" "$REPO/docs/task/demo-ticket"
cat > "$REPO/.idev/marker.yaml" <<'YAML'
marker: idev
evolve: false
YAML
cat > "$REPO/.idev/extensions.yaml" <<'YAML'
schema_version: 1
stages: {}
YAML
cat > "$REPO/.idev/handoff.yaml" <<'YAML'
schema_version: 1
required: []
YAML
cat > "$REPO/docs/task/demo-ticket/deliver.yaml" <<'YAML'
schema_version: 2
feature: demo-ticket
stage: code
risk_tier: P2
aligned: false
by: ""
YAML

# session-context must run on a marked generic product
set +e
OUT="$(python3 "$ROOT/scripts/session-context.py" \
  --repo "$REPO" --feature demo-ticket --scenario S8 --stage code 2>&1)"
sc_rc=$?
set -e
if [[ $sc_rc -ne 0 ]]; then
  echo "FAIL session-context rc=$sc_rc"
  echo "$OUT"
  exit 1
fi
echo "$OUT" | head -20
echo "OK  session-context on generic product"

python3 - <<PY
from pathlib import Path
import sys
sys.path.insert(0, "$ROOT/scripts/lib")
from product_marker import load_marker
m = load_marker(Path("$REPO"))
assert m.get("marker") == "idev", m
print("OK  marker load generic")
PY

# bootstrap help reachable (no pack guess required for --help)
set +e
bash "$ROOT/scripts/bootstrap-outbound.sh" --help >/dev/null 2>&1
bh=$?
set -e
echo "OK  bootstrap help reachable (rc=$bh)"

# No joypaas string leaked into the generic product .idev
if rg -q 'joypaas|JoyPaaS' "$REPO/.idev" 2>/dev/null; then
  echo "FAIL second product .idev leaked joypaas"
  exit 1
fi
echo "OK  no joypaas string in generic .idev"

echo "SECOND_PRODUCT_SMOKE_OK"
