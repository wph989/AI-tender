"use client";

import { App } from "antd";
import { useEffect } from "react";

/** 关闭编辑窗或刷新前保留用户的选择，提交期间则等待服务器给出结果。 */
export function useUnsavedChanges(dirty: boolean, busy = false) {
  const { modal } = App.useApp();
  useEffect(() => {
    if (!dirty) return;
    const prevent = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [dirty]);
  return (close: () => void) => {
    if (busy) return;
    if (!dirty) {
      close();
      return;
    }
    modal.confirm({
      title: "放弃未保存的修改？",
      content: "关闭后，本次修改将不会保存。",
      okText: "放弃修改",
      cancelText: "继续编辑",
      okButtonProps: { danger: true },
      onOk: close,
    });
  };
}
