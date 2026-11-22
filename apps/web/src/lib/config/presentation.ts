import { OCR_MODES, PARSE_TIERS } from "@/lib/projects/parseOptions";

// 这里只维护展示名称和用途；配置清单、默认值、权限和数值范围仍由服务端决定。
const COPY: Record<string, [string, string]> = {
  "analysis.max_inflight": ["同时分析的专题数", "同一公司所有报告共用此上限。"],
  "analysis.max_model_calls": ["每个专题的模型请求上限", "每次运行累计计数，包含重试和内容摘要。"],
  "analysis.max_tool_calls": ["每个专题的工具调用上限", "限制检索、读取原文等操作的总次数。"],
  "analysis.max_evidence_blocks": ["每个专题保留的原文片段数", "限制分析时可以保留的原文依据数量。"],
  "analysis.similarity_threshold": ["检索最低相关度", "范围为 0 到 1；越高越严格，返回的材料可能越少。"],
  "analysis.max_search_results": ["每次检索最多返回的片段数", "只返回达到最低相关度的原文片段。"],
  "analysis.rate_limit_backoff_seconds": ["限流后首次等待时间（秒）", "模型服务未告知恢复时间时使用，后续等待逐次延长。"],
  "analysis.rate_limit_max_wait_seconds": ["每个专题的限流等待上限（秒）", "累计等待超过此时间后停止，可稍后继续分析。"],
  "analysis.max_subagent_retries": ["分析执行故障自动恢复次数", "专题执行发生可恢复故障时，最多自动恢复的次数。"],
  "analysis.timeout_seconds": ["每个专题的分析时限（秒）", "整个专题的累计运行时限，自动恢复不会重新计时。"],
  "analysis.context_tokens": ["分析上下文容量（Token）", "每个专题保留的材料与对话长度，达到 80% 后自动压缩。"],
  "analysis.max_output_tokens": ["单次模型输出上限（Token）", "限制每次回答的长度；Token 是模型计量文本的单位。"],
  "convert.max_inflight": ["同时转换的文件数", "限制同时转换为 PDF 的文件数量。"],
  "parse.max_inflight": ["同时处理的解析任务数", "包含解析服务中排队和执行的任务。"],
  "dispatch.interval_seconds": ["新任务派发间隔（秒）", "每隔多久检查并发送等待处理的任务。"],
  "job.poll.initial_interval_ms": ["解析进度首次查询间隔（毫秒）", "开始处理后，首次等待多久再查询进度。"],
  "job.poll.max_interval_ms": ["解析进度最长查询间隔（毫秒）", "后续查询逐渐放缓，最多间隔此时间。"],
  "job.poll.max_attempts": ["解析进度查询次数上限", "达到此次数仍未完成时，按超时处理。"],
  "job.timeout.convert_minutes": ["文件转换时限（分钟）", "单份文件转换为 PDF 的最长等待时间。"],
  "job.timeout.parse_minutes": ["文件解析时限（分钟）", "单份文件读取文字和版面的最长等待时间。"],
  "job.retry.convert_500": ["转换服务故障重试次数", "转换服务内部出错时重试，文件或参数有误时不重试。"],
  "mineru.tier": ["默认解析方式", "上传文件时未单独选择的解析方式。"],
  "mineru.ocr_mode": ["默认文字识别方式", "决定读取已有文字，还是识别扫描图片中的文字。"],
};

export function configLabel(key: string, description?: string): string {
  return COPY[key]?.[0] ?? (description || key);
}

export function configHint(key: string): string | undefined {
  return COPY[key]?.[1];
}

export function configChoiceLabel(key: string, value: string): string {
  if (key === "mineru.tier") return PARSE_TIERS.find((option) => option.value === value)?.label ?? value;
  if (key === "mineru.ocr_mode") return OCR_MODES.find((option) => option.value === value)?.label ?? value;
  return value;
}

// 展示和序列化分开，避免把中文开关或档位名称提交给后端。
export function configValueLabel(key: string, value: unknown): string {
  if (typeof value === "boolean") return value ? "开启" : "关闭";
  if (typeof value === "string") return configChoiceLabel(key, value);
  return value == null ? "—" : JSON.stringify(value);
}
