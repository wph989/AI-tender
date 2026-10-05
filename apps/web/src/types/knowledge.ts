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

export interface AnalysisItem {
  id: string;
  kind: "fact" | "judgment" | "suggestion" | "conflict" | "insufficient";
  title: string;
  text: string;
  presentation: "paragraph" | "list" | "table";
  cells: Record<string, string>;
  citations: Citation[];
  verification: string;
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
  items: AnalysisItem[];
  error_message: string | null;
}

export interface AnalysisReport {
  id: number;
  status: string;
  category: string;
  topics: string[];
  created_at: string;
  stale: boolean;
  error_message: string | null;
  modules: AnalysisModule[];
  coverage: {
    partial?: boolean;
    scanned_blocks?: number;
    total_blocks?: number;
    files?: { source_id: number; name: string; state: string }[];
  };
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
  items: AnalysisItem[];
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
