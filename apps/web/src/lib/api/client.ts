/**
 * 文档预览与项目文件操作入口。
 *
 * 为什么按 URL 的 versionId 切换：工作台组件不需要知道项目 API 的路由细节，
 * 同一套 PDF.js 与定位逻辑可以直接检查上传后的版本。
 */

import type { FileRole, ParseTier, UploadResult, WireProject, WireProjectDetail } from "@/types/projects";
import type {
  WireBlock,
  WireOutlineItem,
  WirePageMeta,
  WireVersionDetail,
} from "@/types/workbench";

export interface WorkbenchData {
  pdfUrl: string;
  /** 所属项目，用于返回综合分析。 */
  projectId: number | null;
  pages: WirePageMeta[];
  blocksByPage: Record<string, WireBlock[]>;
  /** 最近一次解析状态用于解释文档是否已就绪。 */
  parseStatus: string | null;
  /** 解析失败的可读原因（error_message 优先，回落 error_code）。 */
  parseError: string | null;
  /** 最近一次解析用的档位：重新解析要沿用它，不能顺手把档位也换掉。 */
  parseTier: string | null;
  /** 最近一次解析用的 OCR 模式：重新解析沿用它，理由同 parseTier。 */
  parseOcrMode: string | null;
}

interface PagesResponse {
  pages: WirePageMeta[];
}

interface ElementsResponse {
  run_id: number | null;
  elements: WireBlock[];
}

export interface JobResponse {
  id: string;
  status: string;
  /** 流水线阶段：converting / submitting / parsing 等（见 worker/dispatch.py 的 STREAMS）。 */
  stage?: string | null;
  progress?: Record<string, unknown> | null;
  error_code?: string | null;
  error_message?: string | null;
}

/** 后端的问题响应统一是 {error: {code, message, …}}；代理或网关则可能回一整页 HTML。 */
function problemFromBody(body: unknown, status: number, fallback: string): Error {
  if (typeof body === "object" && body !== null && "error" in body) {
    const problem = body.error;
    if (
      typeof problem === "object" &&
      problem !== null &&
      "message" in problem &&
      typeof problem.message === "string"
    ) {
      return new Error(problem.message);
    }
  }
  return new Error(fallback + " 返回 " + status);
}

/**
 * 上传失败（整批一个都没入库）时，后端仍会把逐文件原因放进 error.detail.skipped。
 *
 * 为什么单独一个错误类型：「没有文件成功入库」这句话没有可行动的信息——用户不知道该改哪个
 * 文件。把 skipped 带出来，交件台就能把原因摊回对应的那一行。
 */
export class UploadRejectedError extends Error {
  readonly skipped: { name: string; reason: string }[];

  constructor(message: string, skipped: { name: string; reason: string }[]) {
    super(message);
    this.name = "UploadRejectedError";
    this.skipped = skipped;
  }
}

/** 从错误体里取出 error.detail.skipped（形状不对就当没有，绝不因此抛错）。 */
function skippedFromBody(body: unknown): { name: string; reason: string }[] {
  if (typeof body !== "object" || body === null || !("error" in body)) return [];
  const problem = body.error;
  if (typeof problem !== "object" || problem === null || !("detail" in problem)) return [];
  const detail = problem.detail;
  if (typeof detail !== "object" || detail === null || !("skipped" in detail)) return [];
  const rows = detail.skipped;
  if (!Array.isArray(rows)) return [];
  const skipped: { name: string; reason: string }[] = [];
  for (const row of rows) {
    if (typeof row !== "object" || row === null || !("name" in row) || !("reason" in row)) continue;
    if (typeof row.name === "string" && typeof row.reason === "string") {
      skipped.push({ name: row.name, reason: row.reason });
    }
  }
  return skipped;
}

async function readError(response: Response, fallback: string): Promise<Error> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // 非 JSON 错误页也保留 HTTP 状态：那是唯一能拿到的诊断信息。
  }
  return problemFromBody(payload, response.status, fallback);
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

async function patchJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "PATCH",
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
  const [detail, pages, elements] = await Promise.all([
    getJson<WireVersionDetail>(base),
    getJson<PagesResponse>(base + "/pages"),
    getJson<ElementsResponse>(base + "/elements"),
  ]);
  const blocksByPage: Record<string, WireBlock[]> = {};
  for (const element of elements.elements) {
    const list = blocksByPage[String(element.page_no)];
    if (list === undefined) blocksByPage[String(element.page_no)] = [element];
    else list.push(element);
  }
  const latestRun = detail.parse_runs[0];
  return {
    pdfUrl: base + "/file",
    projectId: detail.project_id,
    pages: pages.pages,
    blocksByPage,
    parseStatus: latestRun?.status ?? null,
    parseError:
      latestRun?.status === "failed"
        ? (latestRun.error_message ?? latestRun.error_code ?? "解析失败")
        : null,
    parseTier: latestRun?.tier ?? null,
    parseOcrMode: latestRun?.ocr_mode ?? null,
  };
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

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/* ---------------------------------------------------------------------------
 * 项目与文件：列表页、文件管理页与工作台的项目入口。
 * ------------------------------------------------------------------------- */

export async function listProjects(keyword?: string): Promise<WireProject[]> {
  // 页面在本地做筛选和概览统计，不能把后端默认的前 50 条当成全部项目。
  const query = new URLSearchParams({ limit: "100" });
  if (keyword?.trim()) query.set("keyword", keyword.trim());
  const items: WireProject[] = [];
  for (;;) {
    query.set("offset", String(items.length));
    const page = await getJson<{ items: WireProject[]; limit: number }>("/api/v1/projects?" + query);
    items.push(...page.items);
    if (page.items.length === 0 || page.items.length < page.limit) return items;
  }
}

