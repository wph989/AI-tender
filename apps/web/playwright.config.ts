import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:4400",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Edge"],
        channel: "msedge",
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: "mobile",
      use: {
        ...devices["Desktop Edge"],
        channel: "msedge",
        viewport: { width: 390, height: 844 },
      },
    },
  ],
  webServer: {
    // 与本地开发使用同一编译器，避免复用另一种编译器的开发缓存。
    command: "pnpm exec next dev --webpack -p 4400",
    url: "http://localhost:4400/projects",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
