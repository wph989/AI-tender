/**
 * 配置中心的纯逻辑：分层分组、草稿 → 补丁转换、文案口径。
 *
 * 放在 lib 里而不是组件里，是为了让"提交什么值"这件事可以被单测逐条验证：
 * 配置写错类型会直接改变线上解析结果，比样式错位严重得多。
 */

import type { ConfigItem, ConfigLayer, ConfigValueType } from "@/types/config";
import { configLabel } from "./presentation";

export const LAYERS: readonly ConfigLayer[] = ["L1", "L2"] as const;

// 分析预算集中到模型设置，避免在运行设置中重复编辑。
export function isModelConfig(key: string): boolean {
  return key.startsWith("analysis.");
}

export const LAYER_LABELS: Record<ConfigLayer, string> = {
  L1: "运行设置",
  L2: "文件解析设置",
};

export const LAYER_HINTS: Record<ConfigLayer, string> = {
  L1: "并发与调度设置立即生效；其他分析参数在新建报告或继续分析时使用。",
  L2: "先保存草稿，再到「版本与发布」确认影响并发布，新解析任务将使用新设置。",
};

export const RELEASE_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  active: "生效中",
  archived: "已归档",
  rolled_back: "已回滚",
};

export const IMPACT_KIND_LABELS: Record<string, string> = {
  config_changed: "配置项变更",
};

export const BLOCKER_LABELS: Record<string, string> = {
  impact_not_acknowledged: "变更影响清单还有未确认项",
};

export function releaseStatusLabel(status: string): string {
  return RELEASE_STATUS_LABELS[status] ?? status;
}

export function impactKindLabel(kind: string): string {
  return IMPACT_KIND_LABELS[kind] ?? kind;
}

export function blockerLabel(code: string): string {
  return BLOCKER_LABELS[code] ?? code;
}

export function itemsOfLayer(
  items: ConfigItem[],
  layer: ConfigLayer,
): ConfigItem[] {
  return items.filter((item) => item.layer === layer);
}

/** 输入框初值：字符串原样显示，其余走 JSON，避免数组被显示成 [object Object]。 */
export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

interface ParseResult {
  value?: unknown;
  error?: string;
}

function parseValue(
  key: string,
  valueType: ConfigValueType,
  raw: string,
): ParseResult {
  // Number("") 会变成 0；清空数值输入时应提示补填，不能静默发布零并发/零超时。
  if ((valueType === "int" || valueType === "number") && raw.trim() === "") {
    return { error: key + " 不能为空" };
  }
  if (valueType === "bool") {
    if (raw !== "true" && raw !== "false")
      return { error: key + " 请选择开启或关闭" };
    return { value: raw === "true" };
  }
  if (valueType === "int") {
    const parsed = Number(raw);
    if (!Number.isInteger(parsed)) return { error: key + " 需要整数" };
    return { value: parsed };
  }
  if (valueType === "number") {
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) return { error: key + " 需要数字" };
    return { value: parsed };
  }
  if (valueType === "json") {
    try {
      return { value: JSON.parse(raw) };
    } catch {
      return { error: key + " 不是合法 JSON" };
    }
  }
  return { value: raw };
}

function sameValue(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export interface PatchResult {
  patch: Record<string, unknown>;
  errors: string[];
}

/**
 * 草稿 → 提交补丁：没改的项不进补丁，改错类型的不进补丁并报错。
 *
 * 仅提交实际改变的项：L2 的补丁只要带上一个 key
 * 就会把该版本送进门禁流程，噪声会让影响清单里出现没人真正改过的条目。
 */
export function buildPatch(
  items: ConfigItem[],
  drafts: Record<string, string>,
): PatchResult {
  const patch: Record<string, unknown> = {};
  const errors: string[] = [];
  for (const item of items) {
    const label = configLabel(item.key, item.description);
    if (!(item.key in drafts)) continue;
    if (!item.writable) {
      errors.push(label + " 当前不可修改");
      continue;
    }
    const parsed = parseValue(
      label,
      item.value_type,
      drafts[item.key] ?? "",
    );
    if (parsed.error !== undefined) {
      errors.push(parsed.error);
      continue;
    }
    // 范围来自服务端元数据，避免前后端再次维护两套会漂移的数字。
    if (typeof parsed.value === "number" && (
      (item.minimum !== undefined && parsed.value < item.minimum) ||
      (item.maximum !== undefined && parsed.value > item.maximum)
    )) {
      errors.push(label + " 超出允许范围");
      continue;
    }
    if (item.choices && !item.choices.includes(String(parsed.value))) {
      errors.push(label + " 请选择支持的值");
      continue;
    }
    if (sameValue(parsed.value, item.value)) continue;
    patch[item.key] = parsed.value;
  }
  return { patch, errors };
}

/** 服务端 diff 的展示顺序：按 key 排序，页面刷新前后不跳动。 */
export function diffRows(
  changed: Record<string, { old: unknown; new: unknown }>,
) {
  return Object.entries(changed)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => ({ key, old: value.old, new: value.new }));
}
