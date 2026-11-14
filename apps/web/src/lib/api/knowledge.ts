import type { AnalysisReport, Citation, ModuleRecords } from "@/types/knowledge";
import { recordItems } from "@/lib/analysis/records";
import { message } from "@/lib/errors";

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

/** 历史报告只带展示投影，没有独立记录接口；能力判断集中一处，避免调用方各写一遍。 */
export function supportsModuleRecords(report: AnalysisReport): boolean {
  return !report.runtime_retired && Boolean(report.data_schema_version);
}

/** 新版专题直接取独立记录；单个维度失败不阻断其它维度，也不回退旧报告条目。 */
export function loadReportRecords(report: AnalysisReport, signal?: AbortSignal): Promise<AnalysisReport> {
  if (!supportsModuleRecords(report)) return Promise.resolve(report);
  // 请求成功后仍可能在逐条绑定校验中失败，必须与请求错误一起隔离在当前专题。
  const modules = report.modules.map((module) =>
    knowledgeRequest<ModuleRecords>(
      `/analysis/reports/${report.id}/modules/${encodeURIComponent(module.module_key)}/records`,
      "GET", undefined, signal,
    ).then(
      (data) => ({ ...module, status: data.status, progress: data.progress,
        quality_status: data.quality_status, quality_issues: data.quality_issues,
        items: recordItems(data), records_error: undefined, records_loading: false }),
    ).catch((reason: unknown) => ({
      ...module, items: [], records_loading: false,
      records_error: message(reason, "专题结果读取失败，请重试"),
    })));
  return Promise.all(modules).then((loaded) => ({ ...report, modules: loaded }));
}
