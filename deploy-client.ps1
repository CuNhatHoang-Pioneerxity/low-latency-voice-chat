# Deploy RealtimeVoiceChat frontend to Digital Ocean droplet
# Usage: .\deploy-client.ps1

# Configuration
$DROPLET_IP = "143.198.84.169"
$SSH_USER = "root"
$SSH_KEY = "~/.ssh/pioneerxity"
$BACKEND_URL = "https://one-jennet-equal.ngrok-free.app"
$REMOTE_DIR = "/var/www/voicechat"
$LOCAL_DIR = "$PSScriptRoot\code\static"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "RealtimeVoiceChat Frontend Deployment" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Target: ${SSH_USER}@${DROPLET_IP}"
Write-Host "Backend: ${BACKEND_URL}"
Write-Host "==========================================" -ForegroundColor Cyan

# Test SSH connection
Write-Host "[1/6] Testing SSH connection..." -ForegroundColor Yellow
$sshTest = ssh -o ConnectTimeout=5 -o BatchMode=yes -i $SSH_KEY ${SSH_USER}@${DROPLET_IP} "echo 'OK'" 2>&1
if ($sshTest -notmatch "OK") {
    Write-Host "ERROR: Cannot connect to ${DROPLET_IP}. Make sure SSH key is configured." -ForegroundColor Red
    exit 1
}

# Create temp build directory
Write-Host "[2/6] Preparing build files..." -ForegroundColor Yellow
$BUILD_DIR = New-TemporaryDirectory
$BUILD_PATH = $BUILD_DIR.FullName

# Copy frontend files
Copy-Item -Path "$LOCAL_DIR\*" -Destination $BUILD_PATH -Recurse -Force

# Inject backend URL
Write-Host "[3/6] Injecting backend URL into app.js..." -ForegroundColor Yellow
$appJsPath = "$BUILD_PATH\app.js"
$content = Get-Content $appJsPath -Raw
$content = $content -replace "const BACKEND_URL = window\.BACKEND_URL \|\| 'ws://localhost:8000';", "const BACKEND_URL = '$BACKEND_URL';"
Set-Content $appJsPath -Value $content -NoNewline

# Stop existing service
Write-Host "[4/6] Stopping existing services..." -ForegroundColor Yellow
ssh -i $SSH_KEY ${SSH_USER}@${DROPLET_IP} "sudo systemctl stop voicechat-frontend 2>/dev/null || true; sudo pkill -f 'http.server 3000' 2>/dev/null || true"

# Remove old files
Write-Host "[5/6] Deploying files to droplet..." -ForegroundColor Yellow
ssh -i $SSH_KEY ${SSH_USER}@${DROPLET_IP} "sudo rm -rf ${REMOTE_DIR}/* 2>/dev/null; sudo mkdir -p ${REMOTE_DIR}"

# Upload files using scp
$tempRemotePath = "/tmp/voicechat-frontend"
ssh -i $SSH_KEY ${SSH_USER}@${DROPLET_IP} "rm -rf $tempRemotePath; mkdir -p $tempRemotePath"
scp -i $SSH_KEY -r "$BUILD_PATH\*" "${SSH_USER}@${DROPLET_IP}:$tempRemotePath/"

# Move to final location
ssh -i $SSH_KEY ${SSH_USER}@${DROPLET_IP} "sudo cp -r $tempRemotePath/* ${REMOTE_DIR}/; sudo chown -R www-data:www-data ${REMOTE_DIR} 2>/dev/null || sudo chmod -R 755 ${REMOTE_DIR}"

# Setup and start server
Write-Host "[6/6] Starting server..." -ForegroundColor Yellow

# Check if nginx is installed, if not use Python http.server
$nginxCheck = ssh -i $SSH_KEY ${SSH_USER}@${DROPLET_IP} "which nginx 2>/dev/null || echo 'not_installed'"

if ($nginxCheck -eq "not_installed") {
    Write-Host "Nginx not found. Using Python http.server on port 3000..." -ForegroundColor Yellow
    
    # Create systemd service for Python server
    ssh -i $SSH_KEY ${SSH_USER}@${DROPLET_IP} @"
sudo tee /etc/systemd/system/voicechat-frontend.service > /dev/null << 'EOF'
[Unit]
Description=VoiceChat Frontend Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=${REMOTE_DIR}
ExecStart=/usr/bin/python3 -m http.server 3000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
"@
    
    ssh -i $SSH_KEY ${SSH_USER}@${DROPLET_IP} "sudo systemctl daemon-reload; sudo systemctl enable voicechat-frontend; sudo systemctl start voicechat-frontend"
    
    $FRONTEND_URL = "http://${DROPLET_IP}:3000"
} else {
    Write-Host "Nginx found. Configuring..." -ForegroundColor Yellow
    
    # Create nginx config
    ssh -i $SSH_KEY ${SSH_USER}@${DROPLET_IP} @"
sudo tee /etc/nginx/sites-available/voicechat > /dev/null << 'EOF'
server {
    listen 80;
    server_name ${DROPLET_IP};

    root ${REMOTE_DIR};
    index index.html;

    location / {
        try_files \$uri \$uri/ =404;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires 1h;
        add_header Cache-Control 'public, must-revalidate';
    }
}
EOF
"@
    
    ssh -i $SSH_KEY ${SSH_USER}@${DROPLET_IP} "sudo ln -sf /etc/nginx/sites-available/voicechat /etc/nginx/sites-enabled/; sudo nginx -t && sudo systemctl reload nginx"
    
    $FRONTEND_URL = "http://${DROPLET_IP}"
}

# Cleanup
Remove-Item -Path $BUILD_PATH -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "==========================================" -ForegroundColor Green
Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host "Frontend URL: $FRONTEND_URL" -ForegroundColor Green
Write-Host "Backend URL: $BACKEND_URL" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

# Helper function for temp directory
function New-TemporaryDirectory {
    $tempPath = [System.IO.Path]::GetTempPath()
    $tempDir = [System.IO.Path]::Combine($tempPath, [System.IO.Path]::GetRandomFileName())
    New-Item -ItemType Directory -Path $tempDir
}
