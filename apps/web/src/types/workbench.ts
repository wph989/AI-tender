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
  /** 标题层级；后端不改层级也不补缺失父节点，拿到什么画什么（见 application/document_outline.py）。 */
  level: number | null;
  text: string;
  children: WireOutlineItem[];
}

/** `GET /versions/{vid}` 的版本详情；project_id 用于返回项目分析。 */
export interface WireVersionDetail {
  id: number;
  project_id: number | null;
  page_count: number | null;
  parse_runs: WireParseRun[];
}
