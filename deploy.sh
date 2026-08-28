#!/usr/bin/env bash
set -euo pipefail

echo "==> Starting initial deployment on Droplet..."

if [ ! -f .env ]; then
  echo "Error: .env file missing. Copy .env.example to .env and configure keys."
  exit 1
fi

docker compose build
docker compose up -d

echo "==> Deployment complete."
echo "Frontend: http://localhost:3000"
echo "Backend:  http://localhost:8000/docs"