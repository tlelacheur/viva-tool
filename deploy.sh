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

echo "==> Building and launching containers with low-resource caps..."
docker compose build
docker compose up -d

echo "==> Deployment complete."
echo "Frontend: http://localhost:3000"
echo "Backend:  http://localhost:8000/docs"