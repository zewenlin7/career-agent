import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:3100", ...devices["Desktop Chrome"] },
  reporter: "list",
  outputDir: "test-results",
  webServer: [
    {
      command: "node --experimental-strip-types tests/fixture-server.ts",
      url: "http://127.0.0.1:3111/__ready",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "npm run start -- --port 3100",
      url: "http://127.0.0.1:3100/profile",
      env: {
        CAREER_AGENT_API_ORIGIN: "http://127.0.0.1:3111",
        CAREER_AGENT_OPS_TOKEN: "synthetic-never-forward",
      },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
