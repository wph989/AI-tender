/**
 * 工作台用到的接口数据类型。字段名与后端接口**逐字一致**（snake_case）。
 *
 * 为什么不在这里改成 camelCase：这些类型是线格式的镜像。一旦重命名，
 * 后端改字段名时前端不会报错，只会在运行时拿到 undefined——那是最难查的一类问题。
 * 内部模型（lib/coords/page.ts 的 PageGeometry）继续用 camelCase，
 * 两侧的转换只允许出现在 lib/api/wire.ts 一处。
 */

export interface WirePageMeta {
  page_no: number;
  width_pt: number;
  height_pt: number;
  rotation: number;
  has_text_layer: boolean;
}

export interface WireBlock {
  id?: number;
  parent_id?: number | null;
  anchor: string;
  type: string;
  level?: number | null;
  page_no: number;
  bbox: [number, number, number, number] | null;
  text: string;
  source?: string;
  continues_prev?: boolean;
}

export interface WireEvidence {
  anchor: string;
  page_no: number;
  bbox: [number, number, number, number] | null;
  char_start: number;
  char_end: number;
  quote: string;
  quote_source: string;
  match_type: string;
}

/** 与 extraction.status 的库内枚举一致（见 docs/设计/03 表结构）。 */
export type ExtractionStatus =
  | "auto"
  | "need_review"
  | "verified"
  | "rejected"
  | "conflict"
  | "not_found";

export interface WireExtraction {
  id: number;
  instance_id: number;
  /** 老版本静态样本没有 run_id；真实接口会显式返回 number 或 null。 */
  run_id?: number | null;
  machine_attempt_no: number | null;
  attempt_no: number;
  trigger: string;
  is_current: boolean;
  field_key: string;
  /** 仅样本数据带：真实接口的中文标签来自字段定义，不在结果里重复下发。 */
  field_label?: string;
  group_key: string;
  value?: unknown;
  value_text: string;
  lot_id?: number | null;
  lot_code?: string | null;
  confidence: number;
  status: ExtractionStatus;
  strategy?: string;
  evidence_count: number;
  evidence: WireEvidence[];
}

export interface WireAttempt extends WireExtraction {
  hint?: string | null;
  review_action?: string | null;
  superseded_by_id?: number | null;
  created_at?: string;
}

/** 解析运行（版本详情里带回，用于解释结果来自哪一次解析）。 */
export interface WireParseRun {
  id: number;
  status: string;
  tier: string;
  /** 最近一次解析用的 OCR 模式；重新解析要沿用它，否则 `ocr` 的文件会被静默降回 `auto`。 */
  ocr_mode?: string | null;
  created_at: string;
  /** 失败原因只在失败时有：工作台的失败态要直接说出来，而不是让用户去翻日志。 */
  error_code?: string | null;
  error_message?: string | null;
}

/** 章节树节点（`GET /versions/{vid}/outline`，见 docs/设计/06 第 2 节的 OutlineNav）。 */
export interface WireOutlineItem {
  element_id: number;
  anchor: string;
  page_no: number;
  /** 标题层级；后端不改层级也不补缺失父节点，拿到什么画什么（见 application/extraction.py）。 */
  level: number | null;
  text: string;
  children: WireOutlineItem[];
}

/**
 * 最近一次抽取任务（`GET /versions/{vid}` 的 latest_extraction_job）。
 *
 * 为什么取最近一条而不是历史：界面上要回答的是「这一次为什么一条结果都没有」，
 * 历史任务对用户没有意义（见后端 api/versions.py 的 get_version）。
 */
export interface WireExtractionJob {
  status: string;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  finished_at?: string | null;
}

/** `GET /versions/{vid}` 的版本详情；project_id 是项目级动作（导出、冲突）的定位键。 */
export interface WireVersionDetail {
  id: number;
  project_id: number | null;
  page_count: number | null;
  parse_runs: WireParseRun[];
  /** null = 从没排过抽取；旧接口不带这个字段时按 null 处理。 */
  latest_extraction_job?: WireExtractionJob | null;
}

/** 跨文件冲突的候选项：每个候选来自一份文件的某一条尝试。 */
export interface WireConflictCandidate {
  id: number;
  version_id: number;
  value_text: string;
  confidence: number;
  status: string;
  display_name: string;
  role: string;
  anchor: string | null;
  page_no: number | null;
  quote: string | null;
}

/** `GET /projects/{id}/conflicts` 的一条冲突。 */
export interface WireConflict {
  id: number;
  field_key: string;
  field_label: string;
  lot_id: number | null;
  candidate_ids: number[];
  candidates: WireConflictCandidate[];
  resolved_id: number | null;
  status: string;
  created_at: string;
}