import { defineConfig, devices } from "@playwright/test";

/**
 * Browser tests against a real API and a production build, each on its own
 * port and data (see e2e/servers), so a dev session on 3100/8000 is untouched.
 * Specs are *.e2e.ts so Vitest doesn't pick them up.
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  globalSetup: "./e2e/global-setup.ts",
  // One worker: tests share the API's rate limits and the demo school.
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  timeout: 60_000,
  // The real stack is slower than unit tests, especially on first requests.
  expect: { timeout: 15_000 },
  use: {
    baseURL: "http://localhost:3200",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node e2e/servers/api.mjs",
      url: "http://127.0.0.1:8100/healthz",
      timeout: 360_000,
      reuseExistingServer: false,
    },
    {
      command: "node e2e/servers/web.mjs",
      url: "http://localhost:3200/login",
      timeout: 600_000,
      reuseExistingServer: false,
    },
  ],
});
