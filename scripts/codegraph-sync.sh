#!/usr/bin/env bash
# Refresh a repo's CodeGraph index when source files changed.
#
# The caller names the moment. This script decides whether code changed
# since the last successful sync. Unchanged code skips the sync.
#
#   bash scripts/codegraph-sync.sh [--repo <dir>] [--force] <reason>
#
# reason: commit | research | rootcause | docs | agent | promote | semantic
#
# Exit 0: updated, or skipped (no .codegraph/, or code unchanged).
# Exit 1: index exists, code changed, and the refresh did not finish.
# Exit 2: bad arguments.
set -euo pipefail

usage() {
  echo "usage: codegraph-sync.sh [--repo <dir>] [--force] <reason>" >&2
  echo "reason: commit | research | rootcause | docs | agent | promote | semantic" >&2
}

REPO=""
FORCE=0
REASON=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [ -n "${REASON}" ]; then
        usage
        exit 2
      fi
      REASON="$1"
      shift
      ;;
  esac
done

case "${REASON}" in
  commit|research|rootcause|docs|agent|promote|semantic) ;;
  *)
    usage
    exit 2
    ;;
esac

if [ -z "${REPO}" ]; then
  if REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    :
  else
    REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
  fi
fi
REPO="$(cd "${REPO}" && pwd -P)"

if [ ! -d "${REPO}/.codegraph" ]; then
  echo "codegraph-sync: no .codegraph under ${REPO}; skip ${REASON}" >&2
  exit 0
fi

fingerprint() {
  python3 - "${REPO}" <<'PY'
import hashlib, os, subprocess, sys

repo = sys.argv[1]
exts = (
    ".go", ".py", ".java", ".kt", ".kts", ".scala",
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue",
    ".rs", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs",
    ".rb", ".php", ".sql", ".sh", ".bash",
)

def git(*args):
    return subprocess.run(
        ["git", "-C", repo, *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

def is_code(path: str) -> bool:
    return path.lower().endswith(exts)

def file_hash(path: str) -> bytes:
    full = os.path.join(repo, path)
    if not os.path.isfile(full):
        return b"missing"
    digest = hashlib.sha256()
    with open(full, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()

work = git("rev-parse", "--is-inside-work-tree")
inside = work.returncode == 0 and work.stdout.strip() == b"true"
head = b""
paths = []
if inside:
    got = git("rev-parse", "HEAD")
    if got.returncode == 0:
        head = got.stdout.strip()
        changed = git("diff", "HEAD", "--name-only", "-z").stdout.split(b"\0")
        extra = git("ls-files", "--others", "--exclude-standard", "-z").stdout.split(b"\0")
        paths = [p.decode("utf-8", "surrogateescape") for p in changed + extra if p]
        paths = [p for p in paths if is_code(p)]

if not inside or not head:
    found = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".codegraph")]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, repo)
            if is_code(rel):
                found.append(rel)
    paths = found
    head = b"nogit"

acc = hashlib.sha256()
acc.update(b"HEAD ")
acc.update(head)
acc.update(b"\n")
for path in sorted(set(paths)):
    acc.update(path.encode("utf-8", "surrogateescape"))
    acc.update(b"\0")
    acc.update(file_hash(path))
    acc.update(b"\n")
print(acc.hexdigest())
PY
}

CURRENT="$(fingerprint)"
STAMP="${REPO}/.codegraph/sync-stamp"
if [ "${FORCE}" -eq 0 ] && [ -f "${STAMP}" ] && [ "$(cat "${STAMP}")" = "${CURRENT}" ]; then
  echo "codegraph-sync: code unchanged; skip ${REASON}" >&2
  exit 0
fi

if ! command -v codegraph >/dev/null 2>&1; then
  if [ "${CODEGRAPH_SYNC_STRICT_PATH:-}" != 1 ]; then
    export PATH="${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-}"
  fi
fi
if ! command -v codegraph >/dev/null 2>&1; then
  echo "codegraph-sync: codegraph not on PATH; ${REASON} stopped" >&2
  exit 1
fi

if ! codegraph sync -q "${REPO}"; then
  echo "codegraph-sync: sync failed; ${REASON} stopped" >&2
  exit 1
fi
printf '%s\n' "${CURRENT}" > "${STAMP}"
echo "codegraph-sync: code changed; index updated before ${REASON}" >&2
