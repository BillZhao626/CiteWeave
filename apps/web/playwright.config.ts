import { defineConfig } from "@playwright/test";

// The pytest harness owns the isolated database and server-side runtime seam.
// Never point this suite at a running production application.
if (!process.env.CW_BROWSER_TEST_URL || !process.env.CW_BROWSER_DEFAULT_URL) {
  throw new Error(
    "Run via CW_RUN_INTEGRATION=1 pytest tests/test_conversation_browser.py",
  );
}
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.pw.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45000,
  reporter: "list",
  use: {
    baseURL: process.env.CW_BROWSER_TEST_URL,
    browserName: "chromium",
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
