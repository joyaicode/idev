#!/usr/bin/env bash
# idev-update: bring an existing checkout (and its installed surface) current.
#
#   bash scripts/idev-update.sh
#
# update = fetch + ff-only pull + rebuild + the one-shot installer re-run.
# The installer is idempotent by design, so "re-run it" IS the upgrade path:
# symlinks HEAL, hook blocks rewrite, the FTS5 index rebuilds against the new
# true source, and the weekly LaunchAgents re-install (their plists hardcode
# the checkout path; a moved checkout leaves dead plists, this heals them).
#
# Local run data (state/traces, lessons, proposals, knowledge-index) is
# gitignored and never touched by pull or install — an upgrade only changes
# what ships in the repo.
#
# Exit: 0 current (possibly after updating), 1 refusable condition.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
[ -f "$ROOT/SKILL.md" ] || { echo "FAIL not a checkout: $ROOT" >&2; exit 1; }
cd "$ROOT"

echo "# idev update"
echo "checkout $ROOT"

# --- refuse a dirty worktree -----------------------------------------------
# Tracked-file changes belong in a commit (the repo's own rule); pulling
# under them risks a conflict this script must not resolve on anyone's
# behalf. state/ and other gitignored data never trip this.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "FAIL 工作区有未提交改动；先 commit 或 checkout，update 不替人合并" >&2
  git status --short --untracked-files=no | head -10 >&2
  exit 1
fi

# --- fetch + count ----------------------------------------------------------
if ! git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
  echo "FAIL no upstream branch configured (git branch --set-upstream-to)" >&2
  exit 1
fi
echo "## fetch"
git fetch --quiet || { echo "FAIL git fetch" >&2; exit 1; }
behind="$(git rev-list --count 'HEAD..@{u}')"
if [ "$behind" = "0" ]; then
  echo "OK   already current ($(git rev-parse --short HEAD))"
  exit 0
fi
echo "behind=$behind commits"

# --- ff-only pull -----------------------------------------------------------
old="$(git rev-parse --short HEAD)"
echo "## pull (ff-only)"
git pull --ff-only --quiet || { echo "FAIL git pull --ff-only（本地分叉了？先 git rebase）" >&2; exit 1; }
echo "OK   $old -> $(git rev-parse --short HEAD)"

# --- rebuild the binaries -----------------------------------------------------
# Same authority rule as init: build when Go exists; without it the python
# lane keeps running and idev_bin.py rebuilds lazily if Go arrives later.
# ideva/idevd are pure Go additions — they fail independently of idev.
if command -v go >/dev/null 2>&1; then
  echo "## rebuild bin/idev"
  if go build -o bin/idev ./cmd/idev; then
    echo "OK   bin/idev rebuilt"
  else
    echo "MISS go build failed — IDEV_ENGINE=python lane still works" >&2
  fi
  echo "## rebuild bin/ideva bin/idevd"
  if go build -o bin/ideva ./cmd/ideva && go build -o bin/idevd ./cmd/idevd; then
    echo "OK   bin/ideva bin/idevd rebuilt"
  else
    echo "MISS agent CLI build failed — bin/idev above is unaffected" >&2
  fi
fi

# --- re-run the one-shot installer (idempotent) ------------------------------
echo "## reinstall"
if ! bash "${ROOT}/scripts/install-idev.sh"; then
  echo "FAIL install-idev reported a failure; the checkout is current, fix the step above and re-run it" >&2
  exit 1
fi

# --- LaunchAgent heal ---------------------------------------------------------
# The three weekly plists hardcode this checkout's absolute path. Re-running
# the installers rewrites them; on a machine without them installed this is
# a no-op install of nothing the person never asked for — so only heal the
# ones that already exist in ~/Library/LaunchAgents.
LA_DIR="${HOME}/Library/LaunchAgents"
for installer in install-weekly-audit.sh install-weekly-evolve.sh install-weekly-agent-review.sh; do
  label="$(grep -m1 -oE 'com\.idev\.[a-z-]+' "${ROOT}/scripts/${installer}" || true)"
  if [ -n "${label}" ] && [ -f "${LA_DIR}/${label}.plist" ]; then
    bash "${ROOT}/scripts/${installer}" >/dev/null 2>&1 \
      && echo "OK   healed ${label}.plist" \
      || echo "MISS ${installer} re-run failed; run it by hand" >&2
  fi
done

echo
echo "## what changed"
git log --oneline "${old}..HEAD" | head -20
count="$(git rev-list --count "${old}..HEAD")"
if [ "$count" -gt 20 ]; then echo "  … and $((count - 20)) more"; fi
echo "细目按日期：references/changelog.md"
echo
echo "重启宿主会话后新 agent/skill 定义生效。"
exit 0
