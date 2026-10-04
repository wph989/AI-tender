import path from "node:path";

import type { NextConfig } from "next";

// 本地 API 固定使用 8300；容器构建仍通过 API_PROXY_TARGET 指向 api:8000。
const apiTarget = (process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8300").replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // 关掉 Next 16 自动生成的 AGENTS.md / CLAUDE.md：
  // 仓库根已经有自己的 AGENTS.md（编码规范、提交口径都在那儿），
  // 这里再生成一份只会在子目录里多出一份可能冲突的说明，且每次 dev 都重写。
  agentRules: false,
  // 容器镜像只拷运行期需要的东西：不打这句，镜像必须带上 devDependencies 与全部源码。
  output: "standalone",
  // pnpm workspace 的依赖实体提升到仓库根 node_modules/.pnpm，
  // 不把 tracing 根指到仓库根，独立产物里会缺依赖（standalone 的已知坑）。
  outputFileTracingRoot: path.join(__dirname, "../../"),
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: apiTarget + "/api/v1/:path*",
      },
    ];
  },
};

export default nextConfig;
