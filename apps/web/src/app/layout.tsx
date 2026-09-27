import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI-Tender 招标文件工作台",
  description: "招标文件解析结果与原文定位（阶段 1：静态样本数据）",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="bg-slate-100 font-sans text-slate-900 antialiased">{children}</body>
    </html>
  );
}