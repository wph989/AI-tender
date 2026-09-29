/**
 * 工作台取数与结果操作入口：真实 API 与静态开发样本都集中在这里。
 *
 * 为什么按 URL 的 versionId 切换：工作台组件不需要知道项目 API 的路由细节，
 * 同一套 PDF.js 与定位逻辑可以直接检查上传后的版本。
 */

import type {
  WireAttempt,
  WireBlock,
  WireConflict,
  WireExtraction,
  WireEvidence,
  WirePageMeta,
  WireVersionDetail,
} from "@/types/workbench";

export interface WorkbenchData {
  pdfUrl: string;
  /** 项目级动作（导出、冲突裁定）的定位键；静态样本没有项目 → null。 */
  projectId: number | null;
  pages: WirePageMeta[];
  blocksByPage: Record<string, WireBlock[]>;
  extractions: WireExtraction[];
}

interface PagesResponse {
  pages: WirePageMeta[];
}

interface ExtractionsResponse {
  items: WireExtraction[];
}

interface ElementsResponse {
  run_id: number | null;
  elements: WireBlock[];
}

export interface ReviewEvidenceInput {
  anchor: string;
  quote?: string;
  char_start?: number;
  char_end?: number;
}

export interface ReviewInput {
  attempt_id: number;
  action: "confirm" | "correct" | "supplement" | "reject";
  review_mode: "item" | "batch" | "spot_check";
  new_value?: unknown;
  evidence?: ReviewEvidenceInput[];
  comment?: string;
}

interface RerunResponse {
  job_id: string;
  instance_id: number;
  next_machine_attempt_no: number;
}

interface JobResponse {
  id: string;
  status: string;
  error_message?: string | null;
}

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
    // 代理或网关可能返回非 JSON 错误页，保留 HTTP 状态作为可诊断信息。
  }
  return new Error(message);
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw await readError(response, "取数失败：" + url);
  return (await response.json()) as T;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await readError(response, "操作失败：" + url);
  return (await response.json()) as T;
}

export async function loadWorkbench(versionId: number): Promise<WorkbenchData> {
  if (!Number.isSafeInteger(versionId) || versionId < 1) {
    throw new Error("versionId 必须是正整数");
  }
  const base = "/api/v1/versions/" + versionId;
  const [detail, pages, extractions, elements] = await Promise.all([
    getJson<WireVersionDetail>(base),
    getJson<PagesResponse>(base + "/pages"),
    getJson<ExtractionsResponse>(base + "/extractions"),
    getJson<ElementsResponse>(base + "/elements"),
  ]);
  const blocksByPage: Record<string, WireBlock[]> = {};
  for (const element of elements.elements) {
    const list = blocksByPage[String(element.page_no)];
    if (list === undefined) blocksByPage[String(element.page_no)] = [element];
    else list.push(element);
  }
  return {
    pdfUrl: base + "/file",
    projectId: detail.project_id,
    pages: pages.pages,
    blocksByPage,
    extractions: extractions.items,
  };
}

export async function loadWorkbenchForCurrentPage(): Promise<WorkbenchData> {
  const queryValue = new URLSearchParams(window.location.search).get("versionId");
  const versionValue = queryValue ?? process.env.NEXT_PUBLIC_WORKBENCH_VERSION_ID;
  if (versionValue === undefined || versionValue === null || versionValue === "") {
    return loadSampleWorkbench();
  }
  if (!/^[1-9]\d*$/.test(versionValue)) {
    throw new Error("URL 中的 versionId 格式无效");
  }
  return loadWorkbench(Number(versionValue));
}

export async function loadSampleWorkbench(): Promise<WorkbenchData> {
  const [document, extractions] = await Promise.all([
    getJson<{ pages: WirePageMeta[]; blocks_by_page: Record<string, WireBlock[]> }>(
      "/samples/sample-document.json",
    ),
    getJson<{ items: WireExtraction[] }>("/samples/sample-extractions.json"),
  ]);
  return {
    pdfUrl: "/samples/sample-tender.pdf",
    // 静态样本没有项目：导出与冲突入口按「不可用」处理，而不是指向一个假 ID。
    projectId: null,
    pages: document.pages,
    blocksByPage: document.blocks_by_page,
    extractions: extractions.items,
  };
}

