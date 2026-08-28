#!/usr/bin/env bash
set -euo pipefail

echo "==> Pulling changes and rebuilding containers..."

git pull origin main || true
docker compose down
docker compose build --no-cache
docker compose up -d

echo "==> Upgrade complete."