#!/bin/bash
# Configuration
SSH_KEY=~/.ssh/pioneerxity
DROPLET_IP=143.198.84.169
set -e

echo "=========================================="
echo "Target: root@${DROPLET_IP} using key ${SSH_KEY}"
echo "=========================================="

# Test SSH connection first
echo "Testing SSH connection..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes -i $SSH_KEY root@${DROPLET_IP} "echo 'Digital Ocean SSH connection OK'" 2>/dev/null; then
    echo "ERROR: Cannot connect to ${DROPLET_IP}. Make sure SSH key is configured."
    exit 1
fi

# Build and push images
echo "Building Docker images..."
docker-compose build client server

echo "Pushing Docker images..."
docker-compose push client server

# Copy files to remote
echo "Copying files to remote server..."
scp -i "$SSH_KEY" docker-compose.yml root@${DROPLET_IP}:~/omni/
scp -i "$SSH_KEY" .env root@${DROPLET_IP}:~/omni/

# Deploy on remote
echo "Deploying on remote server..."
ssh -i $SSH_KEY root@${DROPLET_IP} "cd ~/omni && docker-compose down && docker-compose pull && docker-compose up -d"

echo "=========================================="
echo "Deployment complete!"
echo "=========================================="
