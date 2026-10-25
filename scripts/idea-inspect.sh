#!/usr/bin/env bash
# Ad-hoc IntelliJ inspect. problems-scan.sh does not call this.
# The Java gate is scripts/plugin/java_inspect.py. It does not install IntelliJ or a JDK.
# Uses an IDE already on the machine when someone runs this file directly. Does not download.
# Bundled plugins stay on the IDE's own path. Do not set idea.plugins.path:
# pointing it at a user plugin folder disables Ultimate and the inspect run
# dies with "Tools are not initialized".
#
#   bash scripts/idea-inspect.sh <repo> [relative-dir]
#   bash scripts/idea-inspect.sh --print-bin
#
# Exit 0: no convention findings (vulnerable-library hits are reported, not failed).
# Exit 1: convention findings remain, or inspect itself failed.
# Exit 2: no local IntelliJ. That is UNPROVEN, not a clean scan.
# IDEA_HOME or IDEA_INSPECT overrides discovery. A set but missing path does not
# fall through to another install.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

discover() {
  if [ -n "${IDEA_INSPECT:-}" ]; then
    [ -x "$IDEA_INSPECT" ] && printf '%s\n' "$IDEA_INSPECT" && return 0
    return 1
  fi
  if [ -n "${IDEA_HOME:-}" ]; then
    if [ -x "$IDEA_HOME/bin/inspect.sh" ]; then
      printf '%s\n' "$IDEA_HOME/bin/inspect.sh"
      return 0
    fi
    if [ -x "$IDEA_HOME/Contents/bin/inspect.sh" ]; then
      printf '%s\n' "$IDEA_HOME/Contents/bin/inspect.sh"
      return 0
    fi
    return 1
  fi
  local dir hit
  for dir in \
    "${HOME}/Applications" \
    /Applications \
    "${HOME}/Library/Application Support/JetBrains/Toolbox/apps" \
    "${HOME}/.local/share/JetBrains/Toolbox/apps"
  do
    [ -d "$dir" ] || continue
    hit="$(find "$dir" -name inspect.sh -path '*/bin/inspect.sh' 2>/dev/null | sort | tail -n 1 || true)"
    if [ -n "$hit" ] && [ -x "$hit" ]; then
      printf '%s\n' "$hit"
      return 0
    fi
  done
  return 1
}

if [ "${1:-}" = "--print-bin" ]; then
  discover
  exit $?
fi

REPO="${1:-}"
if [ -z "$REPO" ] || [ ! -d "$REPO" ]; then
  echo "usage: idea-inspect.sh <repo> [relative-dir]" >&2
  exit 2
fi
REPO="$(cd "$REPO" && pwd)"
ONLY="${2:-}"

INSPECT="$(discover || true)"
if [ -z "$INSPECT" ]; then
  echo "idea inspect: UNPROVEN"
  echo "  no local IntelliJ. java_hygiene 0 is not a clean Problems panel."
  echo "  install IntelliJ locally, or set IDEA_HOME to the install that contains bin/inspect.sh."
  exit 2
fi

modules=()
if [ -n "$ONLY" ]; then
  modules+=("$ONLY")
else
  while IFS= read -r mod; do
    [ -n "$mod" ] && modules+=("$mod")
  done < <(python3 -c '
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import java_hygiene
rels, _scope = java_hygiene.changed_java(Path(sys.argv[2]))
seen = []
for rel in rels:
    mod = rel.split("/", 1)[0] if "/" in rel else "."
    if mod not in seen:
        seen.append(mod)
for mod in seen:
    print(mod)
' "$ROOT/lib" "$REPO")
fi

if [ "${#modules[@]}" -eq 0 ]; then
  echo "idea inspect: no java diff"
  exit 0
fi

PROPS="$(mktemp)"
SYS="$(mktemp -d)"
LOG="$(mktemp -d)"
trap 'rm -rf "$PROPS" "$SYS" "$LOG"' EXIT
cat > "$PROPS" << EOF
idea.system.path=${SYS}
idea.log.path=${LOG}
EOF

echo "idea inspect: ${INSPECT}"
echo "profile: Project Default"
fail=0
for mod in "${modules[@]}"; do
  out="$(mktemp -d)"
  echo "scope: ${mod}"
  chatter="${LOG}/inspect-${mod//\//-}.log"
  set +e
  if [ "$mod" = "." ]; then
    IDEA_PROPERTIES="$PROPS" "$INSPECT" "$REPO" "Project Default" "$out" -format json -v1 >"$chatter" 2>&1
  else
    IDEA_PROPERTIES="$PROPS" "$INSPECT" "$REPO" "Project Default" "$out" -d "$mod" -format json -v1 >"$chatter" 2>&1
  fi
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "  inspect failed (exit ${rc})"
    tail -n 20 "$chatter" || true
    fail=1
    rm -rf "$out"
    continue
  fi
  python3 -c '
import json, os, sys
out = sys.argv[1]
vuln = 0
rows = []
for name in os.listdir(out):
    if not name.endswith(".json") or name.startswith("."):
        continue
    data = json.load(open(os.path.join(out, name), encoding="utf-8"))
    for problem in data.get("problems") or []:
        klass = problem.get("problem_class") or {}
        title = klass.get("name") or ""
        ident = klass.get("id") or ""
        if "易受攻击" in title or ident.startswith("VulnerableLibraries"):
            vuln += 1
            continue
        path = problem.get("file") or ""
        if "/src/" in path:
            path = path.split("/src/", 1)[-1]
        elif "joypaas/" in path:
            path = path.split("joypaas/", 1)[-1]
        rows.append("%s:%s %s %s" % (
            path, problem.get("line"), klass.get("severity") or "", title))
print("  convention: %d" % len(rows))
print("  vulnerable-libraries: %d (other tab, not this gate)" % vuln)
for line in rows[:40]:
    print("  " + line)
if len(rows) > 40:
    print("  ... %d more" % (len(rows) - 40))
sys.exit(1 if rows else 0)
' "$out" || fail=1
  rm -rf "$out"
done

exit "$fail"
