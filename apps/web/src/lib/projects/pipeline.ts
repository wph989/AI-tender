/** 文件只经历转换与解析；Agent 分析以项目报告为单位单独管理。 */
export type StageState = "idle" | "active" | "done" | "failed";

export interface PipelineStage {
  key: "convert" | "parse";
  label: string;
  state: StageState;
}

export interface FilePipelineView {
  stages: PipelineStage[];
  headline: string;
  tone: StageState;
  inFlight: boolean;
}

export interface PipelineInput {
  is_parseable?: boolean;
  latest_job?: { status: string; stage: string | null } | null;
  version_id: number | null;
  parse_status: string | null;
}

const DONE = new Set(["completed", "partial"]);
const DEAD = new Set(["failed", "canceled"]);

function runState(status: string | null): StageState {
  if (status === null) return "idle";
  if (DONE.has(status)) return "done";
  if (DEAD.has(status)) return "failed";
  return "active";
}

export function derivePipeline(file: PipelineInput): FilePipelineView {
  const job = file.latest_job;
  const jobState = runState(job?.status ?? null);
  const convert: StageState = file.version_id !== null ? "done"
    : file.is_parseable === false ? "idle" : jobState;
  // 重解析开始后 parse_run 可能还没创建，不能用上一次成功状态掩盖排队任务。
  const queued = job != null && ["submitting", "parsing"].includes(job.stage ?? "");
  const parse: StageState = file.version_id === null ? "idle"
    : queued ? jobState : runState(file.parse_status);
  const stages: PipelineStage[] = [
    { key: "convert", label: "转换", state: convert },
    { key: "parse", label: "解析", state: parse },
  ];
  const tone = stages.some((stage) => stage.state === "failed") ? "failed"
    : stages.every((stage) => stage.state === "done") ? "done"
      : stages.some((stage) => stage.state === "active") ? "active" : "idle";
  let headline = "已就绪";
  if (file.is_parseable === false && file.version_id === null) headline = "仅归档";
  else if (convert === "active") headline = job?.status === "pending" ? "排队转换" : "转换中";
  else if (convert === "failed") headline = job?.status === "canceled" ? "转换已取消" : "转换失败";
  else if (convert === "idle") headline = "等待转换";
  else if (parse === "idle") headline = "等待解析";
  else if (parse === "failed") headline = "解析失败";
  else if (parse === "active") headline = (queued ? job?.status : file.parse_status) === "pending" ? "排队解析" : "解析中";
  else if (file.parse_status === "partial") headline = "部分解析完成";
  return { stages, tone, inFlight: stages.some((stage) => stage.state === "active"), headline };
}