export interface FieldStat {
  field_key: string;
  rerun_button: string;
}

/**
 * 字段类型级统计（服务端下发 rerun_button，见设计文档 09 第 8 节）。
 *
 * 只取 items：工作台当前只消费重跑按钮口径，首次通过率等留给统计报表。
 */
export async function loadFieldStats(window = "90d"): Promise<FieldStat[]> {
  const data = await getJson<{ items: FieldStat[] }>(
    "/api/v1/stats/fields?scope=all&window=" + encodeURIComponent(window),
  );
  return data.items;
}

export async function submitReview(instanceId: number, input: ReviewInput): Promise<unknown> {
  return postJson("/api/v1/instances/" + instanceId + "/reviews", input);
}

export async function rerunExtraction(
  extractionId: number,
  hint: string | null = null,
): Promise<RerunResponse> {
  return postJson<RerunResponse>("/api/v1/extractions/" + extractionId + "/rerun", {
    hint: hint?.trim() || null,
  });
}

export async function loadAttempts(extractionId: number): Promise<WireAttempt[]> {
  const response = await getJson<{ items: WireAttempt[] }>(
    "/api/v1/extractions/" + extractionId + "/attempts",
  );
  return response.items;
}

export async function waitForJob(jobId: string, timeoutMs = 120_000): Promise<JobResponse> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const job = await getJson<JobResponse>("/api/v1/jobs/" + jobId);
    if (["completed", "partial", "failed", "canceled"].includes(job.status)) return job;
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  throw new Error("任务仍在运行，请稍后刷新结果");
}

/** 仅供类型导入保持线格式的 evidence 结构稳定。 */
export type { WireEvidence };

export interface ConflictResolution {
  action: "resolve" | "dismiss";
  resolved_id?: number | null;
  comment?: string | null;
}

export async function loadConflicts(projectId: number): Promise<WireConflict[]> {
  const response = await getJson<{ items: WireConflict[] }>(
    "/api/v1/projects/" + projectId + "/conflicts",
  );
  return response.items;
}

export async function resolveConflict(
  conflictId: number,
  input: ConflictResolution,
): Promise<void> {
  await postJson("/api/v1/conflicts/" + conflictId + "/resolve", input);
}

export type ExportOutcome =
  | { kind: "file"; filename: string; blob: Blob }
  | { kind: "job"; jobId: string };

/**
 * 从 Content-Disposition 取文件名。
 *
 * 后端对中文名走 RFC 5987 的 filename*（见 api/storage.py 的 content_disposition），
 * 只读 filename= 会拿到被替换成下划线的名字，所以优先解析 filename*。
 */
export function filenameFromDisposition(header: string | null): string | null {
  if (header === null) return null;
  const extended = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (extended?.[1] !== undefined) {
    try {
      return decodeURIComponent(extended[1]);
    } catch {
      return null;
    }
  }
  const plain = /filename="([^"]+)"/i.exec(header);
  return plain?.[1] ?? null;
}

/** 导出：小项目直接回 xlsx 文件，超过阈值的项目回一个排队 job（见 api/exports.py）。 */
export async function exportProject(
  projectId: number,
  include: "all" | "review" | "verified" = "all",
): Promise<ExportOutcome> {
  const response = await fetch("/api/v1/projects/" + projectId + "/export?include=" + include);
  if (!response.ok) throw await readError(response, "导出失败");
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("spreadsheet")) {
    return {
      kind: "file",
      filename:
        filenameFromDisposition(response.headers.get("content-disposition")) ?? "抽取结果.xlsx",
      blob: await response.blob(),
    };
  }
  const payload = (await response.json()) as { job_id: string };
  return { kind: "job", jobId: payload.job_id };
}

export async function downloadExportJob(jobId: string): Promise<{ filename: string; blob: Blob }> {
  const response = await fetch("/api/v1/jobs/" + jobId + "/download");
  if (!response.ok) throw await readError(response, "下载导出文件失败");
  return {
    filename:
      filenameFromDisposition(response.headers.get("content-disposition")) ?? "抽取结果.xlsx",
    blob: await response.blob(),
  };
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}