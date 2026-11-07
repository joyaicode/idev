#!/usr/bin/env bash
# usage: ./fetch.sh <url> [output_dir]
set -euo pipefail
url="${1:?usage: $0 <url> [output_dir]}"
outdir="${2:-.}"
mkdir -p "$outdir"
cd "$outdir"
curl -fL --retry 3 --retry-delay 2 -O -J -- "$url"
echo "saved under: $outdir"
