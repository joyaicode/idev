#!/usr/bin/env bash
# Install a Saturday 10:30 local LaunchAgent that runs idev agent-review.
# Pairs with the kernel's weekly-trace-audit at 10:00 and evolve-review at
# 10:15 — this one lands third in the chain, after both kernel reviews have
# written their receipts, so a hard delegation signal lands as a draft
# proposal in the same morning's batch.
#
# agent-review.sh reads delegation records and metrics from a product
# checkout. Without --repo it reviews the checkout it runs in, which for a
# LaunchAgent is the kernel — harmless but useless. The WorkingDirectory
# below makes the kernel the default target on purpose: the first real
# product to pilot the delegation layer can be added by editing the one
# --repo line here, and until then the receipt records "no signal" instead
# of silently reviewing nothing.
#
# Drafts only — never lands. See the script's own header.
set -euo pipefail
IDEV_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
LABEL="com.idev.weekly-agent-review"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$IDEV_ROOT/state/reviews"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

cat > "$PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${IDEV_ROOT}/scripts/agent-review.sh</string>
    <string>--repo</string>
    <string>${IDEV_ROOT}</string>
  </array>
  <key>WorkingDirectory</key><string>${IDEV_ROOT}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>6</integer>
    <key>Hour</key><integer>10</integer>
    <key>Minute</key><integer>30</integer>
  </dict>
  <key>StandardOutPath</key><string>${LOG_DIR}/weekly-agent-review.stdout.log</string>
  <key>StandardErrorPath</key><string>${LOG_DIR}/weekly-agent-review.stderr.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST" 2>/dev/null || launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $PLIST (Saturday 10:30)"
echo "Log: $LOG_DIR/weekly-agent-review.stdout.log"
# Seed once so state/reviews/agent-review-latest.md exists before Saturday.
bash "$IDEV_ROOT/scripts/agent-review.sh" --repo "$IDEV_ROOT" \
  | tee "$LOG_DIR/weekly-agent-review-seed.log" >/dev/null || true
echo "Seeded agent-review-latest.md / agent-review-status.env"
ls -la "$LOG_DIR/agent-review-latest.md" "$LOG_DIR/agent-review-status.env" 2>/dev/null || true
