import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for BimAtlas web app.
 * Table/spreadsheet tests use fixture data at /table?fixture=1 (no backend required).
 * Run headless: pnpm run test:spreadsheet
 * Run headed (see browser): pnpm run test:spreadsheet:headed
 */
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "pnpm run dev --host 0.0.0.0",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
