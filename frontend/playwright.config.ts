import { defineConfig, devices } from "@playwright/test";

// The app is served by FastAPI, not by `next dev`, so there is no webServer to start.
// The app must already be running. The host cannot run npm (the checkout path contains
// a colon), so this suite normally runs via the e2e service in docker-compose.yml,
// which sets BASE_URL to http://app:8000.
const baseURL = process.env.BASE_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // The suite runs against one container and one SQLite board, and every save is a
  // whole-board PUT. Two workers mutating the same board concurrently would clobber each
  // other, so the e2e suite is serial. Revisit if each test gets its own board.
  workers: 1,
  fullyParallel: false,
  use: {
    baseURL,
    trace: "retain-on-failure",
    // Wide enough for the 2xl layout, which is the one that puts the assistant beside
    // the board. At the 1280px default the sidebar stacks below and the board columns
    // fall below the fold, which makes coordinate-based drag tests unreliable.
    viewport: { width: 1600, height: 1000 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