export async function createProject(input: {
  name: string;
  project_no?: string | null;
  owner?: string | null;
}): Promise<WireProject> {
  return postJson<WireProject>("/api/v1/projects", input);
}

export async function loadProject(projectId: number): Promise<WireProjectDetail> {
  return getJson<WireProjectDetail>("/api/v1/projects/" + projectId);
}

export interface UploadOptions {
  tier: ParseTier | "";
  ocrMode: "auto" | "txt" | "ocr" | "";
  autoParse: boolean;
  /** 不传时由后端按扩展名推断（清单/图纸/其余）。 */
  role?: FileRole | null;
}

/**
 * 上传一批文件。
 *
 * 不用 fetch 的 JSON 通道：后端收的是 multipart，且同一个字段名 files 可以重复出现，
 * 所以直接交给 FormData——浏览器会自己算 boundary，手拼 multipart 只会引入分号与
 * CRLF 的边界 bug（后端也按标准解析）。
 *
 * 也不用 fetch：fetch 至今拿不到请求体的上传进度（只有响应体能读流），而交件台要显示
 * 「传到哪了」——一份标书几百兆，没有进度的等待看起来就是卡死。XHR 的 upload.onprogress
 * 是唯一能拿到已发送字节数的通道，其余行为（multipart、错误体解析）与 fetch 版一致。
 */
export async function uploadProjectFiles(
  projectId: number,
  files: readonly File[],
  options: UploadOptions,
  /** ZIP 归档走独立字段：后端会解压后逐个入库，混在 files 里只会被当成一个不参与解析的文件。 */
  archive: File | null = null,
  /** 已发送比例（0~1）。只在浏览器能算出总长度时回调，取不到就不报数。 */
  onProgress?: (ratio: number) => void,
): Promise<UploadResult> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  if (archive !== null) form.append("archive", archive);
  form.append("auto_parse", String(options.autoParse));
  // 默认选择省略字段，由服务端在创建任务时冻结配置中心的当前值。
  if (options.tier) form.append("tier", options.tier);
  if (options.ocrMode) form.append("ocr_mode", options.ocrMode);
  if (options.role) form.append("role", options.role);

  return await new Promise<UploadResult>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/v1/projects/" + projectId + "/files");
    // responseType=json 让浏览器自己解：成功分支直接是 UploadResult，
    // 失败分支也能走同一套 {error:{message}} 解析。
    request.responseType = "json";
    request.upload.addEventListener("progress", (event) => {
      if (onProgress === undefined || !event.lengthComputable || event.total <= 0) return;
      onProgress(event.loaded / event.total);
    });
    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        resolve(request.response as UploadResult);
        return;
      }
      const problem = problemFromBody(request.response, request.status, "上传失败");
      const skipped = skippedFromBody(request.response);
      reject(skipped.length > 0 ? new UploadRejectedError(problem.message, skipped) : problem);
    });
    request.addEventListener("error", () => reject(new Error("上传失败：网络中断")));
    request.addEventListener("abort", () => reject(new Error("上传已取消")));
    request.send(form);
  });
}

export async function loadJob(jobId: string): Promise<JobResponse> {
  return getJson<JobResponse>("/api/v1/jobs/" + jobId);
}

/** 改文件元数据（显示名 / 角色 / 排序）。后端 PATCH 只改传了的字段。 */
export async function patchProjectFile(
  projectId: number,
  fileId: number,
  patch: { display_name?: string; role?: FileRole; sort_no?: number },
): Promise<unknown> {
  return patchJson("/api/v1/projects/" + projectId + "/files/" + fileId, patch);
}

export async function deleteProjectFile(projectId: number, fileId: number): Promise<void> {
  const response = await fetch("/api/v1/projects/" + projectId + "/files/" + fileId, {
    method: "DELETE",
  });
  if (!response.ok) throw await readError(response, "删除文件失败");
}

/** 对已有版本重跑解析。force=true 表示即使已有解析结果也重跑。 */
export async function parseVersion(
  versionId: number,
  options: { tier: ParseTier; ocrMode: "auto" | "txt" | "ocr"; force?: boolean; reason?: string },
): Promise<{ job_id: string }> {
  return postJson<{ job_id: string }>("/api/v1/versions/" + versionId + "/parse", {
    tier: options.tier,
    ocr_mode: options.ocrMode,
    force: options.force ?? false,
    reason: options.reason ?? null,
  });
}

/** 章节树：解析产出的标题层级。没有解析结果时后端回空数组，不是错误。 */
export async function loadOutline(versionId: number): Promise<WireOutlineItem[]> {
  const data = await getJson<{ run_id: number | null; items: WireOutlineItem[] }>(
    "/api/v1/versions/" + versionId + "/outline",
  );
  return data.items;
}

/** 重新生成解析批次，既有报告继续绑定原批次，后续分析使用新批次。 */
export async function reparseVersion(
  versionId: number,
  options: { tier: ParseTier; ocrMode: "auto" | "txt" | "ocr"; reason: string },
): Promise<{ job_id: string }> {
  return postJson<{ job_id: string }>("/api/v1/versions/" + versionId + "/reparse", {
    tier: options.tier,
    ocr_mode: options.ocrMode,
    force: true,
    reason: options.reason,
  });
}
