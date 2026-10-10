"use client";

import { App } from "antd";
import { useEffect } from "react";

/** 长列表中的操作结果必须出现在视口内，同时保留页面原有提示供稍后核对。 */
export function useFeedback(error?: string | null, notice?: string | null) {
  const { message } = App.useApp();
  useEffect(() => {
    if (error) void message.error({ content: error, duration: 6 });
  }, [error, message]);
  useEffect(() => {
    if (notice) void message.info({ content: notice, duration: 4 });
  }, [notice, message]);
}
