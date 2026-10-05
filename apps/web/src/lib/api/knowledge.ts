import type { Citation } from "@/types/knowledge";

/** 新接口沿用现有错误协议；AbortSignal 用于防止快速切换时旧响应覆盖新状态。 */
export async function knowledgeRequest<T>(path: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch("/api/v1" + path, {
    method, signal,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error?.message ?? "请求失败，请重试（" + response.status + "）");
  return data as T;
}

export function resolveCitation(ref: Citation, signal?: AbortSignal): Promise<Citation> {
  const { source_id, collection_id, project_id, project_file_id, version_id, parse_run_id, element_id, anchor } = ref;
  return knowledgeRequest<Citation>("/knowledge/citations/resolve", "POST",
    { source_id, collection_id, project_id, project_file_id, version_id, parse_run_id, element_id, anchor }, signal)
    .then((resolved) => ({ ...ref, ...resolved }));
}
