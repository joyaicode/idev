#!/usr/bin/env bash
# Discovery fails closed. A missing IDEA_HOME does not fall through to another install.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/idev-idea.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK"
out="$(IDEA_HOME="$WORK/missing" bash "$ROOT/idea-inspect.sh" "$WORK" || true)"
printf '%s\n' "$out" | grep -q 'UNPROVEN' || {
  printf '%s\n' "$out" >&2
  echo "missing IDEA_HOME must say UNPROVEN" >&2
  exit 1
}
IDEA_HOME="$WORK/missing" bash "$ROOT/idea-inspect.sh" "$WORK" >/dev/null 2>&1 && {
  echo "missing IDEA_HOME must exit 2" >&2
  exit 1
}
if bash "$ROOT/idea-inspect.sh" --print-bin >/dev/null 2>&1; then
  bin="$(bash "$ROOT/idea-inspect.sh" --print-bin)"
  [ -x "$bin" ] || {
    echo "print-bin is not executable: $bin" >&2
    exit 1
  }
fi
echo "OK  idea-inspect fails closed without a local IDE"
