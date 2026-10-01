import path from "node:path";

import type { NextConfig } from "next";

const apiTarget = (process.env.API_PROXY_TARGET ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
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