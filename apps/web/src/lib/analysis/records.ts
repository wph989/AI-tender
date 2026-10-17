import type { AnalysisField, ModuleRecords } from "@/types/knowledge";

/** 从独立 JSON 组装界面，分类和列使用冻结 Skill，原文仅用于定位。 */
export function recordItems(data: ModuleRecords): AnalysisField[] {
  return data.records.flatMap((record) => {
    const citations = record.evidence_ids.map((id) => data.evidence[id]);
    // 修订双方或条件引用缺失时整条隐藏，不能仅凭剩余证据显示完整结论。
    if (!citations.length || citations.some((ref) => !ref)) return [];
    const resolved = citations.filter((ref) => ref !== undefined);
    const section = data.output_schema.sections.find((item) => item.title === record.group)
      ?? data.output_schema.sections.find((item) => item.title === "*");
    if (!section || !record.content) throw new Error("专题结果的展示格式不完整，请重试");
    const scope = record.scope.kind === "common" ? "公共要求"
      : record.scope.kind === "lots" ? record.scope.lot_refs.join("、") : "归属待确认";
    return [{
      id: record.id, field: record.title, group: record.group, sort_order: record.sort_order,
      values: [{ value: record.text, citations: resolved }], verification: record.verification,
      note: "适用范围：" + scope + (record.structuring === "partial" ? "；部分条件待核对" : ""),
      output: {
        version: data.output_schema.version, layout: section.layout, columns: section.columns,
        key: record.key, content: record.content, parent_key: record.parent_key ?? null,
        node_type: record.node_type ?? null,
      },
    }];
  });
}
