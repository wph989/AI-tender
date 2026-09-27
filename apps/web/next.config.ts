import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // 样本 PDF、页面几何、pdfjs 运行时资源都放在 public/ 下按静态路径取，
  // 不经过任何服务端接口——这一刀刻意不碰后端（见 docs/工程/07 阶段 1）。
};

export default nextConfig;