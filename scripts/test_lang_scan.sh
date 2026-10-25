#!/usr/bin/env bash
# Language plugins ship with idev. A finding exits 1. A missing plugin file
# is UNPROVEN (exit 2). The scan does not download a toolchain.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/idev-lang.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

fail() {
  echo "FAIL $*" >&2
  exit 1
}

if grep -nE '/Users/|/home/' \
  "$ROOT/lang-scan.sh" \
  "$ROOT/lib/source_diff.py" \
  "$ROOT"/plugin/*_inspect.py
then
  fail "hardcoded home path"
fi

if grep -nE 'qodana|curl |npm ' "$ROOT/lang-scan.sh"; then
  fail "lang-scan still downloads or names qodana"
fi

repo() {
  mkdir -p "$1"
  git -C "$1" init -q
  git -C "$1" -c user.email=dev@example.com -c user.name=dev commit --allow-empty -q -m init
}

repo "$WORK/py"
printf 'def f(a=[]):\n    if a == None:\n        pass\n    try:\n        a\n    except:\n        pass\n' > "$WORK/py/a.py"
out="$(python3 "$ROOT/plugin/python_inspect.py" "$WORK/py" || true)"
printf '%s\n' "$out" | grep -q 'a.py:1 WARNING 不要用可变默认参数' || fail "mutable default missed: $out"
printf '%s\n' "$out" | grep -q 'a.py:2 WARNING 用 is None' || fail "== None missed: $out"
printf '%s\n' "$out" | grep -q 'a.py:6 WARNING 不要裸 except' || fail "bare except missed: $out"
python3 "$ROOT/plugin/python_inspect.py" "$WORK/py" >/dev/null 2>&1 && fail "python finding must exit 1"

repo "$WORK/py-clean"
printf 'def f(a=None):\n    if a is None:\n        return\n    try:\n        a\n    except ValueError:\n        return\n' > "$WORK/py-clean/a.py"
python3 "$ROOT/plugin/python_inspect.py" "$WORK/py-clean" >/dev/null || fail "clean python must exit 0"

repo "$WORK/go"
cat > "$WORK/go/a.go" << 'EOF'
package p

import "time"

func f() {
	for {
		time.Sleep(time.Second)
	}
	x, _ := g()
	_ = x
}

func g() (int, error) { return 0, nil }
EOF
out="$(python3 "$ROOT/plugin/go_inspect.py" "$WORK/go" || true)"
printf '%s\n' "$out" | grep -q 'a.go:7 WARNING 循环里的 time.Sleep' || fail "sleep missed: $out"
printf '%s\n' "$out" | grep -q '返回值被丢掉' && fail "blank identifier is not a sleep finding: $out"
python3 "$ROOT/plugin/go_inspect.py" "$WORK/go" >/dev/null 2>&1 && fail "go finding must exit 1"

repo "$WORK/go-clean"
cat > "$WORK/go-clean/a.go" << 'EOF'
package p

import "time"

func f(items []int) {
	time.Sleep(time.Second)
	for _, item := range items {
		_ = item
	}
}
EOF
python3 "$ROOT/plugin/go_inspect.py" "$WORK/go-clean" >/dev/null || fail "clean go must exit 0"

repo "$WORK/sh"
printf 'echo $1\n' > "$WORK/sh/run.sh"
out="$(python3 "$ROOT/plugin/shell_inspect.py" "$WORK/sh" || true)"
printf '%s\n' "$out" | grep -q 'run.sh:1 WARNING 变量没有加引号' || fail "unquoted var missed: $out"
python3 "$ROOT/plugin/shell_inspect.py" "$WORK/sh" >/dev/null 2>&1 && fail "shell finding must exit 1"

repo "$WORK/sh-clean"
cat > "$WORK/sh-clean/run.sh" << 'ENDSH'
name=$1
echo "$1"
echo "$(echo "$1")"
echo "$(python3 "${S}/x" "${TMP}/y")"
cat <<EOF
${TICKET}
EOF
[[ -n $1 ]]
n=$(($1 + 1))
echo $((1 + 2))
ENDSH
python3 "$ROOT/plugin/shell_inspect.py" "$WORK/sh-clean" >/dev/null || fail "quoted shell must exit 0"

repo "$WORK/sh-nested"
printf 'echo "$(echo $1)"\n' > "$WORK/sh-nested/run.sh"
out="$(python3 "$ROOT/plugin/shell_inspect.py" "$WORK/sh-nested" || true)"
printf '%s\n' "$out" | grep -q 'run.sh:1 WARNING 变量没有加引号' || fail "unquoted inside substitution missed: $out"

repo "$WORK/sh-off"
printf '# shellcheck disable=SC2086\necho $1\n' > "$WORK/sh-off/run.sh"
python3 "$ROOT/plugin/shell_inspect.py" "$WORK/sh-off" >/dev/null || fail "SC2086 disable must exit 0"

repo "$WORK/js"
printf 'function f(a, b) {\n  if (a == b) {\n    var n = 1\n  }\n}\n' > "$WORK/js/a.js"
out="$(python3 "$ROOT/plugin/js_inspect.py" "$WORK/js" || true)"
printf '%s\n' "$out" | grep -q 'a.js:2 WARNING 用 ===' || fail "== missed: $out"
printf '%s\n' "$out" | grep -q 'a.js:3 WARNING 用 let 或 const' || fail "var missed: $out"
python3 "$ROOT/plugin/js_inspect.py" "$WORK/js" >/dev/null 2>&1 && fail "js finding must exit 1"

repo "$WORK/js-clean"
printf 'function f(a, b) {\n  if (a === b && a !== b && a == null) {\n    const n = 1\n    return n\n  }\n}\n' > "$WORK/js-clean/a.js"
python3 "$ROOT/plugin/js_inspect.py" "$WORK/js-clean" >/dev/null || fail "clean js must exit 0"

repo "$WORK/vue"
printf '<li v-for="item in list" v-if="item == 1">\n' > "$WORK/vue/App.vue"
out="$(python3 "$ROOT/plugin/js_inspect.py" "$WORK/vue" || true)"
printf '%s\n' "$out" | grep -q 'App.vue:1 WARNING v-for 缺少 key' || fail "v-for missed: $out"
printf '%s\n' "$out" | grep -q '用 ===' || fail "vue == missed: $out"
python3 "$ROOT/plugin/js_inspect.py" "$WORK/vue" >/dev/null 2>&1 && fail "vue finding must exit 1"

repo "$WORK/vue-clean"
printf '<li v-for="item in list" :key="item.id">\n' > "$WORK/vue-clean/App.vue"
python3 "$ROOT/plugin/js_inspect.py" "$WORK/vue-clean" >/dev/null || fail "keyed v-for must exit 0"

out="$(LANG_PLUGIN_DIR="$WORK/missing" bash "$ROOT/lang-scan.sh" "$WORK/py" || true)"
printf '%s\n' "$out" | grep -q 'lang: UNPROVEN' || fail "missing plugin was not UNPROVEN: $out"
LANG_PLUGIN_DIR="$WORK/missing" bash "$ROOT/lang-scan.sh" "$WORK/py" >/dev/null 2>&1 && fail "missing plugin must exit 2"

set +e
scan_out="$(bash "$ROOT/coding-scan.sh" "$WORK/go")"
scan_rc=$?
set -e
[ "$scan_rc" -eq 1 ] || {
  printf '%s\n' "$scan_out" >&2
  fail "coding-scan must exit 1 on a go finding"
}
printf '%s\n' "$scan_out" | grep -q '循环里的 time.Sleep' || fail "coding-scan hid the go finding"

bash "$ROOT/test_coding_scan_exec.sh" >/dev/null

echo "OK  lang-scan uses the bundled plugins"
