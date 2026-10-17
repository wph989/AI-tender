import type { AnalysisReport, Citation, ModuleRecords } from "@/types/knowledge";
import { recordItems } from "@/lib/analysis/records";

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

/** 新版专题直接取独立记录；单个维度失败不阻断其它维度，也不回退旧报告条目。 */
export async function loadReportRecords(report: AnalysisReport, signal?: AbortSignal): Promise<AnalysisReport> {
  if (report.runtime_retired || !report.data_schema_version) return report;
  const results = await Promise.allSettled(report.modules.map(async (module) => {
    const data = await knowledgeRequest<ModuleRecords>(
      `/analysis/reports/${report.id}/modules/${encodeURIComponent(module.module_key)}/records`,
      "GET", undefined, signal,
    );
    return { ...module, items: recordItems(data), records_error: undefined, records_loading: false };
  }));
  return { ...report, modules: report.modules.map((module, index) => {
    const result = results[index]!;
    return result.status === "fulfilled" ? result.value : {
      ...module, items: [], records_loading: false,
      records_error: result.reason instanceof Error ? result.reason.message : "专题结果读取失败，请重试",
    };
  }) };
}
