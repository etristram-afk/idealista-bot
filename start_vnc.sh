#!/bin/bash
# Start VNC server for browser access

echo "Starting VNC server..."

# Start Xvfb
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

# Wait for Xvfb to start
sleep 2

# Start window manager
fluxbox &

# Start VNC server (no password for simplicity)
x11vnc -display :99 -forever -nopw -listen 0.0.0.0 -rfbport 5900 &

echo "VNC server started on port 5900"
echo "Connect from Mac using: Screen Sharing -> 100.116.183.37:5900"
echo ""
echo "Now run: python3 /app/setup_session.py"
echo ""

# Keep container running
tail -f /dev/null
