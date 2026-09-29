#!/usr/bin/env bash
# Usage: ticket-metrics.sh [--repo <product-repo-root>]   (facts only; n/a when unknown)
set -euo pipefail
exec python3 "$(cd "$(dirname "$0")" && pwd -P)/ticket_metrics.py" "$@"
