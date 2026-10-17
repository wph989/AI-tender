"use client";

import type { ReactNode } from "react";
import { Alert } from "antd";

// 仅识别已知错误特征；未知错误不猜原因，完整响应始终可展开排查。
function failureHint(detail: string): [string, string] {
  if (/RateLimitError|HTTP 429|上游限流/.test(detail))
    return ["模型服务暂时限流", "请稍后重试；若持续出现，请检查模型服务的可用额度。"];
  if (/AuthenticationError|PermissionDeniedError|HTTP 40[13]/.test(detail))
    return ["模型服务拒绝了访问", "请在「模型管理」检查供应商密钥和模型使用权限后重试。"];
  if (/TimeoutError|APITimeoutError|超时|总时长预算已耗尽/.test(detail))
    return ["分析等待时间已超出限制", "可稍后重试；若反复超时，请在「模型管理」检查连接与时间限制。"];
  if (/ConnectError|APIConnectionError|模型连接失败/.test(detail))
    return ["暂时无法连接模型服务", "请稍后重试；若仍失败，请到「模型管理」检查供应商连接。"];
  if (/预算已耗尽|连续无进展且收尾纠正/.test(detail))
    return ["本次分析已达到运行限制", "可在「模型管理 → 分析参数」调整对应限制后继续分析。"];
  return ["本次分析未完成", detail.trim()
    ? "请查看错误详情，处理原因后重试。"
    : "请稍后重试；若仍失败，请到「模型管理 → 调用记录」查看原因。"];
}

export function AnalysisFailureNotice({ message, canceled = false, action }: {
  message?: string | null;
  canceled?: boolean;
  action?: ReactNode;
}) {
  const [title, hint] = canceled
    ? ["分析已停止", "需要时可继续分析，已有结果会保留。"]
    : failureHint(message ?? "");
  return <Alert className="analysis-failure my-3" showIcon type={canceled ? "info" : "error"}
    title={title} action={action} description={<>
      <p>{hint}</p>
      {message && <details className="analysis-failure-detail">
        <summary>{canceled ? "查看停止详情" : "查看错误详情"}</summary>
        <p>{message}</p>
      </details>}
    </>} />;
}
