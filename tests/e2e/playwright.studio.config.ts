import { defineConfig, devices } from "@playwright/test";

/** Studio e2e: run with `npx playwright test -c playwright.studio.config.ts`. */
export default defineConfig({
  testDir: ".",
  testMatch: "studio.spec.ts",
  globalSetup: "./fixtures/studio-global-setup.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  use: { trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
