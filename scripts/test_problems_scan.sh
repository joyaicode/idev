#!/usr/bin/env bash
# The Java gate runs the bundled plugin and does not call Java or IntelliJ.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/idev-problems.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

fail() {
  printf '%s\n' "$1" >&2
  exit 1
}

grep -RInE '/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+/' \
  "$ROOT/problems-scan.sh" "$ROOT/plugin/java_inspect.py" && fail "hardcoded home path"
grep -q 'idea-inspect' "$ROOT/problems-scan.sh" && fail "problems-scan still calls IntelliJ"
grep -q 'qodana' "$ROOT/problems-scan.sh" && fail "problems-scan still installs Qodana"

python3 "$ROOT/test_java_inspect.py" >/dev/null

mkdir -p "$WORK/bin"
cat > "$WORK/bin/java" << EOF
#!/bin/sh
echo called >> "$WORK/called"
exit 1
EOF
cp "$WORK/bin/java" "$WORK/bin/javac"
chmod +x "$WORK/bin/java" "$WORK/bin/javac"

repo="$WORK/repo"
mkdir -p "$repo/src"
git -C "$repo" init -q
printf '<project/>\n' > "$repo/pom.xml"
cat > "$repo/src/A.java" << 'EOF'
class A {
    private void gone() {}
    void run() {}
}
EOF

export PATH="$WORK/bin:/usr/bin:/bin"
export HOME="$WORK/home"
mkdir -p "$HOME"
out="$(bash "$ROOT/problems-scan.sh" "$repo" || true)"
printf '%s\n' "$out" | grep -q 'engine: plugin' || fail "plugin engine was not used"
printf '%s\n' "$out" | grep -q 'convention: 1' || fail "unused private method was missed"
printf '%s\n' "$out" | grep -q 'src/A.java:' || fail "finding had no file:line"
bash "$ROOT/problems-scan.sh" "$repo" >/dev/null 2>&1 && fail "finding must exit 1"
[ ! -f "$WORK/called" ] || fail "java or javac was executed"

empty="$WORK/empty"
mkdir -p "$empty"
git -C "$empty" init -q
printf '<project/>\n' > "$empty/pom.xml"
out="$(bash "$ROOT/problems-scan.sh" "$empty")"
printf '%s\n' "$out" | grep -q 'problems: no java diff' || fail "empty diff should not scan"

bash "$ROOT/test_coding_scan_exec.sh" >/dev/null

set +e
scan_out="$(HOME="$HOME" PATH="$PATH" bash "$ROOT/coding-scan.sh" "$repo")"
scan_rc=$?
set -e
[ "$scan_rc" -eq 1 ] || {
  printf '%s\n' "$scan_out" >&2
  fail "coding-scan must exit 1 when the plugin finds a private method"
}
printf '%s\n' "$scan_out" | grep -q 'convention: 1' || fail "coding-scan hid the plugin finding"
[ ! -f "$WORK/called" ] || fail "coding-scan executed java"

echo "OK  problems-scan uses the bundled plugin"
