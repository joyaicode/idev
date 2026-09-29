#!/usr/bin/env bash
# Install a Saturday 10:00 local LaunchAgent that runs idev trace audit and appends a log.
set -euo pipefail
IDEV_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
LABEL="com.idev.weekly-trace-audit"
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
    <string>${IDEV_ROOT}/scripts/audit-traces.sh</string>
    <string>50</string>
  </array>
  <key>WorkingDirectory</key><string>${IDEV_ROOT}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>6</integer>
    <key>Hour</key><integer>10</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>${LOG_DIR}/weekly-audit.stdout.log</string>
  <key>StandardErrorPath</key><string>${LOG_DIR}/weekly-audit.stderr.log</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed $PLIST (Saturday 10:00)"
echo "Log: $LOG_DIR/weekly-audit.stdout.log"
# run once now to seed log
bash "$IDEV_ROOT/scripts/audit-traces.sh" 50 | tee "$LOG_DIR/weekly-audit-latest.md" >/dev/null
echo "Seeded $LOG_DIR/weekly-audit-latest.md"
# seed healthcheck snapshot (non-fatal)
bash "$IDEV_ROOT/scripts/healthcheck.sh" | tee "$LOG_DIR/healthcheck-latest.md" >/dev/null || true
