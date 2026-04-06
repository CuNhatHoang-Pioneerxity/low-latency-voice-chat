#!/bin/bash
# Deploy RealtimeVoiceChat frontend to Digital Ocean droplet
# Usage: ./deploy-client.sh

# Configuration
DROPLET_IP="143.198.84.169"
SSH_KEY=~/.ssh/pioneerxity
BACKEND_URL="https://one-jennet-equal.ngrok-free.app"
REMOTE_DIR="/var/www/voicechat"
LOCAL_DIR="$(dirname "$0")/code/static"

echo "=========================================="
echo "RealtimeVoiceChat Frontend Deployment"
echo "=========================================="
echo "Target: root@${DROPLET_IP} using key ${SSH_KEY}"
echo "Backend: ${BACKEND_URL}"
echo "=========================================="

# Check SSH connection
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes -i $SSH_KEY root@${DROPLET_IP} "echo 'SSH connection OK'" 2>/dev/null; then
    echo "ERROR: Cannot connect to ${DROPLET_IP}. Make sure SSH key is configured."
    exit 1
fi

echo "[1/5] Creating temporary build directory..."
BUILD_DIR=$(mktemp -d)
trap "rm -rf $BUILD_DIR" EXIT

echo "[2/5] Copying frontend files..."
cp -r "${LOCAL_DIR}"/* "${BUILD_DIR}/"

echo "[3/5] Injecting backend URL into app.js..."
python3 -c "
import re
with open('${BUILD_DIR}/app.js', 'r') as f:
    content = f.read()

content = re.sub(
    r\"const BACKEND_URL = window\\.BACKEND_URL \\|\\| 'ws://localhost:8000';\",
    \"const BACKEND_URL = '${BACKEND_URL}';\",
    content
)

with open('${BUILD_DIR}/app.js', 'w') as f:
    f.write(content)
"

echo "[4/5] Deploying to droplet..."

# Stop existing frontend service if exists
ssh -i $SSH_KEY root@${DROPLET_IP} "sudo systemctl stop voicechat-frontend 2>/dev/null || true"

# Prepare remote directory
ssh -i $SSH_KEY root@${DROPLET_IP} "sudo mkdir -p ${REMOTE_DIR}"
ssh -i $SSH_KEY root@${DROPLET_IP} "sudo rm -rf ${REMOTE_DIR}/*"

# Upload files
rsync -avz -e "ssh -i $SSH_KEY" --delete "${BUILD_DIR}/" root@${DROPLET_IP}:/tmp/voicechat-frontend/

# Move files into final directory
ssh -i $SSH_KEY root@${DROPLET_IP} "
sudo cp -r /tmp/voicechat-frontend/* ${REMOTE_DIR}/ &&
sudo chown -R root:root ${REMOTE_DIR}
"

echo "[5/5] Setting up Python frontend server..."

# Create / overwrite systemd service
ssh -i $SSH_KEY root@${DROPLET_IP} "cat << 'EOF' | sudo tee /etc/systemd/system/voicechat-frontend.service
[Unit]
Description=VoiceChat Frontend Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${REMOTE_DIR}
ExecStart=/usr/bin/python3 -m http.server 3000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

# Reload + enable + start service
ssh -i $SSH_KEY root@${DROPLET_IP} "
sudo systemctl daemon-reload &&
sudo systemctl enable voicechat-frontend &&
sudo systemctl restart voicechat-frontend
"

FRONTEND_URL="http://${DROPLET_IP}:3000"

echo "=========================================="
echo "✅ Deployment complete!"
echo "Frontend URL: ${FRONTEND_URL}"
echo "Backend URL: ${BACKEND_URL}"
echo "=========================================="