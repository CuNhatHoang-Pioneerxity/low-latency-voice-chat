#!/bin/bash
# Configuration
SSH_KEY=~/.ssh/pioneerxity
DROPLET_IP=143.198.84.169
set -e

echo "=========================================="
echo "Target: root@${DROPLET_IP} using key ${SSH_KEY}"
echo "=========================================="

docker-compose build
docker-compose push

scp -i "$SSH_KEY" docker-compose.yml root@${DROPLET_IP}:~/omni-fb
scp -i "$SSH_KEY" .env root@${DROPLET_IP}:~/omni-fb

echo "=========================================="
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes -i $SSH_KEY root@${DROPLET_IP} "echo 'Digital Ocean SSH connection OK'" 2>/dev/null; then
    echo "ERROR: Cannot connect to ${DROPLET_IP}. Make sure SSH key is configured."
    exit 1
fi

ssh -i $SSH_KEY root@${DROPLET_IP} "cd ~/omni-fb && docker-compose down && docker-compose up -d --pull always"