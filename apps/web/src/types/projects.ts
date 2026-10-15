/**
 * 项目与文件的接口数据类型。字段名与后端逐字一致（snake_case），理由同 types/workbench.ts：
 * 这些类型是线格式的镜像，改了名后端变更就不会报错，只会在运行时静默变 undefined。
 */

/** `GET /projects` 的一条；`GET /projects/{id}` 在此之上多 files 与 lots。 */
export interface WireProject {
  id: number;
  company_id: number;
  name: string;
  project_no: string | null;
  owner: string | null;
  status: string;
  created_at: string;
  /** 仅列表接口带：项目下的文件数（软删除的不算）。 */
  file_count?: number;
  /**
   * 仅列表接口带：项目下「转换或解析失败」的文件数。
   * 卷宗脊要用它报警——只有待复核数的话，坏掉的项目会伪装成「没有待办」。
   */
  failed_count?: number;
  /**
   * 仅列表接口带：建项目、文件入库、任务状态更新三者里最晚的一个。
   * 列表页的「最近活动」列要它——只拿 created_at 的话，三个月前建、昨天还在跑的
   * 项目看上去像没人动过，列表也就答不出「哪个项目还有活」。
   */
  last_activity_at?: string;
}

/** 文件在项目里的角色；决定它参不参与解析（见后端 project_files.py 的 _PARSEABLE_ROLES）。 */
export type FileRole = "main" | "clarification" | "addendum" | "boq" | "drawing" | "format" | "other";

export const FILE_ROLE_LABELS: Record<FileRole, string> = {
  main: "主文件",
  clarification: "澄清",
  addendum: "补遗",
  boq: "清单",
  drawing: "图纸",
  format: "格式",
  other: "其它",
};

/** 解析档位；与后端 ParseRequest.tier 一致。 */
export type ParseTier = "flash" | "basic" | "standard" | "advanced";

/** OCR 模式；与后端 parse 接口的 ocr_mode 一致。 */
export type OcrMode = "auto" | "txt" | "ocr";

/** `GET /projects/{id}` 的 files[] 一条。 */
export interface WireProjectFile {
  project_file_id: number;
  project_id: number;
  /** 转换完成后才有；还没转换时是 null，此时工作台打不开这个文件。 */
  version_id: number | null;
  role: string;
  display_name: string;
  is_parseable: boolean;
  replaces_id: number | null;
  sort_no: number;
  created_at: string;
  sha256: string;
  mime: string | null;
  size_bytes: number;
  page_count: number | null;
  /** 最近一次解析的状态：null 表示还没跑过解析。 */
  parse_status: string | null;
  /**
   * 最近一次解析用的档位与 OCR 模式（parse_run.tier 与 config_snapshot.ocr_mode）。
   * 重新解析要沿用它们，否则文件管理页发出的重新解析会把 advanced / ocr 静默降回默认档。
   */
  parse_tier: ParseTier | null;
  parse_ocr_mode: OcrMode | null;
  latest_run_id: number | null;
  /** 非 null 表示这个文件已被新版本替换（换内容走的是新增一行，不是原地改）。 */
  replaced_by_id: number | null;
  /** 转换、解析排队等阶段还没有结果行，页面必须依据任务状态继续刷新。 */
  latest_job: {
    id: string;
    status: string;
    stage: string | null;
    progress: Record<string, unknown> | null;
    error_code: string | null;
    error_message: string | null;
  } | null;
}

export interface WireProjectDetail extends WireProject {
  files: WireProjectFile[];
  lots: { id: number; code: string | null; name: string; sort_no: number }[];
}

/** `POST /projects/{id}/files` 的返回。skipped 里是被拒的文件与原因，不是错误。 */
export interface UploadResult {
  added: {
    project_file_id: number;
    display_name: string;
    role: string;
    is_parseable: boolean;
    version_id: number | null;
    job_id: string | null;
  }[];
  jobs: string[];
  skipped: { name: string; reason: string }[];
}
