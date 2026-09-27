#!/usr/bin/env bash
# Run the unit suites only (backend pytest + frontend vitest). Skips the e2e half and
# the app image build, for a fast inner loop. Full coverage: ./scripts/test.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== backend (pytest) ==="
docker compose --profile test run --rm backend-test

echo
echo "=== frontend unit (vitest) ==="
docker compose --profile test run --rm frontend-test

echo
echo "Unit suites passed."
