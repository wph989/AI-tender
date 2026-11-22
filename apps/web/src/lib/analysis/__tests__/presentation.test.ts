import { expect, it } from "vitest";
import { filterResults, matchesScope, needsAttention, resultCounts, unpairedFields } from "../presentation";
import { groupGaps } from "../gaps";
import { scopeLabel } from "../scope";
import type { AnalysisField, AnalysisGap, BusinessRecord } from "@/types/knowledge";

function item(id: string, overrides: Partial<BusinessRecord> = {}): AnalysisField {
  return {
    id, field: id, group: "正文", sort_order: 0, note: "", verification: "supported", values: [],
    record: { id, key: id, kind: "requirement", title: id, text: id, module_key: "tech",
      scope: { kind: "common", lot_refs: [], lot_ids: [] }, structuring: "partial", verification: "supported",
      citations: [], group: "正文", sort_order: 0, category: "other", materials: [], scoring: null,
      conditions: { expression: "", logic: "text", terms: [], exceptions: [] }, ...overrides },
  };
}

it("按标段筛选保留公共要求，排除未知范围和近似标段名", () => {
  expect(matchesScope({ kind: "common", lot_refs: [] }, "id:1")).toBe(true);
  expect(matchesScope({ kind: "unknown", lot_refs: ["A"] }, "ref:A")).toBe(false);
  expect(matchesScope({ kind: "lots", lot_refs: ["A1"] }, "ref:A")).toBe(false);
  expect(matchesScope({ kind: "lots", lot_refs: ["A"], lot_ids: [2] }, "id:1")).toBe(false);
  expect(matchesScope({ kind: "lots", lot_refs: ["A"], lot_ids: [1] }, "id:1")).toBe(true);
  expect(scopeLabel({ kind: "lots", lot_refs: ["甲标段"], lot_ids: [1] })).toBe("甲标段");
});

it("KV 数组按项对应，只将数量不符列为待核对", () => {
  const normal = item("normal");
  const gap: AnalysisGap = { code: "incomplete_structure", detail: "未提取数量", record_id: "normal",
    scope: { kind: "common", lot_ids: [], lot_refs: [] } };
  expect(needsAttention(normal, [gap])).toBe(false);
  expect(needsAttention(normal, [{ ...gap, code: "unknown_condition" }])).toBe(true);
  const compound = { ...normal, output: { version: "1", key: "compound", layout: "table" as const,
    parent_key: null, node_type: null,
    columns: ["字段", "内容"], content: { 字段: ["项目", "预算"], 内容: ["工程", "100万元"] } } };
  expect(unpairedFields(compound)).toBe(false);
  expect(needsAttention(compound)).toBe(false);
  const incomplete = { ...compound, output: { ...compound.output, content: { 字段: ["项目", "预算"], 内容: ["工程"] } } };
  expect(unpairedFields(incomplete)).toBe(true);
  expect(needsAttention(incomplete)).toBe(true);
  expect(unpairedFields({ ...compound, output: { ...compound.output, content: { 字段: "项目范围", 内容: ["安装", "调试"] } } })).toBe(false);
  expect(unpairedFields({ ...compound, output: { ...compound.output, content: { 字段: ["项目范围"], 内容: ["安装", "调试"] } } })).toBe(false);
});

it("深层材料搜索与分类联合筛选保留祖先，但只计直接命中的节点", () => {
  const nodes = ["root", "middle", "leaf"].map((id, i) => ({ ...item(id, { kind: "format_node" }),
    group: i === 2 ? "附件" : "目录", output: { version: "1", key: id, layout: "tree" as const,
      parent_key: i === 0 ? null : ["root", "middle"][i - 1]!, node_type: "section" as const, columns: ["编制要求"],
      content: { 编制要求: i === 2 ? "列出回退步骤" : "上层目录" } } }));
  const filtered = filterResults(nodes, { query: "回退", group: "附件", scope: "", attention: false });
  expect(filtered.map((node) => [node.id, node.contextOnly])).toEqual([["root", true], ["middle", true], ["leaf", false]]);
  expect(filterResults(nodes, { query: "回退", group: "目录", scope: "", attention: false })).toEqual([]);
  expect(nodes.every((node) => node.contextOnly === undefined)).toBe(true);
});

it("同专题同主题同范围说明去重，不合并不同主题、标段和目标事项", () => {
  const base = { key: "1", detail: "缺少附件", code: "unresolved_reference", moduleKey: "tech", topicTitle: "迁移", scopeLabel: "A" };
  const groups = groupGaps([base, { ...base, key: "2" }, { ...base, key: "3", scopeLabel: "B" },
    { ...base, key: "4", topicTitle: "验收" }, { ...base, key: "5", recordId: "r1" },
    { ...base, key: "6", code: "coverage_pending" }]);
  expect(groups).toHaveLength(5);
  expect(groups[0]?.gaps).toHaveLength(1);
  expect(groups.at(-1)?.category).toBe("分析尚未完成");
});

it("统计区分信息、要求、材料节点和关联", () => {
  const items = [item("fact", { kind: "fact" }), item("lot", { kind: "lot" }), item("req"),
    item("format", { kind: "format_node" }), item("relation", { kind: "relation" })];
  expect(resultCounts([{ id: 1, title: "专题", module_key: "tech", status: "completed", error_message: null, items }]))
    .toEqual({ facts: 2, requirements: 1, materials: 1, relations: 1 });
});

it("显示文案相同的未知标段缺口仍按原始范围区分", () => {
  const base = { code: "coverage_pending", detail: "此主题尚未完成核对", moduleKey: "tech",
    topicTitle: "实施条件", scopeLabel: "归属待确认" };
  const gaps = ["A", "B", "A"].map((ref, index) => ({ ...base, key: String(index),
    scope: { kind: "unknown" as const, lot_refs: [ref], lot_ids: [] } }));
  expect(groupGaps(gaps).map((group) => group.gaps.length)).toEqual([1, 1]);
});

it("稳定问题ID跨主题只统计一次，独立标段缺口及待补材料分别保留", () => {
  const base = { key: "a", issueId: "date-a", action: "provide_input" as const,
    detail: "具体日期待核对", moduleKey: "opening", topicTitle: "开标时间",
    scope: { kind: "lots" as const, lot_refs: ["标段一"] } };
  const groups = groupGaps([base, { ...base, key: "b", topicTitle: "异议时限" },
    { ...base, key: "c", issueId: "date-b", scope: { kind: "lots", lot_refs: ["标段二"] } }]);
  expect(groups.flatMap((group) => group.gaps)).toHaveLength(2);
  expect(groups.every((group) => group.category === "待补充材料")).toBe(true);
});


it("机器自查未通过的事项进入待核对筛选", () => {
  const old: AnalysisField = { ...item("old"), verification: "unsupported" };
  const current = item("current");
  expect(needsAttention(old)).toBe(true);
  expect(needsAttention(current)).toBe(false);
  expect(filterResults([old, current], { query: "", scope: "", attention: true })
    .map((entry) => entry.id)).toEqual(["old"]);
});
