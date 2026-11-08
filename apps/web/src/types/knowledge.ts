/** 引用保留全部来源身份，避免切文件或重新解析后误用同名锚点。 */
export interface Citation {
  source_id: number;
  collection_id: number;
  project_id: number;
  project_file_id: number;
  version_id: number;
  parse_run_id: number;
  element_id: number;
  anchor: string;
  page_no: number;
  bbox: [number, number, number, number] | null;
  file_name: string;
  purpose: string;
  quote: string;
}

export interface FieldValue {
  value: string;
  citations: Citation[];
}

/** 分类与列由服务端从 Skill 固定，正文由 Agent 综合生成，引用单独绑定。 */
export interface AnalysisOutput {
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

/** 报告条目沿用历史身份，新增专题 output；问答和历史报告仍使用 values 投影。 */
export interface AnalysisField {
  id: string;
  field: string;
  group: string;
  sort_order: number;
  values: FieldValue[];
  note: string;
  verification: string;
  module_keys?: string[];
  output?: AnalysisOutput;
  // 展示保留业务身份；范围、修订和筛选不能从归纳文字中猜测。
  record?: ModuleRecord | BusinessRecord;
  contextOnly?: boolean;
}

export interface KnowledgeSource {
  source_id: number;
  collection_id: number;
  project_id: number;
  project_file_id: number;
  file_name: string;
  version_id: number | null;
  parse_run_id: number | null;
  state: string;
  purpose: string;
  index_status: string | null;
  index_error: string | null;
  error_message: string | null;
  embedding_model_id: number | null;
  semantic_ready?: boolean;
  needs_reindex?: boolean;
}

export interface KnowledgeCollection {
  id: number;
  name: string;
  purpose: string;
  upload_project_id: number;
  is_project: boolean;
  file_count: number;
  sources?: KnowledgeSource[];
  embedding_configured?: boolean;
  embedding_model?: string | null;
}

export interface AnalysisModule {
  id: number;
  module_key: string;
  title: string;
  status: string;
  items: AnalysisField[];
  error_message: string | null;
  runs?: AgentRun[];
  research_summary?: string;
  research_gaps?: { key: string; detail: string }[];
  records_loading?: boolean;
  records_error?: string;
  progress?: TopicProgress;
}

export interface TopicProgress {
  phase?: "research" | "synthesis" | "review" | "completed" | "partial";
  audit_round: number;
  topics: {
    topic: string; title: string; scope: Omit<AnalysisScope, "lot_ids">;
    status: "pending" | "researching" | "ready" | "blocked" | "needs_review";
    checks: string[]; checked: string[]; detail: string;
    tasks: { detail: string; status: "pending" | "resolved" | "blocked" }[];
  }[];
}

export interface AgentRun {
  id: number;
  attempt: number;
  status: string;
  thread_id: string;
  started_at: string | null;
  deadline_at: string | null;
  finished_at: string | null;
  model_calls: number;
  tool_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  limits: { max_model_calls: number; max_tool_calls: number; timeout_seconds: number; max_output_tokens: number };
  error_message: string | null;
}

export interface AnalysisReport {
  canceling?: boolean;
  id: number;
  status: string;
  category: string;
  topics: string[];
  created_at: string;
  finished_at?: string | null;
  data_schema_version?: string | null;
  stale: boolean;
  runtime_retired?: boolean;
  error_message: string | null;
  modules: AnalysisModule[];
  runtime_version?: string;
  summary?: AnalysisField[];
  coverage: {
    mode?: string;
    partial?: boolean;
    scanned_blocks?: number;
    total_blocks?: number;
    files?: { source_id: number; name: string; state: string }[];
  };
}

export interface AnalysisScope {
  kind: "common" | "lots" | "unknown";
  lot_ids: number[];
  lot_refs: string[];
}

/** 正式业务记录与展示字段分离，编制任务固定快照和记录身份。 */
export interface BusinessRecord {
  review_status?: "current" | "needs_review";
  id: string;
  key: string;
  kind: "fact" | "requirement" | "lot" | "format_node" | "relation";
  title: string;
  text: string;
  content?: Record<string, string | string[]>;
  scope: AnalysisScope;
  structuring: "complete" | "partial";
  citations: Citation[];
  module_key: string;
  verification: "supported";
  group: string;
  sort_order: number;
  category: string;
  parent_id?: string | null;
  parent_key?: string | null;
  parent_path?: string[];
  node_type?: "group" | "section" | null;
  requirement_ids?: string[];
  requirement_keys?: string[];
  conditions: {
    expression: string;
    logic: "all" | "any" | "mixed" | "text";
    terms: {
      subject: string;
      operator: "=" | "!=" | ">" | ">=" | "<" | "<=" | "in" | "text";
      value: string;
      unit: string | null;
      time_basis: string | null;
    }[];
    exceptions: string[];
  };
  materials: { name: string; requirement: string }[];
  scoring: {
    max_points: string | null;
    formula: string;
    tiers: { condition: string; points: string }[];
    deductions: string[];
  } | null;
  predicate?: "supersedes" | "conflicts" | "requires" | "contains" | null;
  subject_id?: string;
  object_id?: string;
  subject_key?: string;
  object_key?: string;
  effective_status?: "active" | "unknown";
  superseded_in?: AnalysisScope[];
  conflicts_in?: AnalysisScope[];
}

/** 维度原始业务记录未解析标段目录，引用通过独立证据集合关联。 */
export interface ModuleRecord extends Omit<BusinessRecord, "citations" | "scope"> {
  review_status?: "current" | "needs_review";
  evidence_ids: string[];
  content_evidence?: Record<string, string[][]>;
  scope: Omit<AnalysisScope, "lot_ids">;
}

export interface ModuleRecords {
  progress?: TopicProgress;
  // schema_version 与 status 仅随契约透传，前端尚无版本分支；读取方不要据此推断兼容性。
  schema_version: string;
  module_key: string;
  status: string;
  records: ModuleRecord[];
  evidence: Record<string, Citation>;
  output_schema: {
    version: string;
    sections: { title: string; layout: AnalysisOutput["layout"]; columns: string[] }[];
  };
}

export interface AnalysisGap {
  code: string;
  detail: string;
  scope: AnalysisScope;
  record_id?: string;
  key?: string;
  topic?: string;
  module_key?: string;
}

export interface AnalysisCoverage {
  topic: string;
  title: string;
  status: string;
  scope: AnalysisScope;
  detail: string;
  module_key?: string;
}

export interface AnalysisDataset {
  schema_version: string;
  lots: (BusinessRecord & { lot_id: number; code: string | null; aliases: string[] })[];
  facts: BusinessRecord[];
  requirements: BusinessRecord[];
  format_nodes: BusinessRecord[];
  relations: BusinessRecord[];
  coverage: AnalysisCoverage[];
  gaps: AnalysisGap[];
  readiness: "usable" | "partial" | "unavailable";
}

export interface AnalysisDataSnapshot {
  report_id: number;
  snapshot_id: number;
  revision: number;
  schema_version: string;
  stale: boolean;
  data: AnalysisDataset;
}

export interface AnalysisContext extends Omit<AnalysisDataset, "lots" | "schema_version"> {
  schema_version: string;
  snapshot_id: number;
  purpose: "outline" | "content" | "check";
  lot_id: number | null;
  unresolved: BusinessRecord[];
  requirement_manifest: string[];
  total_requirements: number;
  next_offset: number | null;
  references: { purpose: "company" | "history"; text: string; citation: Citation }[];
  reference_warning?: string | null;
}

export interface AnalysisStatus {
  analysis_category: string | null;
  analysis_topics: string[];
  sources: KnowledgeSource[];
  reports: Pick<AnalysisReport, "id" | "status" | "created_at">[];
  categories: Record<string, string>;
  topics: Record<string, string>;
  lots: { id: number; name: string; category: string | null; topics: string[] | null }[];
}

export interface KnowledgeAnswer {
  id: number;
  status: string;
  question: string;
  items: AnalysisField[];
  error_message: string | null;
  snapshot: { mode?: string; no_evidence?: boolean; warning?: string; graph_used?: boolean };
  relations: { subject: string; predicate: string; object: string; condition: string; scope: string; citations: Citation[] }[];
}

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
