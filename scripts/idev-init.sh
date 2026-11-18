#!/usr/bin/env bash
# idev-init: bootstrap a fresh machine from zero to a working conductor.
#
#   bash scripts/idev-init.sh                          # install from THIS checkout
#   bash scripts/idev-init.sh --repo <URL> --dest DIR  # clone first, then install
#
# init is the guided front door install-idev.sh never had: clone guidance,
# dependency REPORTING (never installation — installing software on
# someone's machine is not this script's authority), a binary build when a
# Go toolchain exists, companion-skill provenance HINTS when the true
# sources are missing, then the existing one-shot installer untouched.
# Re-running is safe: every step below is idempotent or delegates to one
# that is.
#
# Exit: 0 installed (possibly with MISS notes), 1 usage/clone failure.
set -uo pipefail

ROOT=""
REPO=""
DEST=""

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --repo=*) REPO="${1#--repo=}"; shift ;;
    --dest) DEST="${2:-}"; shift 2 ;;
    --dest=*) DEST="${1#--dest=}"; shift ;;
    -h|--help)
      sed -n '2,12p' "$0" 2>/dev/null || true
      exit 0 ;;
    *)
      echo "FAIL unexpected arg $1 (usage: idev-init.sh [--repo <URL>] [--dest <DIR>])" >&2
      exit 1 ;;
  esac
done

echo "# idev init"

# --- locate or clone the checkout ------------------------------------------
if [ -n "$REPO" ]; then
  if [ -z "$DEST" ]; then
    echo "FAIL --dest is required with --repo (no default checkout path is guessed)" >&2
    echo "HINT: bash scripts/idev-init.sh --repo <URL> --dest ~/go/src/github.com/idev" >&2
    exit 1
  fi
  if [ -e "$DEST" ] && [ ! -d "$DEST/.git" ]; then
    echo "FAIL $DEST exists and is not a git checkout" >&2
    exit 1
  fi
  if [ ! -d "$DEST/.git" ]; then
    echo "## clone"
    git clone --depth 1 "$REPO" "$DEST" || { echo "FAIL clone $REPO" >&2; exit 1; }
  else
    echo "OK   checkout exists at $DEST (clone skipped)"
  fi
  ROOT="$(cd "$DEST" && pwd -P)"
else
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
  [ -f "$ROOT/SKILL.md" ] || { echo "FAIL not a checkout: $ROOT (pass --repo/--dest to clone)" >&2; exit 1; }
  echo "OK   checkout $ROOT"
fi

# --- dependency REPORTING (never installation) ------------------------------
# Same list and same rule as install-idev.sh --verify: detect, report, let
# the person install. A missing dependency degrades, it does not block.
dep_missing=0
note_dep() {
  if "$@" >/dev/null 2>&1; then echo "OK   $dep_label"; else
    echo "MISS $dep_label — $dep_hint"; dep_missing=1
  fi
}
dep_label="python3"        note_dep command -v python3
dep_label="PyYAML"         note_dep python3 -c "import yaml"
dep_label="go toolchain"   note_dep sh -c 'command -v go'
dep_label="sqlite3 FTS5"   note_dep python3 -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute(\"CREATE VIRTUAL TABLE t USING fts5(x)\")"
dep_label="codegraph CLI"  note_dep command -v codegraph
if [ "$dep_missing" -ne 0 ]; then
  echo "     (missing deps degrade features; install them yourself, then re-run)"
fi

# --- binaries ----------------------------------------------------------------
# bin/ is gitignored by design; a fresh checkout has none. Build when a Go
# toolchain exists; without one the python lane still runs (IDEV_ENGINE=python,
# README「构建」节), and idev_bin.py rebuilds lazily later if Go arrives.
# ideva/idevd are pure Go additions — they fail independently of idev.
if command -v go >/dev/null 2>&1; then
  echo "## build bin/idev"
  if (cd "$ROOT" && go build -o bin/idev ./cmd/idev); then
    echo "OK   $ROOT/bin/idev"
  else
    echo "MISS go build failed — the python lane still works (IDEV_ENGINE=python)" >&2
  fi
  echo "## build bin/ideva bin/idevd"
  if (cd "$ROOT" && go build -o bin/ideva ./cmd/ideva && go build -o bin/idevd ./cmd/idevd); then
    echo "OK   $ROOT/bin/ideva $ROOT/bin/idevd"
  else
    echo "MISS agent CLI build failed — bin/idev above is unaffected" >&2
  fi
else
  echo "MISS go toolchain — run with IDEV_ENGINE=python, or install Go and re-run" >&2
fi

# --- companion-skill provenance (HINT, never clone) ------------------------
# link-companion-skills.sh links what already exists at ~/.cursor/skills/<name>
# and FAILs on a missing true source. init's job is to say WHERE the true
# sources come from, not to fetch them: cloning a remote repo the person has
# no standing in is not this script's call.
for name in grilling setup-agents-docs; do
  if [ -e "${HOME}/.cursor/skills/${name}/SKILL.md" ] || { [ -L "${HOME}/.cursor/skills/${name}" ] && [ -e "${HOME}/.cursor/skills/${name}" ]; }; then
    echo "OK   companion skill ${name}"
  else
    echo "MISS companion skill ${name} — true source must live at ~/.cursor/skills/${name}" >&2
    echo "HINT git clone <its upstream repo> somewhere, then: ln -s <clone-path> ~/.cursor/skills/${name}" >&2
  fi
done

# --- install (the existing one-shot, untouched) ----------------------------
echo "## install"
if ! bash "${ROOT}/scripts/install-idev.sh"; then
  echo "FAIL install-idev reported a failure; fix the step above and re-run" >&2
  exit 1
fi

echo
echo "## next"
echo "  1. 重启宿主会话（Claude Code / Cursor 只在会话启动时读 agents 与 skills）"
echo "  2. 新会话里说一条交付诉求，或直接 /idev —— 五个执行者（idev-coder 等）已挂载为子 agent"
echo "  3. 以后升级：bash scripts/idev-update.sh"
exit 0
