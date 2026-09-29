import type { NextConfig } from "next";

const apiTarget = (process.env.API_PROXY_TARGET ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
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