#!/bin/bash
# SunCredit Autopilot — install as cron job
# Runs every 15 minutes. Logs to ~/suncredit/logs/autopilot.log

SUNCREDIT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CRON_LINE="*/15 * * * * cd $SUNCREDIT_DIR && /usr/bin/python3 -m automation.autopilot >> $SUNCREDIT_DIR/logs/cron.log 2>&1"

echo "Installing SunCredit autopilot cron..."
echo "  $CRON_LINE"

# Add to user's crontab (idempotent — replaces existing suncredit line)
( crontab -l 2>/dev/null | grep -v 'automation.autopilot' ; echo "$CRON_LINE" ) | crontab -

echo "✓ Installed. Current crontab:"
crontab -l | grep autopilot
echo ""
echo "Run manually anytime: cd $SUNCREDIT_DIR && python3 -m automation.autopilot"
echo "Watch logs:           tail -f $SUNCREDIT_DIR/logs/autopilot.log"
