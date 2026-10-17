import type { AnalysisField, Citation, ModuleRecords } from "@/types/knowledge";
import { scopeLabel } from "@/lib/analysis/scope";

/** 从独立 JSON 组装界面，分类和列使用冻结 Skill，原文仅用于定位。 */
export function recordItems(data: ModuleRecords): AnalysisField[] {
  const { version, sections: declared } = data.output_schema;
  // 每条记录都会按分组找展示格式，先建索引，避免逐条线性扫描 sections。
  const sections = new Map(declared.map((section) => [section.title, section]));
  return data.records.flatMap((record) => {
    const citations: Citation[] = [];
    // 修订双方或条件引用缺失时整条隐藏，不能仅凭剩余证据显示完整结论。
    for (const id of record.evidence_ids) {
      const ref = data.evidence[id];
      if (!ref) return [];
      citations.push(ref);
    }
    if (!citations.length) return [];
    const section = sections.get(record.group) ?? sections.get("*");
    if (!section || !record.content) throw new Error("专题结果的展示格式不完整，请重试");
    const note = "适用范围：" + scopeLabel(record.scope)
      + (record.structuring === "partial" ? "；部分条件待核对" : "");
    return [{
      id: record.id, field: record.title, group: record.group, sort_order: record.sort_order,
      values: [{ value: record.text, citations }], verification: record.verification,
      note,
      output: {
        version, layout: section.layout, columns: section.columns,
        key: record.key, content: record.content, parent_key: record.parent_key ?? null,
        node_type: record.node_type ?? null,
      },
    }];
  });
}
