#!/usr/bin/env bash
# Install a Saturday 10:15 local LaunchAgent that runs idev evolve-review (draft or no-signal receipt).
# Pairs with weekly-trace-audit at Saturday 10:00. Does NOT land Skill.
set -euo pipefail
IDEV_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
LABEL="com.idev.weekly-evolve-review"
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
    <string>${IDEV_ROOT}/scripts/evolve-review.sh</string>
  </array>
  <key>WorkingDirectory</key><string>${IDEV_ROOT}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>6</integer>
    <key>Hour</key><integer>10</integer>
    <key>Minute</key><integer>15</integer>
  </dict>
  <key>StandardOutPath</key><string>${LOG_DIR}/weekly-evolve.stdout.log</string>
  <key>StandardErrorPath</key><string>${LOG_DIR}/weekly-evolve.stderr.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST" 2>/dev/null || launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $PLIST (Saturday 10:15)"
echo "Log: $LOG_DIR/weekly-evolve.stdout.log"
# seed once
bash "$IDEV_ROOT/scripts/evolve-review.sh" | tee "$LOG_DIR/weekly-evolve-seed.log" >/dev/null || true
echo "Seeded evolve-review-latest.md / evolve-review-status.env"
ls -la "$LOG_DIR/evolve-review-latest.md" "$LOG_DIR/evolve-review-status.env" 2>/dev/null || true
