#!/usr/bin/env bash
# List / mark stale / archive non-landed proposals. Never hard-deletes.
# Usage: evolve-curator.sh [--stale-days N] [--days N] [--apply] [--dir PATH]
# Default: stale at 14d (status: stale), archive at 30d (status: archived).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${IDEV_PROPOSALS_DIR:-$(python3 "$ROOT/scripts/lib/product_sink.py" proposals)}"
STALE_DAYS=14
DAYS=30
APPLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stale-days) STALE_DAYS="$2"; shift 2 ;;
    --days) DAYS="$2"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    --dir) DIR="$2"; shift 2 ;;
    --help|-h)
      echo "usage: $0 [--stale-days N] [--days N] [--apply] [--dir PATH]"
      exit 0
      ;;
    *) echo "unknown: $1" >&2; exit 2 ;;
  esac
done

[[ -d "$DIR" ]] || { echo "No proposals dir: $DIR" >&2; exit 1; }

python3 - "$DIR" "$STALE_DAYS" "$DAYS" "$APPLY" <<'PY'
import os, sys, re, time
from datetime import datetime

prop_dir, stale_days, archive_days, apply_s = (
    sys.argv[1],
    int(sys.argv[2]),
    int(sys.argv[3]),
    sys.argv[4] == "1",
)
now = time.time()
stale_cut = now - stale_days * 86400
archive_cut = now - archive_days * 86400
closed = {"landed", "archived", "rejected", "ga"}
to_archive = []
to_stale = []
kept = []


def status_of(text):
    m = re.search(r"^status:\s*(\S+)", text, re.M)
    return (m.group(1) if m else "unknown").strip().strip('"').lower()


def stamp_block(status, reason):
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    return (
        f"status: {status}\n"
        f"{status}_at: \"{stamp}\"\n"
        f"{status}_by: evolve-curator\n"
        f"{status}_reason: {reason}"
    )


def rewrite_status(text, status, reason):
    block = stamp_block(status, reason)
    if re.search(r"^status:\s*\S+", text, re.M):
        # drop prior curator meta lines for this transition
        text2 = re.sub(
            rf"(?m)^(?:stale|archived)_(?:at|by|reason):.*\n",
            "",
            text,
        )
        return re.sub(r"^status:\s*\S+", block, text2, count=1, flags=re.M)
    return block + "\n" + text


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
    if mtime < archive_cut:
        to_archive.append((name, status, age_days, path, text))
    elif mtime < stale_cut and status != "stale":
        to_stale.append((name, status, age_days, path, text))
    else:
        kept.append((name, status, f"age={age_days}d"))

print(
    f"=== evolve-curator dir={prop_dir} stale_days={stale_days} "
    f"archive_days={archive_days} apply={apply_s} ==="
)
print(
    f"open_or_recent={len(kept)} stale_candidates={len(to_stale)} "
    f"archive_candidates={len(to_archive)}"
)
for name, status, note in kept:
    print(f"KEEP  {name} status={status} ({note})")
for name, status, age, path, text in to_stale:
    print(f"STALE {name} status={status} age={age}d")
    if apply_s:
        open(path, "w", encoding="utf-8").write(
            rewrite_status(text, "stale", f"idle>{stale_days}d")
        )
        print(f"  -> stale {path}")
for name, status, age, path, text in to_archive:
    print(f"ARCHIVE {name} status={status} age={age}d")
    if apply_s:
        open(path, "w", encoding="utf-8").write(
            rewrite_status(text, "archived", f"stale>{archive_days}d")
        )
        print(f"  -> archived {path}")

if (to_stale or to_archive) and not apply_s:
    print("hint: re-run with --apply to mark stale/archived (no delete)")
elif not to_stale and not to_archive:
    print("OK  no stale or archive candidates")
PY
