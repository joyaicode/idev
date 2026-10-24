#!/usr/bin/env bash
# A super-linter config runs the local tool it names. It does not download one.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/idev-scan.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/.github/workflows" "$WORK/pkg"
printf 'print("ok")\n' > "$WORK/pkg/ok.py"
cat > "$WORK/.github/workflows/lint.yml" <<'YAML'
name: lint
jobs:
  lint:
    steps:
      - uses: super-linter/super-linter@v7
        env:
          VALIDATE_PYTHON: true
YAML
out="$(bash "$ROOT/coding-scan.sh" "$WORK")"
printf '%s\n' "$out" | grep -q 'scanner run: python3 compile' || {
  printf '%s\n' "$out" >&2
  echo "expected the configured python validator to run" >&2
  exit 1
}
printf '%s\n' "$out" | grep -q 'not downloading super-linter' && {
  echo "a present python tool was reported as not run" >&2
  exit 1
}
echo "OK  coding-scan runs the configured local validator"
