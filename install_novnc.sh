#!/bin/bash
# One-time setup: installs websockify, clones noVNC, enables macOS VNC, writes VNC_PASSWORD to .env
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
NOVNC_DIR="$HOME/novnc"

echo "=== Idealista Bot — noVNC CAPTCHA Solver Setup ==="
echo

# 1. VNC password
read -s -p "Choose a VNC password (min 6 chars, used to access the browser remotely): " VNC_PASS
echo
if [ ${#VNC_PASS} -lt 6 ]; then
    echo "Error: password must be at least 6 characters."
    exit 1
fi

# 2. Enable macOS Screen Sharing + set VNC password
echo
echo "Enabling macOS Screen Sharing (requires sudo)..."
sudo /System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart \
    -activate \
    -configure \
    -clientopts -setvnclegacy -vnclegacy yes -setvncpw -vncpw "$VNC_PASS" \
    -access -on \
    -allowAccessFor -specifiedUsers \
    -configure -users "$USER" \
    -privs -all \
    -restart -agent -menu 2>/dev/null || true

# Ensure the screensharing launchd service is loaded
sudo launchctl enable system/com.apple.screensharing 2>/dev/null || true
sudo launchctl kickstart -k system/com.apple.screensharing 2>/dev/null || true

echo "Screen Sharing enabled on port 5900."

# 3. Install websockify into system Python (same one the bot uses)
echo
echo "Installing websockify..."
sudo /usr/bin/python3 -m pip install --quiet websockify

# 4. Clone noVNC
echo
if [ -d "$NOVNC_DIR" ]; then
    echo "noVNC already present at $NOVNC_DIR — skipping clone."
else
    echo "Cloning noVNC to $NOVNC_DIR..."
    git clone --depth=1 https://github.com/novnc/noVNC.git "$NOVNC_DIR"
fi

# 5. Write VNC_PASSWORD to .env
if grep -q "^VNC_PASSWORD=" "$ENV_FILE" 2>/dev/null; then
    # Update existing entry (macOS sed requires '' after -i)
    sed -i '' "s|^VNC_PASSWORD=.*|VNC_PASSWORD=$VNC_PASS|" "$ENV_FILE"
else
    echo "VNC_PASSWORD=$VNC_PASS" >> "$ENV_FILE"
fi

echo
echo "✅ Setup complete! Your Tailscale IP is: $(tailscale ip --4 2>/dev/null || echo 'unknown — check tailscale status')"
echo
echo "Next time you get a CAPTCHA, just send /solve from Telegram."
echo "A link will appear — tap it on your phone to open the browser and drag the slider."
echo "Send /done when finished."
