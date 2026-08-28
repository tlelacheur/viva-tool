#!/usr/bin/env bash
set -euo pipefail

echo "==> Checking memory & swap configuration..."
SWAP_TOTAL=$(free -m | awk '/Swap:/ {print $2}')
if [ "$SWAP_TOTAL" -eq 0 ]; then
  echo "==> No swap space detected. Creating 2GB swap file to prevent OOM server crashes..."
  sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab || true
  echo "==> 2GB Swap file created and active."
fi

if [ ! -f .env ]; then
  echo "Error: .env file missing. Copy .env.example to .env and configure keys."
  exit 1
fi

echo "==> Opening firewall ports (80, 443, 3000, 8000)..."
if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow 80/tcp || true
  sudo ufw allow 443/tcp || true
  sudo ufw allow 3000/tcp || true
  sudo ufw allow 8000/tcp || true
fi

echo "==> Building and launching containers..."
docker compose build
docker compose up -d

DROPLET_IP=$(curl -s https://api.ipify.org || echo "YOUR_DROPLET_IP")

echo "=================================================="
echo " ==> VivaTool Deployed Successfully with HTTPS!"
echo " Secure HTTPS (Mic Enabled): https://${DROPLET_IP}"
echo " Alternative HTTP URL:       http://${DROPLET_IP}"
echo " Backend API:                http://${DROPLET_IP}:8000/docs"
echo "=================================================="