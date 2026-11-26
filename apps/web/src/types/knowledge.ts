import type { ApiSchemas } from "@/types/api.generated";

export type QualityStatus = NonNullable<ApiSchemas["AnalysisModuleResponse"]["quality_status"]>;
export const QUALITY_LABELS: Record<QualityStatus, string> = {
  self_check_passed: "机器自查通过", needs_review: "结论待复核",
  needs_input: "资料待核对", unknown: "质量未记录",
};

/** 引用保留全部来源身份，避免切文件或重新解析后误用同名锚点。 */
export type Citation = ApiSchemas["AnalysisEvidenceResponse"];

export type FieldValue = ApiSchemas["KnowledgeValueResponse"];

/** 分类与列由服务端从 Skill 固定，正文由 Agent 综合生成，引用单独绑定。 */
export interface AnalysisOutput {
  title_column?: string;
  version: string;
  layout: "table" | "list" | "tree";
  columns: string[];
  content: Record<string, string | string[]>;
  // 每个内容单元使用经校验的独立引用，数组位置与 content 中的条目一一对应。
  citations?: Record<string, Citation[][]>;
  key: string;
  parent_key: string | null;
  node_type: "group" | "section" | null;
}

/** 问答展示 values，专题记录生成 output；两者共用引用身份以支持原文定位。 */
export type AnalysisField = ApiSchemas["KnowledgeItemResponse"] & {
  output?: AnalysisOutput;
  // 展示保留业务身份；范围、修订和筛选不能从归纳文字中猜测。
  record?: ModuleRecord | BusinessRecord;
  contextOnly?: boolean;
};

/** 接口字段直接派生自OpenAPI，空值与可选字段随服务端契约检查。 */
export type KnowledgeSource = ApiSchemas["KnowledgeSourceResponse"];
export type KnowledgeCollection = ApiSchemas["CollectionResponse"];

/** 专题界面只增加正文加载状态；接口字段直接跟随生成契约。 */
export type AnalysisModule = ApiSchemas["AnalysisModuleResponse"] & {
  items: AnalysisField[];
  records_loading?: boolean;
  records_error?: string;
  records_version?: string;
};

export type AnalysisReportDetail = ApiSchemas["AnalysisReportResponse"];

/** 独立记录读取完成后补上展示条目，不再维护另一套报告字段。 */
export type AnalysisReport = Omit<AnalysisReportDetail, "modules"> & {
  modules: AnalysisModule[];
};

export type AnalysisScope = ApiSchemas["AnalysisScopeResponse"];
export type BusinessRecord = ApiSchemas["AnalysisRecordResponse"];
export type ModuleRecord = ApiSchemas["AnalysisModuleRecordResponse"];
export type ModuleRecords = ApiSchemas["ModuleRecordsResponse"];
export type ReportRecords = ApiSchemas["ReportRecordsResponse"];
export type AnalysisGap = ApiSchemas["AnalysisGapResponse"];
export type AnalysisDataSnapshot = ApiSchemas["AnalysisDataResponse"];
export type AnalysisContext = ApiSchemas["AnalysisContextResponse"];

export type AnalysisStatus = ApiSchemas["AnalysisStatusResponse"];
export type KnowledgeAnswer = ApiSchemas["KnowledgeAnswerResponse"];

export const PURPOSE_LABELS: Record<string, string> = {
  tender: "招标材料", company: "企业资料", history: "历史标书", reference: "参考资料",
};
export const STATE_LABELS: Record<string, string> = {
  waiting: "等待文件就绪", pending: "排队中", processing: "文件处理中", running: "分析中",
  ready: "原文已就绪", completed: "已完成", partial: "部分完成", failed: "处理失败",
  canceled: "已取消", unsupported: "格式暂不支持解析",
};
/** 报告与模块仍会继续变化的终态之外的状态；轮询与"进行中"按钮共用，避免各处各写一份。 */
export const ACTIVE_STATUSES = ["waiting", "pending", "running"];

export function isActive(status?: string | null): boolean {
  return status != null && ACTIVE_STATUSES.includes(status);
}
