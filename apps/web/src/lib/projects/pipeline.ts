/**
 * 文件流水线状态推导：把三处分散的字段（version_id / parse_status / extraction_status）
 * 归约成一条可直接渲染的轨迹。
 *
 * 为什么放在 lib 而不是组件里：这是纯映射，组件只负责画。列表页要排序、要筛「还有多少没跑完」，
 * 判据必须只有一份——同一个文件在列表里显示「已完成」、在工作台里没结果，是最难解释的一类 bug。
 */

export type StageState = "idle" | "active" | "done" | "failed";

export interface PipelineStage {
  key: "convert" | "parse" | "extract";
  label: string;
  state: StageState;
}

export interface FilePipelineView {
  stages: PipelineStage[];
  /** 一句话状态；轨迹上的色块不能替代文字，色觉障碍用户只能靠它。 */
  headline: string;
  tone: StageState;
  /** 是否需要轮询：还有阶段在跑时列表页应当自动刷新。 */
  inFlight: boolean;
}

/** 只取推导需要的字段，测试与调用方都不用造完整的接口对象。 */
export interface PipelineInput {
  is_parseable?: boolean;
  latest_job?: { status: string; stage: string | null } | null;
  version_id: number | null;
  parse_status: string | null;
  extraction_status: string | null;
  extraction_count: number;
  review_count: number;
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
  // 转换完成的标志是版本行被建出来，而不是 mime/后缀——PDF 与 Office 走的是两条实现，
  // 只有在 _finish_file_version 之后 version_id 才存在（见 worker/tasks.py）。
  const job = file.latest_job;
  const jobState = runState(job?.status ?? null);
  const convertState: StageState = file.version_id !== null ? "done"
    : file.is_parseable === false ? "idle" : jobState;

  // 提交解析后 parse_run 可能尚未创建；重解析时还可能残留上一次成功状态。
  const parseQueued = job != null && ["submitting", "parsing"].includes(job.stage ?? "");
  const parseState: StageState = file.version_id === null ? "idle"
    : parseQueued ? jobState : runState(file.parse_status);

  // 解析没完成时抽取不可能开始：把抽取显式压回 idle，
  // 否则并发的两个 job 状态会拼出「解析进行中、抽取已完成」这种不存在的画面。
  const extractionStatus = job?.stage === "extracting" ? job.status : file.extraction_status;
  // 逐字段写入和重跑都会保留已有结果，结果条数不能盖过正在运行或失败的任务。
  let extractState = runState(extractionStatus);
  if (extractionStatus === null && file.extraction_count > 0) extractState = "done";
  if (parseState !== "done") extractState = "idle";

  const stages: PipelineStage[] = [
    { key: "convert", label: "转换", state: convertState },
    { key: "parse", label: "解析", state: parseState },
    { key: "extract", label: "抽取", state: extractState },
  ];

  const tone: StageState = stages.some((stage) => stage.state === "failed")
    ? "failed"
    : stages.every((stage) => stage.state === "done")
      ? "done"
      : stages.some((stage) => stage.state === "active")
        ? "active"
        : "idle";

  return {
    stages,
    tone,
    inFlight: stages.some((stage) => stage.state === "active"),
    headline: describe(file, convertState, parseState, extractState),
  };
}

function describe(
  file: PipelineInput,
  convertState: StageState,
  parseState: StageState,
  extractState: StageState,
): string {
  if (file.is_parseable === false && file.version_id === null) return "仅归档";
  if (convertState === "active") return file.latest_job?.status === "pending" ? "排队转换" : "转换中";
  if (convertState === "failed") return file.latest_job?.status === "canceled" ? "转换已取消" : "转换失败";
  if (convertState === "idle") return "等待转换";
  if (parseState === "idle") return "等待解析";
  if (parseState === "failed") return "解析失败";
  if (parseState === "active") return file.parse_status === "pending" ? "排队解析" : "解析中";
  if (extractState === "active") {
    return file.extraction_status === "pending" ? "排队抽取" : "抽取中";
  }
  if (extractState === "failed") return "抽取失败";
  if (extractState === "idle") return "等待抽取";
  if (file.review_count > 0) return `${file.review_count} 项待复核`;
  if (file.extraction_count === 0) return "没有抽取结果";
  return "已完成";
}

/*
 * 两种重跑的可点条件。
 *
 * 为什么判据放这里而不是写在按钮的 disabled 里：文件清单与工作台失败态都要按同一套
 * 条件决定给哪个按钮，各写一份必然出现「列表页能点、工作台点不了」。
 *
 * 两者互斥：解析没成时重跑抽取一定还会失败（抽取要拿 element 当输入），
 * 此时只能重新解析；解析成了而抽取没产出，重新解析就是白付一次重建锚点的代价。
 */

/** 解析没成（失败或从没跑过）→ 只能先重新解析。 */
export function needsReparse(file: PipelineInput): boolean {
  if (file.version_id === null) return false;
  return file.parse_status === null || DEAD.has(file.parse_status);
}

/**
 * 解析成了但抽取没产出 → 该给「重跑抽取」升为主操作。
 *
 * 三种情形都算：抽取 job 失败/被取消；抽取 job 从没建过（上一版实现里表现为
 * 「没有抽取结果」）；抽取跑了却没有一条 is_current 结果。
 * 已经有结果时不给这个入口：那属于按字段补跑（项目级 rerun），不是整份重抽。
 */
export function needsExtractRerun(file: PipelineInput): boolean {
  if (file.version_id === null) return false;
  if (!DONE.has(file.parse_status ?? "")) return false;
  if (file.extraction_count > 0) return false;
  return file.extraction_status === null || DEAD.has(file.extraction_status);
}
