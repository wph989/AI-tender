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
  anchor: string;
  type: string;
  page_no: number;
  bbox: [number, number, number, number];
  text: string;
}

export interface WireEvidence {
  anchor: string;
  page_no: number;
  bbox: [number, number, number, number];
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
  machine_attempt_no: number;
  attempt_no: number;
  trigger: string;
  is_current: boolean;
  field_key: string;
  /** 仅样本数据带：真实接口的中文标签来自字段定义，不在结果里重复下发。 */
  field_label?: string;
  group_key: string;
  value_text: string;
  confidence: number;
  status: ExtractionStatus;
  evidence_count: number;
  evidence: WireEvidence[];
}