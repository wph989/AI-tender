"use client";

import { App, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import type { ReactNode } from "react";

/** 消息与弹层共享主题和中文文案；组件库负责焦点约束、键盘操作和滚动锁定。 */
export function AntdProvider({ children }: { children: ReactNode }) {
  return (
    <ConfigProvider
      locale={zhCN}
      button={{ autoInsertSpace: false }}
      theme={{
        token: {
          colorPrimary: "#2563eb",
          colorSuccess: "#2d866f",
          colorError: "#bf4764",
          colorText: "#1e293b",
          colorBgLayout: "#f8fafc",
          borderRadius: 8,
          controlHeight: 36,
          fontFamily: '"Segoe UI", "Microsoft YaHei", sans-serif',
        },
      }}
    >
      <App message={{ maxCount: 3, top: 80 }}>{children}</App>
    </ConfigProvider>
  );
}
