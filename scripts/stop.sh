#!/usr/bin/env bash
# Stop the app and remove its container.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Stopping the app"
docker compose down

echo "Stopped."
