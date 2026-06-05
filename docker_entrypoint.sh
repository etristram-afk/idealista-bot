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
echo "Starting X server (Xvfb on :99)..."
# Clean stale lock/socket left behind by a previous container start —
# Xvfb refuses to bind to a display whose lock file already exists.
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null

# Redirect Xvfb output to a file so we can inspect failures instead of
# losing the error message into the void of a backgrounded process.
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp >/var/log/xvfb.log 2>&1 &
XVFB_PID=$!

# Wait up to 10s for Xvfb to be ready — readiness = X socket exists.
# A fixed `sleep 2` is unreliable on a slow NAS.
XVFB_READY=0
for i in $(seq 1 50); do
    if [ -S /tmp/.X11-unix/X99 ] && kill -0 $XVFB_PID 2>/dev/null; then
        XVFB_READY=1
        echo "Xvfb ready (pid $XVFB_PID) after $((i * 200))ms"
        break
    fi
    sleep 0.2
done

if [ "$XVFB_READY" != "1" ]; then
    echo "ERROR: Xvfb did not become ready within 10s. Log follows:"
    cat /var/log/xvfb.log 2>&1 || echo "(no log)"
    echo "Continuing — bot will fail on browser launch until this is fixed."
fi

fluxbox >/var/log/fluxbox.log 2>&1 &
x11vnc -display :99 -forever -nopw -listen 0.0.0.0 -rfbport 5900 >/var/log/x11vnc.log 2>&1 &
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
