import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AntdRegistry } from "@ant-design/nextjs-registry";
import { AntdProvider } from "@/components/AntdProvider";
import { AppRail } from "@/components/AppRail";
import { AppViewport } from "@/components/AppViewport";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI-Tender · 招标文件解析与溯源",
  description: "上传招标文件，使用 Agent 汇总专题要求，并逐条定位原文证据。",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      {/*
       * 根布局统一保留导航；下方视口接收剩余高度，避免各页面重复占满屏幕。
       */}
      <body className="bg-slate-50 font-sans text-[14px] leading-[22px] text-slate-800 antialiased">
        <AntdRegistry>
          <AntdProvider>
            <div className="app-frame">
              <AppRail />
              <AppViewport>{children}</AppViewport>
            </div>
          </AntdProvider>
        </AntdRegistry>
      </body>
    </html>
  );
}
