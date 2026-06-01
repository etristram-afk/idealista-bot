#!/bin/bash

# Idealista Bot Scheduler
# Runs every 5 minutes around the clock

LOG_FILE="$HOME/dev/idealista-bot/logs/scheduler.log"
LAST_RUN_FILE="$HOME/dev/idealista-bot/.last_run"
FORCE_RUN_FILE="$HOME/dev/idealista-bot/.force_run"

CURRENT_TIMESTAMP=$(date +%s)
RUN_INTERVAL=300  # 5 minutes in seconds

# Log this check
echo "$(date): Scheduler check" >> "$LOG_FILE"

# Process pending Telegram commands (/retry, /solve, /status)
/usr/bin/python3 "$HOME/dev/idealista-bot/telegram_listener.py" >> "$LOG_FILE" 2>&1

# Check for force run flag (written by /retry command)
if [ -f "$FORCE_RUN_FILE" ]; then
    rm "$FORCE_RUN_FILE"
    echo "$(date): Force run triggered via Telegram" >> "$LOG_FILE"
else
    # Check last run time
    if [ -f "$LAST_RUN_FILE" ]; then
        LAST_RUN=$(cat "$LAST_RUN_FILE")
        TIME_SINCE_LAST=$((CURRENT_TIMESTAMP - LAST_RUN))

        if [ $TIME_SINCE_LAST -lt $RUN_INTERVAL ]; then
            echo "$(date): Skipping - Last run was ${TIME_SINCE_LAST}s ago" >> "$LOG_FILE"
            exit 0
        fi
    fi
fi

# Run the bot
echo "$(date): Running bot" >> "$LOG_FILE"
echo "$CURRENT_TIMESTAMP" > "$LAST_RUN_FILE"

cd "$HOME/dev/idealista-bot"
/usr/bin/python3 idealista_bot.py >> "$LOG_FILE" 2>&1

echo "$(date): Bot run completed" >> "$LOG_FILE"
