/**
 * 配置中心 API 客户端（设计文档 08，前缀 `/api/v1/config`）。
 *
 * 与 lib/api/llm.ts 一样自带错误解析：两个设置页面对的失败语义不同
 * （门禁 422 带 blockers、权限 403 带原因），合并成一个客户端会互相牵动。
 */

import type {
  ConfigAuditEntry,
  ConfigItemsResponse,
  ConfigRelease,
  ConfigReleaseDetail,
  CreateReleaseResponse,
  ImpactEntry,
} from "@/types/config";

const BASE = "/api/v1/config";

async function readError(response: Response, fallback: string): Promise<Error> {
  let message = fallback + " 返回 " + response.status;
  try {
    const payload: unknown = await response.json();
    if (
      typeof payload === "object" &&
      payload !== null &&
      "error" in payload &&
      typeof payload.error === "object" &&
      payload.error !== null &&
      "message" in payload.error &&
      typeof payload.error.message === "string"
    ) {
      message = payload.error.message;
    }
  } catch {
    // 网关可能返回非 JSON 错误页，保留 HTTP 状态作为可诊断信息。
  }
  return new Error(message);
}

async function send<T>(url: string, method: "GET" | "POST", body?: unknown): Promise<T> {
  const init: RequestInit =
    body === undefined
      ? { method }
      : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const response = await fetch(url, init);
  if (!response.ok) throw await readError(response, "操作失败：" + url);
  return (await response.json()) as T;
}

export function listConfigItems(): Promise<ConfigItemsResponse> {
  return send<ConfigItemsResponse>(BASE + "/items", "GET");
}

export async function listReleases(): Promise<ConfigRelease[]> {
  const data = await send<{ items: ConfigRelease[] }>(BASE + "/releases", "GET");
  return data.items;
}

export function createRelease(input: {
  values: Record<string, unknown>;
  note?: string;
}): Promise<CreateReleaseResponse> {
  return send<CreateReleaseResponse>(BASE + "/releases", "POST", input);
}

export function getRelease(id: number): Promise<ConfigReleaseDetail> {
  return send<ConfigReleaseDetail>(BASE + "/releases/" + id, "GET");
}

export function acknowledgeRelease(
  id: number,
  items: Array<Pick<ImpactEntry, "kind" | "ref">>,
  comment?: string,
): Promise<{ impact: ImpactEntry[] }> {
  return send<{ impact: ImpactEntry[] }>(BASE + "/releases/" + id + "/acknowledge", "POST", {
    items,
    comment,
  });
}

export function activateRelease(
  id: number,
  input: { force: boolean; reason?: string },
): Promise<{ gate: { passed: boolean } }> {
  return send<{ gate: { passed: boolean } }>(
    BASE + "/releases/" + id + "/activate",
    "POST",
    input,
  );
}

export function rollbackRelease(id: number, reason?: string): Promise<{ id: number }> {
  return send<{ id: number }>(BASE + "/releases/" + id + "/rollback", "POST", { reason });
}

export async function listAudit(limit = 50): Promise<ConfigAuditEntry[]> {
  const data = await send<{ items: ConfigAuditEntry[] }>(BASE + "/audit?limit=" + limit, "GET");
  return data.items;
}