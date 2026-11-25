import type { AnalysisReport, AnalysisReportDetail, Citation, ReportRecords } from "@/types/knowledge";
import { recordItems } from "@/lib/analysis/records";
import { message } from "@/lib/errors";
import { requestJson } from "@/lib/api/request";

/** 知识接口共用错误协议；AbortSignal 防止快速切换时在途响应覆盖新状态。 */
export async function knowledgeRequest<T>(path: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<T> {
  return requestJson<T>("/api/v1" + path, {
    method,
    signal,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }, (status) => "请求失败，请重试（" + status + "）");
}

export function resolveCitation(ref: Citation, signal?: AbortSignal): Promise<Citation> {
  const { source_id, collection_id, project_id, project_file_id, version_id, parse_run_id, element_id, anchor } = ref;
  return knowledgeRequest<Citation>("/knowledge/citations/resolve", "POST",
    { source_id, collection_id, project_id, project_file_id, version_id, parse_run_id, element_id, anchor }, signal)
    .then((resolved) => ({ ...ref, ...resolved }));
}

/** 专题独立读取记录；失败时清除本专题缓存正文，避免继续展示已撤销的依据。 */
export async function loadReportRecords(
  report: AnalysisReportDetail, signal?: AbortSignal, previous?: AnalysisReport | null,
): Promise<AnalysisReport> {
  const cached = new Map(previous?.id === report.id
    ? previous.modules.map((module) => [module.module_key, module]) : []);
  const versions = Object.fromEntries(report.modules.flatMap((module) => {
    const saved = cached.get(module.module_key);
    return saved?.id === module.id && saved.records_version && !saved.records_error
      ? [[module.module_key, saved.records_version]] : [];
  }));
  let response: ReportRecords;
  try {
    response = await knowledgeRequest<ReportRecords>(
      `/analysis/reports/${report.id}/records`, "POST",
      { module_keys: report.modules.map((module) => module.module_key), versions }, signal,
    );
  } catch (reason: unknown) {
    if (signal?.aborted) throw reason;
    // 整批核验失败时清除正文和版本，下一次成功必须重新获取完整数据。
    return { ...report, modules: report.modules.map((module) => ({
      ...module, items: [], records_loading: false,
      records_version: undefined,
      records_error: message(reason, "专题结果读取失败，请重试"),
    })) };
  }
  const updates = new Map(response.modules.map((update) => [update.module_key, update]));
  const modules = report.modules.map((module) => {
    try {
      const update = updates.get(module.module_key);
      if (!update || update.error || !update.version) {
        throw new Error(update?.error || "专题结果读取失败，请重试");
      }
      if (update.data) {
        const data = update.data;
        return { ...module, status: data.status,
          quality_status: data.quality_status, quality_issues: data.quality_issues,
          items: recordItems(data), records_version: update.version,
          records_error: undefined, records_loading: false };
      }
      const saved = cached.get(module.module_key);
      if (saved?.id !== module.id || saved.records_version !== update.version || saved.records_error) {
        throw new Error("专题缓存已失效，请刷新结果");
      }
      // 服务端已重新核验权限；仅复用正文，最新执行进度仍取报告详情。
      return { ...module, status: saved.status,
        quality_status: saved.quality_status, quality_issues: saved.quality_issues,
        items: saved.items, records_version: update.version,
        records_error: undefined, records_loading: false };
    } catch (reason: unknown) {
      return { ...module, items: [], records_loading: false,
        records_version: undefined,
        records_error: message(reason, "专题结果读取失败，请重试") };
    }
  });
  return { ...report, modules };
}
