#!/usr/bin/env bash
# Dry-run by default. --apply unlinks old execution artifacts only.
# --compact folds cited or aged residue into .idev/memory.md first.
exec python3 "$(cd "$(dirname "$0")" && pwd)/execution-clean.py" "$@"
