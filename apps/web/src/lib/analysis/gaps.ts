import type { ScopeText } from "./scope";

export interface DisplayGap {
  key: string;
  detail: string;
  code?: string;
  moduleKey?: string;
  moduleTitle?: string;
  topicTitle?: string;
  scopeLabel?: string;
  scope?: ScopeText;
  recordId?: string;
}

function category(code = "") {
  if (["unresolved_reference", "missing_source"].includes(code)) return "待补充材料";
  if (["scope_unknown", "lot_catalog_unknown"].includes(code)) return "适用范围待确认";
  if (code === "conflict") return "条款冲突";
  if (["module_incomplete", "coverage_pending", "coverage_unchecked", "search_exhausted"].includes(code)) return "分析尚未完成";
  if (code === "incomplete_structure") return "结构化待完善";
  return "条款内容待核对";
}

/** 同专题、主题、范围和事项才合组，重复说明只展示一次；不同范围不得相互覆盖。 */
export function groupGaps(gaps: DisplayGap[]) {
  const groups = new Map<string, { key: string; category: string; gaps: DisplayGap[] }>();
  for (const gap of gaps) {
    const label = category(gap.code);
    // 展示名称可能相同或尚未解析；身份使用原始范围，并忽略集合的排列顺序。
    const scope = gap.scope ? [gap.scope.kind,
      [...new Set(gap.scope.lot_ids ?? [])].sort((a, b) => a - b),
      [...new Set(gap.scope.lot_refs)].sort()] : gap.scopeLabel;
    const key = JSON.stringify([label, gap.moduleKey, gap.moduleTitle, gap.topicTitle,
      scope, gap.recordId]);
    const group = groups.get(key) ?? { key, category: label, gaps: [] };
    if (!group.gaps.some((entry) => entry.detail === gap.detail)) group.gaps.push(gap);
    groups.set(key, group);
  }
  const order = ["条款冲突", "适用范围待确认", "待补充材料", "条款内容待核对", "分析尚未完成", "结构化待完善"];
  return [...groups.values()].sort((a, b) => order.indexOf(a.category) - order.indexOf(b.category));
}
