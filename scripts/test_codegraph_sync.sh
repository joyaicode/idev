#!/usr/bin/env bash
# codegraph-sync.sh updates only when source files changed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
SYNC="$ROOT/scripts/codegraph-sync.sh"
fail=0

ok() { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
BIN="$TMP/bin"
mkdir -p "$BIN" "$TMP/repo/.codegraph"
cat > "$BIN/codegraph" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "${CODEGRAPH_LOG:?}"
exit 0
EOF
chmod 755 "$BIN/codegraph"
ln -s "$(command -v python3)" "$BIN/python3"
ln -s "$(command -v git)" "$BIN/git"

git -C "$TMP/repo" init -q
export GIT_AUTHOR_NAME=sync GIT_AUTHOR_EMAIL=sync@example.com
export GIT_COMMITTER_NAME=sync GIT_COMMITTER_EMAIL=sync@example.com
printf 'package p\n' > "$TMP/repo/main.go"
printf '# notes\n' > "$TMP/repo/README.md"
git -C "$TMP/repo" add main.go README.md
git -C "$TMP/repo" commit -q -m init

LOG="$TMP/calls"
export HOME="$TMP/home"
export PATH="$BIN:/usr/bin:/bin"
export CODEGRAPH_LOG="$LOG"

: > "$LOG"
bash "$SYNC" --repo "$TMP/repo" agent >"$TMP/out" 2>"$TMP/err" || bad "first sync should exit 0"
grep -q "index updated before agent" "$TMP/err" && ok "first run updates" || bad "first run should update"
[ "$(wc -l < "$LOG" | tr -d ' ')" = "1" ] && ok "sync called once" || bad "sync call count"

: > "$LOG"
bash "$SYNC" --repo "$TMP/repo" research >/dev/null 2>"$TMP/err" || bad "second sync should exit 0"
grep -q "code unchanged; skip research" "$TMP/err" && ok "unchanged skips" || bad "unchanged should skip"
[ ! -s "$LOG" ] && ok "unchanged does not call codegraph" || bad "unchanged called codegraph"

printf '\n# more notes\n' >> "$TMP/repo/README.md"
: > "$LOG"
bash "$SYNC" --repo "$TMP/repo" docs >/dev/null 2>"$TMP/err" || bad "docs-only should exit 0"
grep -q "code unchanged; skip docs" "$TMP/err" && ok "markdown does not count" || bad "markdown triggered sync"
[ ! -s "$LOG" ] && ok "markdown does not call codegraph" || bad "markdown called codegraph"

printf 'func F() {}\n' >> "$TMP/repo/main.go"
: > "$LOG"
bash "$SYNC" --repo "$TMP/repo" rootcause >/dev/null 2>"$TMP/err" || bad "go edit should exit 0"
grep -q "index updated before rootcause" "$TMP/err" && ok "go edit updates" || bad "go edit should update"
[ -s "$LOG" ] && ok "go edit calls codegraph" || bad "go edit did not call codegraph"

rm -rf "$TMP/repo/.codegraph"
: > "$LOG"
bash "$SYNC" --repo "$TMP/repo" promote >/dev/null 2>"$TMP/err" || bad "missing index should exit 0"
grep -q "no .codegraph" "$TMP/err" && ok "missing index skips" || bad "missing index should skip"
[ ! -s "$LOG" ] && ok "missing index does not call codegraph" || bad "missing index called codegraph"

mkdir -p "$TMP/repo/.codegraph"
printf 'x\n' >> "$TMP/repo/main.go"
rm -f "$BIN/codegraph"
CODEGRAPH_SYNC_STRICT_PATH=1 bash "$SYNC" --repo "$TMP/repo" semantic >/dev/null 2>"$TMP/err" && bad "missing binary should fail" || ok "missing binary stops"
grep -q "not on PATH" "$TMP/err" && ok "missing binary says why" || bad "missing binary message"

bash "$SYNC" --repo "$TMP/repo" nope >/dev/null 2>"$TMP/err" && bad "bad reason should fail" || ok "bad reason rejected"

if [ "$fail" -eq 0 ]; then
  echo "codegraph-sync PASS"
else
  echo "codegraph-sync FAIL $fail"
  exit 1
fi
