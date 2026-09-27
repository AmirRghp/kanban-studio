#!/usr/bin/env bash
# Run every test suite. All of them run in Docker: the host cannot run npm or uv,
# because the checkout path contains a colon.
set -euo pipefail

cd "$(dirname "$0")/.."

# The Playwright image pins browsers to a version that must match the installed
# @playwright/test. A drift (e.g. after a lockfile refresh) fails in the e2e stage with
# a confusing 'Executable doesn't exist' error; catch it here, with a clear message.
LOCKED_PW="$(node -p "require('./frontend/package-lock.json').packages['node_modules/@playwright/test'].version")"
IMAGE_PW="$(grep -o 'playwright:v[0-9.]*' Dockerfile | head -1 | tr -d 'v')"
IMAGE_PW="${IMAGE_PW#playwright:}"
if [ "$LOCKED_PW" != "$IMAGE_PW" ]; then
  echo "Playwright version mismatch: lockfile has $LOCKED_PW but the Dockerfile e2e" >&2
  echo "image pins $IMAGE_PW. Align frontend/package-lock.json and the FROM line." >&2
  exit 1
fi

cleanup() {
  # e2e leaves app-e2e running on purpose when the run succeeds (see its comment), but
  # a failed run must not accumulate exited containers and networks. --remove-orphans
  # sweeps the throwaway services; the named volume keeps the real board.
  docker compose --profile test down --remove-orphans >/dev/null 2>&1 || true
  docker compose down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== backend (pytest) ==="
docker compose --profile test run --rm backend-test

echo
echo "=== frontend unit (vitest) ==="
docker compose --profile test run --rm frontend-test

echo
echo "=== frontend e2e (playwright) ==="
# app-e2e reuses the app image, so make sure it is built and current. Cached when
# nothing changed, but a stale image here silently hides new UI from the e2e run.
docker compose build app
# The board is persistent, so e2e runs against its own app instance with a tmpfs
# database. --force-recreate guarantees a freshly seeded board every run, which is
# what makes the suite idempotent; `run` alone would reuse a running container and
# accumulate cards across runs.
docker compose --profile test up -d --force-recreate --wait app-e2e
docker compose --profile test run --rm --no-deps e2e

echo
echo "All suites passed."
