#!/usr/bin/env bash
set -euo pipefail
repo="${CHECK_REPO:-.}"
feature="${1:?usage: check-feature.sh <feature> <stage> [--product <name>] [--backfill-semantic-gate-dry-run]}"
stage="${2:?usage: check-feature.sh <feature> <stage> [--product <name>] [--backfill-semantic-gate-dry-run]}"
shift 2
exec python3 "$(dirname "$0")/check-feature.py" --repo "$repo" --feature "$feature" --stage "$stage" "$@"
