import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AntdRegistry } from "@ant-design/nextjs-registry";
import { AntdProvider } from "@/components/AntdProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI-Tender · 招标文件解析与溯源",
  description: "上传招标文件，使用 Agent 汇总专题要求，并逐条定位原文证据。",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      {/*
       * 底色与字色在这里定一次，子页面只画自己的内容。
       * 不加 min-h-screen：工作台要求 h-screen 撑满，外层再撑一次会多出一条滚动。
       */}
      <body className="bg-slate-50 font-sans text-[14px] leading-[22px] text-slate-800 antialiased">
        <AntdRegistry>
          <AntdProvider>{children}</AntdProvider>
        </AntdRegistry>
      </body>
    </html>
  );
}
