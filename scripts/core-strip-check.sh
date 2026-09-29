#!/usr/bin/env bash
# idev core-strip-check: keep product-proprietary knowledge OUT of idev CORE.
#
# Two layers:
#   L1 (strict): the 3 canonical core pages MUST NOT contain any proprietary
#       identifier token at all — not even as an "example". These pages are
#       product-agnostic by contract.
#   L2 (annotated): the wider CORE area (conventions/references/module SKILLs)
#       MAY mention a product name ONLY as a labelled illustration
#       (「试点例」/「试点：」/「例：」/"e.g."). An unlabelled proprietary
#       identifier is a leak → FAIL, with the offending line printed.
#
# Product overlays live in the product repo at .idev/pack/. This scan only sees the idev kernel.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
fail=0

echo "# idev core-strip-check"

# ---------- L1: strict pages, zero proprietary tokens ----------
l1_files=(
  conventions/evidence.md
  conventions/coding.md
  conventions/java.md
)
tokens=()
while IFS= read -r _tok; do
  [[ -n "$_tok" ]] && tokens+=("$_tok")
done < <(python3 "$ROOT/scripts/lib/product_marker.py" --strip-tokens)
l1_patterns=()
if [[ ${#tokens[@]} -eq 0 ]]; then
  echo "WARN no evolve:pilot strip-tokens; core token scan is empty"
else
  echo "OK  strip tokens from evolve:pilot (${#tokens[@]})"
  l1_patterns=("${tokens[@]}")
fi

for f in "${l1_files[@]}"; do
  path="$ROOT/$f"
  if [[ ! -f "$path" ]]; then
    echo "FAIL missing $f"
    fail=1
    continue
  fi
  hit=0
  if [[ ${#l1_patterns[@]} -gt 0 ]]; then
    for p in "${l1_patterns[@]}"; do
      if grep -F "$p" "$path" >/dev/null; then
        echo "FAIL(L1) $f still has proprietary token: $p"
        fail=1
        hit=1
      fi
    done
  fi
  [[ $hit -eq 0 ]] && echo "OK  L1 $f"
done

# ---------- L2: wider core, product mentions must be labelled ----------
# Proprietary identifiers that must never appear UNLABELLED in core prose.
l2_patterns=""
if [[ ${#tokens[@]} -gt 0 ]]; then
  l2_patterns="$(python3 -c 'import re,sys; print("|".join(re.escape(t) for t in sys.argv[1:]))' "${tokens[@]}")"
fi
# Lines carrying any of these labels are allowed illustrations.
label_re='试点例|试点：|试点:|例：|例:|e\.g\.|for example|EXAMPLE|example:'
# Core files to scan for L2. Overlay pages / packs / state excluded by construction.
# The root SKILL.md is the entry description — it MUST stay product-agnostic too.
l2_files=()
while IFS= read -r _f; do
  [[ -n "$_f" ]] && l2_files+=("$_f")
done < <(
  cd "$ROOT" && { echo "SKILL.md"; find conventions references deliver verify ops -name '*.md' 2>/dev/null; } \
    | grep -vE '/(identity|config|frontend|landing|specials)\.md$' \
    | grep -vE '^packs/' \
    | grep -vE '^references/changelog\.md$' \
    | sort
)

l2_hit=0
if [[ -n "$l2_patterns" ]]; then
  for rel in "${l2_files[@]}"; do
    path="$ROOT/$rel"
    [[ -f "$path" ]] || continue
    # grep proprietary token lines that do NOT carry an allow-label.
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      echo "FAIL(L2) $rel: unlabelled product token → $line"
      fail=1
      l2_hit=1
    done < <(grep -nE "$l2_patterns" "$path" 2>/dev/null | grep -vE "$label_re" || true)
  done
fi
[[ $l2_hit -eq 0 ]] && echo "OK  L2 core prose (product tokens are labelled or absent)"

# ---------- scope.md must keep the strip contract ----------
if ! grep -q '试点 → 核心' "$ROOT/conventions/scope.md"; then
  echo "FAIL conventions/scope.md missing strip heading"
  fail=1
else
  echo "OK  scope strip heading"
fi

if [[ "$fail" -ne 0 ]]; then
  echo "core-strip-check FAIL"
  echo "fix: move the token to the product repo .idev/pack/, or label the line as 「试点例：…」 if it is only an illustration."
  exit 1
fi
echo "core-strip-check PASS"
exit 0
