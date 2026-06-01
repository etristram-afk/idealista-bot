#!/bin/bash
# Deploy idealista-bot to NAS and (re)start the Docker container.
# Usage: bash deploy_to_nas.sh
set -e

NAS_USER="edwardauth"
NAS_HOST="192.168.1.152"
NAS_DIR="/volume1/docker/idealista-bot"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Deploying idealista-bot to NAS ==="
echo

# 1. Sync Python/shell files in-place via SSH (tar creates new inodes which breaks Docker bind mounts)
echo "Syncing files to $NAS_HOST:$NAS_DIR ..."
for f in idealista_bot.py telegram_listener.py setup_session.py novnc_helper.py \
          human_behavior.py google_sheets_sync.py captcha_solver.py docker_entrypoint.sh \
          Dockerfile docker-compose.yml requirements.txt; do
    [ -f "$LOCAL_DIR/$f" ] && \
        cat "$LOCAL_DIR/$f" | ssh "$NAS_USER@$NAS_HOST" "cat > $NAS_DIR/$f" && \
        echo "  ✓ $f"
done

echo
echo "Files synced."

# 2. SSH in: ensure data dirs exist, build image, restart container
echo "Building and starting container on NAS..."
ssh "$NAS_USER@$NAS_HOST" bash <<EOF
set -e
export PATH="/usr/local/bin:\$PATH"
cd $NAS_DIR

# Ensure required data files exist (Docker won't create files, only dirs)
touch tracked_listings.json 2>/dev/null || true
touch listings_database.csv 2>/dev/null || true
mkdir -p logs listings

# Verify .env and browser_state.json are present
if [ ! -f .env ]; then
    echo "ERROR: .env not found at $NAS_DIR/.env — deploy aborted."
    exit 1
fi
if [ ! -f browser_state.json ]; then
    echo "WARNING: browser_state.json not found — bot will start but may hit CAPTCHA immediately."
    echo '{}' > browser_state.json
fi

# Build and (re)start
/usr/local/bin/docker-compose build
/usr/local/bin/docker-compose up -d

echo
echo "Container status:"
/usr/local/bin/docker-compose ps
EOF

echo
echo "✅ Deploy complete."
echo
echo "Useful commands (SSH to NAS first):"
echo "  Logs:    cd $NAS_DIR && docker-compose logs -f"
echo "  Restart: cd $NAS_DIR && docker-compose restart"
echo "  Stop:    cd $NAS_DIR && docker-compose down"
