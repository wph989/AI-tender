/**
 * 结果状态、徽标样式与尝试触发方式的统一文案。
 *
 * 为什么集中维护：当前结果卡和历史尝试区必须对同一个枚举使用同一套中文名，
 * 否则用户会把「重跑」和「带提示重跑」误认为两种不同的业务动作。
 *
 * 状态的颜色也只在这里定义一次：六种状态的配色一旦分散，两种不同状态会看起来
 * 一模一样，而「这条到底要不要管」正是用户扫结果面板时最依赖的信号。
 *
 * 形态上刻意不用「彩色药丸」：一列 20 张卡片各顶一个填色胶囊，眼睛会被色块带着走，
 * 反而读不到字段名。改成「小圆点 + 同色文字」，色相还在，但重量让给值本身。
 */

import type { ExtractionStatus } from "@/types/workbench";

const STATUS_LABELS: Record<ExtractionStatus, string> = {
  auto: "自动抽取",
  need_review: "待复核",
  verified: "已确认",
  rejected: "已驳回",
  conflict: "存在冲突",
  not_found: "未找到",
};

const STATUS_DOT_CLASSES: Record<ExtractionStatus, string> = {
  auto: "bg-emerald-500",
  need_review: "bg-amber-500",
  verified: "bg-sky-600",
  rejected: "bg-slate-400",
  conflict: "bg-rose-500",
  not_found: "bg-slate-400",
};

const STATUS_TEXT_CLASSES: Record<ExtractionStatus, string> = {
  auto: "text-emerald-700",
  need_review: "text-amber-700",
  verified: "text-sky-700",
  rejected: "text-slate-500",
  conflict: "text-rose-700",
  not_found: "text-slate-600",
};

/** 卡片左侧那道卷宗脊的颜色：和结果状态同一套口径。 */
const STATUS_SPINE_CLASSES: Record<ExtractionStatus, string> = {
  auto: "bg-emerald-500",
  need_review: "bg-amber-400",
  verified: "bg-sky-600",
  rejected: "bg-slate-300",
  conflict: "bg-rose-500",
  not_found: "bg-slate-300",
};

const STATUS_BADGE_CLASSES: Record<ExtractionStatus, string> = {
  auto: "border-emerald-200 bg-emerald-50 text-emerald-700",
  need_review: "border-amber-200 bg-amber-50 text-amber-700",
  verified: "border-sky-200 bg-sky-50 text-sky-700",
  rejected: "border-slate-200 bg-slate-100 text-slate-500",
  conflict: "border-rose-200 bg-rose-50 text-rose-700",
  not_found: "border-slate-300 bg-slate-100 text-slate-600",
};

const UNKNOWN_BADGE_CLASS = "border-slate-200 bg-slate-100 text-slate-600";

export function statusLabel(status: string): string {
  return STATUS_LABELS[status as ExtractionStatus] ?? status;
}

export function statusDotClass(status: string): string {
  return STATUS_DOT_CLASSES[status as ExtractionStatus] ?? "bg-slate-400";
}

export function statusTextClass(status: string): string {
  return STATUS_TEXT_CLASSES[status as ExtractionStatus] ?? "text-slate-600";
}

export function statusSpineClass(status: string): string {
  return STATUS_SPINE_CLASSES[status as ExtractionStatus] ?? "bg-slate-300";
}

/** 保留药丸形态：跨文件冲突的裁决界面需要更强的「这是一个待办」信号。 */
export function statusBadgeClass(status: string): string {
  return STATUS_BADGE_CLASSES[status as ExtractionStatus] ?? UNKNOWN_BADGE_CLASS;
}

export function triggerLabel(trigger: string): string {
  const labels: Record<string, string> = {
    first: "首次抽取",
    hinted_rerun: "带提示重跑",
    user_rerun: "重跑",
    param_rerun: "换参数重跑",
    reparse: "重新解析",
    manual_edit: "人工修正",
  };
  return labels[trigger] ?? trigger;
}

export function reviewActionLabel(action: string | null | undefined): string | null {
  if (action === undefined || action === null) return null;
  const labels: Record<string, string> = {
    confirm: "确认",
    correct: "修正",
    supplement: "人工补充",
    reject: "驳回",
  };
  return labels[action] ?? action;
}
