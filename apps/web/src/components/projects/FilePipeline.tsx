"use client";

/**
 * 流水线轨迹：转换 → 解析 → 抽取。
 *
 * 这是全站的签名元素，也是这个界面里唯一带顺序的图形。它成立的前提是
 * 「顺序真的是信息」——三个阶段确实有先后依赖（见 worker/dispatch.py 的 STREAMS），
 * 所以用三段色块表示进度是编码事实，而不是给界面加编号。
 *
 * 为什么不用一个彩色 badge 写完「已完成」：badge 只能说结论，说不出「卡在哪一步」。
 * 文件卡在解析时，用户需要知道的是该等还是该重跑。
 *
 * 为什么色块下面还要写字：色块对色觉障碍用户等于不存在。颜色是给扫视用的，
 * 文字是给确认用的，两者不能互相替代。
 */

import { derivePipeline, type PipelineInput, type StageState } from "@/lib/projects/pipeline";

/** 卷宗脊：列表行最左侧那道 3px 竖色条，颜色即流水线状态（见 globals.css 的说明）。 */
export const SPINE_CLASS: Record<StageState, string> = {
  idle: "bg-slate-300",
  active: "bg-amber-400",
  done: "bg-slate-900",
  failed: "bg-rose-600",
};

const SEGMENT_CLASS: Record<StageState, string> = {
  idle: "bg-slate-300",
  active: "bg-amber-400 animate-pulse",
  done: "bg-slate-900",
  failed: "bg-rose-600",
};

const TEXT_CLASS: Record<StageState, string> = {
  idle: "text-slate-500",
  active: "text-amber-700",
  done: "text-slate-600",
  failed: "text-rose-700",
};

const STATE_TEXT: Record<StageState, string> = {
  idle: "未开始",
  active: "进行中",
  done: "已完成",
  failed: "失败",
};

interface Props {
  file: PipelineInput;
  /** 紧凑档：只出色块，文字交给调用方排版（工作台的文件切换条里用）。 */
  compact?: boolean;
}

export function FilePipeline({ file, compact = false }: Props) {
  const view = derivePipeline(file);
  const ariaLabel =
    "流水线：" + view.stages.map((stage) => `${stage.label}${STATE_TEXT[stage.state]}`).join("，");

  if (compact) {
    return (
      <ol className="flex items-center gap-1" aria-label={ariaLabel}>
        {view.stages.map((stage) => (
          <li
            key={stage.key}
            title={`${stage.label}：${STATE_TEXT[stage.state]}`}
            className={"h-[7px] w-[14px] " + SEGMENT_CLASS[stage.state]}
          />
        ))}
      </ol>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <ol className="flex items-start" aria-label={ariaLabel}>
        {view.stages.map((stage, index) => (
          <li key={stage.key} className="flex items-start">
            {/* 阶段之间的细线：没有它，三段色块看起来是三个并列的开关而不是一条流程 */}
            {index > 0 && <span aria-hidden className="mt-[4px] h-px w-3 bg-slate-300" />}
            <span className="flex w-9 flex-col items-center gap-1">
              <span
                title={`${stage.label}：${STATE_TEXT[stage.state]}`}
                className={"mt-[1px] h-[7px] w-[7px] " + SEGMENT_CLASS[stage.state]}
              />
              <span className={"text-[11px] leading-none " + TEXT_CLASS[stage.state]}>
                {stage.label}
              </span>
            </span>
          </li>
        ))}
      </ol>
      <span className={"whitespace-nowrap text-[13px] leading-5 " + TEXT_CLASS[view.tone]}>
        {view.headline}
      </span>
    </div>
  );
}
