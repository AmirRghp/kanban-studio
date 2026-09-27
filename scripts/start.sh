#!/usr/bin/env bash
# Build and start the app in Docker. Serves on http://localhost:8000
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Missing .env in the project root. It must contain OPENROUTER_API_KEY." >&2
  exit 1
fi

echo "Starting the app on http://localhost:8000"
docker compose up --build -d --wait

echo
echo "Running. Stop it with ./scripts/stop.sh"
echo "Logs: docker compose logs -f app"
