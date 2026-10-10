import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// 单测要能解析 @/ 别名：tsc 认 tsconfig 的 paths，vitest 默认不认，必须显式配一次
export default defineConfig({
  test: { include: ["src/**/*.test.ts"] },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
});
