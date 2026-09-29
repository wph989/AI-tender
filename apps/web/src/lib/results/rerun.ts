/**
 * 重跑按钮的展示口径（设计文档 09 第 8 节）。
 *
 * 规则由服务端下发（`GET /stats/fields` 的 `rerun_button`）：阈值属于业务规则，
 * 改阈值不应该要求前端跟着发版；前端只按三值渲染。
 *
 * 为什么默认是 show：样本不足或统计接口不可用时必须保留入口——
 * 宁可让用户多看到一个可能没用的按钮，也不要因为取数失败把功能藏掉。
 */

export type RerunButtonMode = "show" | "show_hint" | "hide";

export interface FieldStatLike {
  field_key: string;
  rerun_button: string;
}

const MODES: readonly RerunButtonMode[] = ["show", "show_hint", "hide"];

function isMode(value: string): value is RerunButtonMode {
  return (MODES as readonly string[]).includes(value);
}

/** 把统计接口的条目压成 field_key → 展示模式；未知值回落 show。 */
export function rerunModeByField(
  items: readonly FieldStatLike[],
): Record<string, RerunButtonMode> {
  const modes: Record<string, RerunButtonMode> = {};
  for (const item of items) {
    if (typeof item.field_key !== "string" || item.field_key === "") continue;
    modes[item.field_key] = typeof item.rerun_button === "string" && isMode(item.rerun_button)
      ? item.rerun_button
      : "show";
  }
  return modes;
}

export function rerunMode(modes: Record<string, RerunButtonMode>, fieldKey: string): RerunButtonMode {
  return modes[fieldKey] ?? "show";
}