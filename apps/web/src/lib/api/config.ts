/** 配置中心 API 客户端。 */

import type {
  ConfigItemsResponse,
  ConfigRelease,
  ConfigReleaseDetail,
  CreateReleaseResponse,
  ImpactEntry,
} from "@/types/config";

import { sendJson } from "@/lib/api/request";

const BASE = "/api/v1/config";

export function listConfigItems(): Promise<ConfigItemsResponse> {
  return sendJson<ConfigItemsResponse>(BASE + "/items", "GET");
}

export async function listReleases(): Promise<ConfigRelease[]> {
  const data = await sendJson<{ items: ConfigRelease[] }>(BASE + "/releases", "GET");
  return data.items;
}

export function createRelease(input: {
  values: Record<string, unknown>;
  note?: string;
}): Promise<CreateReleaseResponse> {
  return sendJson<CreateReleaseResponse>(BASE + "/releases", "POST", input);
}

export function getRelease(id: number): Promise<ConfigReleaseDetail> {
  return sendJson<ConfigReleaseDetail>(BASE + "/releases/" + id, "GET");
}

export function acknowledgeRelease(
  id: number,
  items: Array<Pick<ImpactEntry, "kind" | "ref">>,
  comment?: string,
): Promise<{ impact: ImpactEntry[] }> {
  return sendJson<{ impact: ImpactEntry[] }>(BASE + "/releases/" + id + "/acknowledge", "POST", {
    items,
    comment,
  });
}

export function activateRelease(
  id: number,
  input: { reason?: string },
): Promise<{ gate: { passed: boolean } }> {
  return sendJson<{ gate: { passed: boolean } }>(
    BASE + "/releases/" + id + "/activate",
    "POST",
    input,
  );
}

export function rollbackRelease(id: number, reason?: string): Promise<{ id: number }> {
  return sendJson<{ id: number }>(BASE + "/releases/" + id + "/rollback", "POST", { reason });
}
