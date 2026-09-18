import { defineConfig, devices } from "@playwright/test";

/**
 * Browser tests.
 *
 * These assume both servers are already running (`make demo`). Playwright can start them
 * itself via `webServer`, but on a laptop that means a cold Next build inside the test
 * timeout, which fails for reasons that have nothing to do with the code under test.
 * `make e2e` documents the prerequisite instead.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: { timeout: 12_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  outputDir: "./test-results",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    // The demo is designed for a 1440px screen-share; test what we ship.
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
});
