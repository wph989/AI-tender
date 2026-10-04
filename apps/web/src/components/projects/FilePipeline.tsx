"use client";
import { derivePipeline, type PipelineInput, type StageState } from "@/lib/projects/pipeline";
import { Icon } from "@/components/Icon";

/** 转换、解析、抽取确有先后依赖，以连接节点表达进度，并保留文字状态。 */
export const SPINE_CLASS: Record<StageState, string> = {
  idle: "bg-slate-300", active: "bg-sky-500", done: "bg-emerald-500", failed: "bg-rose-600",
};
const TEXT_CLASS: Record<StageState, string> = {
  idle: "text-slate-400", active: "text-sky-700", done: "text-emerald-700", failed: "text-rose-700",
};
const NODE_CLASS: Record<StageState, string> = {
  idle: "border-slate-200 bg-white text-slate-300", active: "border-sky-200 bg-sky-50 text-sky-600",
  done: "border-emerald-200 bg-emerald-50 text-emerald-600", failed: "border-rose-200 bg-rose-50 text-rose-600",
};
const STATE_TEXT: Record<StageState, string> = { idle: "未开始", active: "进行中", done: "已完成", failed: "失败" };

export function FilePipeline({ file, compact = false }: { file: PipelineInput; compact?: boolean }) {
  const view = derivePipeline(file);
  const label = view.stages.map((stage) => stage.label + STATE_TEXT[stage.state]).join("，");
  if (compact) return <span className={"ml-1 h-1.5 w-1.5 shrink-0 rounded-full " + SPINE_CLASS[view.tone]} role="img" aria-label={label} title={label} />;
  return <div className="flex flex-col items-start gap-2">
    <ol className="flex items-center" aria-label={label}>
      {view.stages.map((stage, index) => <li key={stage.key} className="flex items-center">
        {index > 0 && <span aria-hidden className="mx-2 h-px w-3 bg-slate-200" />}
        <span className={"flex items-center gap-1.5 text-[10px] " + TEXT_CLASS[stage.state]} title={STATE_TEXT[stage.state]}>
          <span className={"flex h-5 w-5 items-center justify-center rounded-full border " + NODE_CLASS[stage.state]}>{stage.state === "done" ? <Icon name="check" size={11} /> : stage.state === "failed" ? <Icon name="close" size={10} /> : <span className="h-1 w-1 rounded-full bg-current" />}</span>
          {stage.label}
        </span>
      </li>)}
    </ol>
    <span className={"text-[11px] " + TEXT_CLASS[view.tone]}>{view.headline}</span>
  </div>;
}
