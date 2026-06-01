#!/bin/bash

# Docker entrypoint script for Idealista Bot
# Primary: email_listener.py triggers bot when Idealista notification arrives
# Fallback: once-daily scan at 9am in case email is missed

echo "==================================="
echo "Idealista Bot Starting"
echo "==================================="

# Use the venv Python if present (playwright/python:v1.60+ puts everything in /app/.venv)
if [ -f /app/.venv/bin/python3 ]; then
    export PATH="/app/.venv/bin:$PATH"
fi
echo "Time Zone: $TZ"
echo "Current time: $(date)"
echo ""

# Check if browser state exists
if [ ! -f /app/browser_state.json ]; then
    echo "⚠️  WARNING: browser_state.json not found!"
    echo ""
fi

echo ""
echo "Starting VNC server..."
Xvfb :99 -screen 0 1920x1080x24 &
sleep 2
fluxbox &
x11vnc -display :99 -forever -nopw -listen 0.0.0.0 -rfbport 5900 &
echo "VNC ready on port 5900"
echo ""

# Telegram listener runs every 15 seconds in the background
echo "Starting Telegram listener..."
(while true; do
    cd /app && python3 telegram_listener.py
    sleep 15
done) &

# Email listener — triggers bot immediately when Idealista notification arrives
echo "Starting email listener..."
(while true; do
    cd /app && python3 email_listener.py
    sleep 30
done) &

# Fallback: once-daily scan at 9am Spain time in case an email was missed
echo "Starting daily fallback scheduler..."
echo ""

LAST_RUN_FILE="/app/.last_run"
touch "$LAST_RUN_FILE"

while true; do
    SPAIN_HOUR=$(TZ='Europe/Madrid' date +%H)
    SPAIN_TIME=$(TZ='Europe/Madrid' date '+%Y-%m-%d %H:%M:%S %Z')
    CURRENT_DAY=$(TZ='Europe/Madrid' date +%Y-%m-%d)
    LAST_RUN=$(cat "$LAST_RUN_FILE" 2>/dev/null || echo "0")

    if [ "$SPAIN_HOUR" -eq 9 ] && [ "$LAST_RUN" != "$CURRENT_DAY" ]; then
        echo "[$SPAIN_TIME] Daily fallback scan"
        cd /app && python3 idealista_bot.py
        echo "$CURRENT_DAY" > "$LAST_RUN_FILE"
        echo "[$SPAIN_TIME] Fallback scan completed"
        echo ""
    fi

    sleep 60
done
