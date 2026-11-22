import type { AnalysisField, AnalysisGap, AnalysisModule, AnalysisScope } from "@/types/knowledge";

type Scope = Pick<AnalysisScope, "kind" | "lot_refs"> & { lot_ids?: number[] };

/** 标段 ID 与原文名称分开比较；不能用包含关系把 A1 误认为 A 标段。 */
export function matchesScope(scope: Scope | undefined, selected: string): boolean {
  if (!selected) return true;
  if (selected === "unknown") return !scope || scope.kind === "unknown";
  if (selected === "common") return scope?.kind === "common";
  if (!scope) return false;
  if (scope.kind === "common") return true;
  if (scope.kind !== "lots") return false;
  return selected.startsWith("id:")
    ? (scope.lot_ids ?? []).includes(Number(selected.slice(3)))
    : scope.lot_refs.includes(selected.slice(4));
}

export function unpairedFields(item: AnalysisField): boolean {
  const fields = item.output?.content["字段"];
  const values = item.output?.content["内容"];
  if (!Array.isArray(fields) || fields.length === 1) return false;
  return !fields.length || !Array.isArray(values) || fields.length !== values.length;
}

/** KV 数组按原顺序逐行对应；单个字段的多条内容保持在同一格，不拆成缺少字段的行。 */
export function keyValueRows(item: AnalysisField) {
  const fields = item.output?.content["字段"];
  const values = item.output?.content["内容"];
  if (!Array.isArray(fields) || fields.length === 1) {
    return [{ key: (Array.isArray(fields) ? fields[0] : fields) || item.field,
      value: item.output ? values : item.note || "来源已不可用，请更新分析。", contentIndex: 0 }];
  }
  const content = Array.isArray(values) ? values : values ? [values] : [];
  // 数量不符时保留全部原始项并标出缺失，不能用较短数组截掉字段或内容。
  return Array.from({ length: Math.max(fields.length, content.length, 1) }, (_, index) => ({
    key: fields[index] || "未提供字段", value: content[index], contentIndex: index,
  }));
}

export function needsAttention(item: AnalysisField, gaps: AnalysisGap[] = []): boolean {
  const record = item.record;
  return unpairedFields(item) || item.verification !== "supported"
    || record?.scope.kind === "unknown" || Boolean(record?.conflicts_in?.length)
    || gaps.some((gap) => gap.record_id === item.id && gap.code !== "incomplete_structure");
}

export function filterResults(items: AnalysisField[], options: {
  query: string; scope: string; group?: string; attention: boolean; gaps?: AnalysisGap[];
}): AnalysisField[] {
  const query = options.query.trim().toLocaleLowerCase();
  const matched = items.filter((item) => matchesScope(item.record?.scope, options.scope)
    && (!options.group || item.group === options.group)
    && (!options.attention || needsAttention(item, options.gaps))
    && (!query || [item.field, item.group, item.note, ...Object.values(item.output?.content ?? {}),
      ...item.values.map((value) => value.value)].flat().join(" ").toLocaleLowerCase().includes(query)));
  const identities = new Set(matched.map((item) => item.id));
  const byKey = new Map(items.filter((item) => item.output?.layout === "tree")
    .map((item) => [item.output!.key, item]));
  // 命中深层材料时保留祖先作为导航上下文，不把祖先计作本次筛选命中。
  for (const item of matched) {
    let parent = item.output?.parent_key;
    const visited = new Set<string>();
    while (parent && !visited.has(parent)) {
      visited.add(parent);
      const ancestor = byKey.get(parent);
      if (!ancestor) break;
      identities.add(ancestor.id);
      parent = ancestor.output?.parent_key;
    }
  }
  const direct = new Set(matched.map((item) => item.id));
  return items.filter((item) => identities.has(item.id))
    .map((item) => ({ ...item, contextOnly: !direct.has(item.id) }));
}

/** 标段也是项目信息，和事实一并计数，避免遗漏报告范围。 */
export function resultCounts(modules: AnalysisModule[]) {
  const counts = { facts: 0, requirements: 0, materials: 0, relations: 0 };
  for (const item of modules.flatMap((module) => module.items)) {
    const kind = item.record?.kind;
    if (kind === "fact" || kind === "lot") counts.facts++;
    else if (kind === "requirement") counts.requirements++;
    else if (kind === "format_node") counts.materials++;
    else if (kind === "relation") counts.relations++;
  }
  return counts;
}
