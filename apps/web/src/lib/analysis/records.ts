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
    let contentCitations: Record<string, Citation[][]> | undefined;
    if (record.content_evidence) {
      contentCitations = {};
      const allowed = new Set(record.evidence_ids);
      for (const [column, value] of Object.entries(record.content)) {
        const groups = record.content_evidence[column];
        // 绑定缺失或串到别的记录时不能退回整组引用，避免看似可定位却指向错误来源。
        if (!groups || groups.length !== (Array.isArray(value) ? value.length : 1)
          || groups.some((ids) => !ids.length || ids.some((id) => !allowed.has(id)))) {
          throw new Error("专题结果的逐条依据不完整，请重新解析本模块");
        }
        contentCitations[column] = groups.map((ids) => ids.map((id) => data.evidence[id]!));
      }
    }
    const note = "适用范围：" + scopeLabel(record.scope);
    return [{
      id: record.id, field: record.title, group: record.group, sort_order: record.sort_order,
      values: [{ value: record.text, citations }], verification: record.verification,
      note, record,
      output: {
        version, layout: section.layout, columns: section.columns,
        title_column: section.title_column,
        key: record.key, content: record.content, citations: contentCitations, parent_key: record.parent_key ?? null,
        node_type: record.node_type ?? null,
      },
    }];
  });
}
