import { defineConfig, devices } from "@playwright/test";

// Windows 可能保留默认测试端口；允许隔离验收选用空闲端口，不改业务服务配置。
const port = process.env.PLAYWRIGHT_PORT ?? "4400";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  use: {
    baseURL: `http://localhost:${port}`,
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
    command: `pnpm exec next dev --webpack -p ${port}`,
    url: `http://localhost:${port}/projects`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
