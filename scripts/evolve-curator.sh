#!/usr/bin/env bash
# List / archive stale non-landed proposals. Never hard-deletes.
# Usage: evolve-curator.sh [--days N] [--apply] [--dir PATH]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${IDEV_PROPOSALS_DIR:-$(python3 "$ROOT/scripts/lib/product_sink.py" proposals)}"
DAYS=30
APPLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --days) DAYS="$2"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    --dir) DIR="$2"; shift 2 ;;
    --help|-h) echo "usage: $0 [--days N] [--apply] [--dir PATH]"; exit 0 ;;
    *) echo "unknown: $1" >&2; exit 2 ;;
  esac
done

[[ -d "$DIR" ]] || { echo "No proposals dir: $DIR" >&2; exit 1; }

python3 - "$DIR" "$DAYS" "$APPLY" <<'PY'
import os, sys, re, time
from datetime import datetime, timezone

prop_dir, days_s, apply_s = sys.argv[1], int(sys.argv[2]), sys.argv[3] == "1"
now = time.time()
cutoff = now - days_s * 86400
closed = {"landed", "archived", "rejected", "ga"}
stale = []
kept = []

def status_of(text):
    m = re.search(r"^status:\s*(\S+)", text, re.M)
    return (m.group(1) if m else "unknown").strip().strip('"').lower()

for name in sorted(os.listdir(prop_dir)):
    if not name.endswith(".md"):
        continue
    path = os.path.join(prop_dir, name)
    try:
        st = os.stat(path)
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError as e:
        print(f"SKIP {name}: {e}")
        continue
    status = status_of(text)
    if status in closed:
        kept.append((name, status, "closed"))
        continue
    mtime = st.st_mtime
    age_days = int((now - mtime) / 86400)
    if mtime < cutoff:
        stale.append((name, status, age_days, path, text))
    else:
        kept.append((name, status, f"age={age_days}d"))

print(f"=== evolve-curator dir={prop_dir} days={days_s} apply={apply_s} ===")
print(f"open_or_recent={len(kept)} stale_candidates={len(stale)}")
for name, status, note in kept:
    print(f"KEEP  {name} status={status} ({note})")
for name, status, age, path, text in stale:
    print(f"STALE {name} status={status} age={age}d")
    if not apply_s:
        continue
    if re.search(r"^status:\s*\S+", text, re.M):
        new = re.sub(r"^status:\s*\S+", "status: archived", text, count=1, flags=re.M)
    else:
        new = f"status: archived\n" + text
    if "archived_by: evolve-curator" not in new:
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        new = new.replace("status: archived", f"status: archived\narchived_at: \"{stamp}\"\narchived_by: evolve-curator\narchived_reason: stale>{days_s}d", 1)
    open(path, "w", encoding="utf-8").write(new)
    print(f"  -> archived {path}")

if stale and not apply_s:
    print("hint: re-run with --apply to mark stale as archived (no delete)")
elif not stale:
    print("OK  no stale proposals")
PY
