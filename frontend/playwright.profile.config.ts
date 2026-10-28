import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/profile-browser",
  workers: 1,
  fullyParallel: false,
  timeout: 60000,
  use: { baseURL: "http://127.0.0.1:3130", ...devices["Desktop Chrome"] },
  reporter: "list",
  outputDir: "test-results-profile",
  webServer: [
    {
      command: "../.venv/bin/python tests/profile-backend.py",
      url: "http://127.0.0.1:3131/api/v1/health",
      timeout: 60000,
      reuseExistingServer: false,
    },
    {
      command: "npm run start -- --port 3130",
      url: "http://127.0.0.1:3130/profile",
      env: { CAREER_AGENT_API_ORIGIN: "http://127.0.0.1:3131" },
      timeout: 60000,
      reuseExistingServer: false,
    },
  ],
});
