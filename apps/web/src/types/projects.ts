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
  /** 仅列表接口带：项目下所有文件的待复核 + 冲突条数。 */
  review_count?: number;
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
  latest_run_id: number | null;
  /** 非 null 表示这个文件已被新版本替换（换内容走的是新增一行，不是原地改）。 */
  replaced_by_id: number | null;
  /** 抽取结果条数（只算 is_current 的尝试）。 */
  extraction_count: number;
  /** 其中待复核 + 冲突的条数；列表页要拿它当「还有多少要处理」的唯一口径。 */
  review_count: number;
  /**
   * 其中已确认（verified）的条数。重新解析前的二次确认要列出「将失效的已确认结果数量」
   * （见 docs/质量/09 第 5.2 节），所以列表页必须拿得到它。
   */
  confirmed_count: number;
  /** 最近一次抽取任务的状态（pending/running/completed/partial/failed）；null = 还没排过队。 */
  extraction_status: string | null;
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