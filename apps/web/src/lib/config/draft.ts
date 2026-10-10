/**
 * 配置中心的纯逻辑：分层分组、草稿 → 补丁转换、文案口径。
 *
 * 放在 lib 里而不是组件里，是为了让"提交什么值"这件事可以被单测逐条验证：
 * 配置写错类型会直接改变线上解析结果，比样式错位严重得多。
 */

import type { ConfigItem, ConfigLayer, ConfigValueType } from "@/types/config";

export const LAYERS: readonly ConfigLayer[] = ["L1", "L2", "L3"] as const;

export const LAYER_LABELS: Record<ConfigLayer, string> = {
  L1: "L1 运行参数",
  L2: "L2 解析配置",
  L3: "L3 抽取配置",
};

export const LAYER_HINTS: Record<ConfigLayer, string> = {
  L1: "立即生效：只影响并发与超时，不改变解析与抽取结果。",
  L2: "新任务生效：会改变解析产物，保存后是草稿，需回归门禁 + 逐条确认影响。",
  L3: "新任务生效：会改变抽取结果，保存后是草稿，需回归门禁 + 逐条确认影响。",
};

export const RELEASE_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  active: "生效中",
  archived: "已归档",
  rolled_back: "已回滚",
};

export const IMPACT_KIND_LABELS: Record<string, string> = {
  config_changed: "配置项变更",
  field_def_changed: "字段定义变更",
  field_removed: "字段删除",
  regression_failure: "回归失败项",
};

export const BLOCKER_LABELS: Record<string, string> = {
  impact_not_acknowledged: "变更影响清单还有未确认项",
  hallucination_rate_not_zero: "幻觉率不为 0",
  anchor_404_not_zero: "证据反查 404 率不为 0",
  pass_rate_below_baseline: "回归集通过率低于当前生效版本",
};

export const SOFT_BREACH_LABELS: Record<string, string> = {
  first_pass_rate_drop_over_2pp: "首次通过率较当前版本下降超过 2 个百分点",
};

export function releaseStatusLabel(status: string): string {
  return RELEASE_STATUS_LABELS[status] ?? status;
}

export function impactKindLabel(kind: string): string {
  return IMPACT_KIND_LABELS[kind] ?? kind;
}

export function blockerLabel(code: string): string {
  return BLOCKER_LABELS[code] ?? SOFT_BREACH_LABELS[code] ?? code;
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
      return { error: key + " 只能是 true / false" };
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
 * "没改的不提交"不是优化，而是正确性要求：L2/L3 的补丁只要带上一个 key
 * 就会把该版本送进门禁流程，噪声会让影响清单里出现没人真正改过的条目。
 */
export function buildPatch(
  items: ConfigItem[],
  drafts: Record<string, string>,
): PatchResult {
  const patch: Record<string, unknown> = {};
  const errors: string[] = [];
  for (const item of items) {
    if (!(item.key in drafts)) continue;
    const parsed = parseValue(
      item.key,
      item.value_type,
      drafts[item.key] ?? "",
    );
    if (parsed.error !== undefined) {
      errors.push(parsed.error);
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
