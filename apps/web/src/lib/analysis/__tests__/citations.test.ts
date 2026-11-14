import { expect, it } from "vitest";
import { findCitationResult, groupCitationLocations, presentCitations, viewerCitations } from "../citations";
import type { AnalysisField, AnalysisModule, Citation } from "@/types/knowledge";

const ref: Citation = {
  source_id: 1, collection_id: 1, project_id: 1, project_file_id: 1,
  version_id: 2, parse_run_id: 3, element_id: 4, anchor: "p1b1", page_no: 1,
  bbox: null, file_name: "原文.pdf", purpose: "tender", quote: "共有的原文依据",
};
function citedItem(id: string, citation: Citation = ref): AnalysisField {
  return { id, field: id, group: "", sort_order: 0, note: "", verification: "supported",
    values: [{ value: id, citations: [citation] }] };
}
function module(id: number, items: AnalysisField[]): AnalysisModule {
  return { id, module_key: String(id), title: "专题", status: "completed", error_message: null, items };
}

it("多个专题共享原文时返回刚刚点击的事项，而不是第一个匹配项", () => {
  const modules = [module(1, [citedItem("background")]), module(2, [citedItem("score")])];
  expect(findCitationResult(modules, ref, "score", 2)?.item.id).toBe("score");
  expect(findCitationResult(modules, ref, undefined, 2)?.item.id).toBe("score");
});

it("同名元素不能跨文档版本或解析批次反向定位", () => {
  const modules = [module(1, [citedItem("old-version", { ...ref, version_id: 1 }),
    citedItem("old-parse", { ...ref, parse_run_id: 2 }), citedItem("current")])];
  expect(findCitationResult(modules, ref, "old-version")?.item.id).toBe("current");
  expect(findCitationResult(modules, { ...ref, version_id: 99 })).toBeUndefined();
});

it("未选中事项时优先匹配摘录，撤销事项不再成为返回目标", () => {
  const modules = [module(1, [citedItem("another", { ...ref, quote: "另一项要求" }), citedItem("exact")])];
  expect(findCitationResult(modules, ref, "withdrawn")?.item.id).toBe("exact");
});

const source: Citation = {
  source_id: 1, collection_id: 1, project_id: 1, project_file_id: 1,
  version_id: 1, parse_run_id: 1, element_id: 1, anchor: "p1b1", page_no: 1,
  bbox: [0, 0, 1, 1], file_name: "招标文件.pdf", purpose: "tender", quote: "原文要求。",
};
function item(content: Record<string, string | string[]>, citations: Record<string, Citation[][]>, refs: Citation[]): AnalysisField {
  return {
    id: "one", field: "实施要求", group: "技术方案要求", sort_order: 0, note: "", verification: "supported",
    values: [{ value: "完整事项", citations: refs }],
    output: { version: "1", key: "one", layout: "list", parent_key: null, node_type: null,
      columns: Object.keys(content), content, citations },
  };
}

it("跨正文单元与补充依据只保留一个位置，全部不同摘录归入首次入口", () => {
  const detail = { ...source, quote: "同块的实施细节。" };
  const condition = { ...source, quote: "仅适用于夜间窗口。" };
  const record = item({ 要求摘要: "实施迁移", 关键要求: ["制定计划", "执行回退"] },
    { 要求摘要: [[source]], 关键要求: [[detail, source], [source]] }, [source, detail, condition]);
  const original = structuredClone(record);
  const result = presentCitations(record);
  expect(result.content["要求摘要"]).toEqual([[source, detail, condition]]);
  expect(result.content["关键要求"]).toEqual([[], []]);
  expect(result.extra).toEqual([]);
  const locations = groupCitationLocations(result.content["要求摘要"]![0]!);
  expect(locations).toHaveLength(1);
  expect(locations[0]!.ref).toBe(source);
  expect([...locations[0]!.quotes]).toEqual([source.quote, detail.quote, condition.quote]);
  // 分配必须可重复且以事项为边界，切换筛选或重渲染不能消耗原始证据。
  expect(presentCitations(record)).toEqual(result);
  expect(presentCitations({ ...record, id: "another" })).toEqual(result);
  expect(record).toEqual(original);
});

it("同页不同块以及不同来源、文档版本、解析批次保留独立位置", () => {
  const refs = [source, { ...source, element_id: 2, anchor: "p1b2" }, { ...source, source_id: 2 },
    { ...source, version_id: 2 }, { ...source, parse_run_id: 2 }];
  const record = item({ 背景: refs.map(() => "独立依据") }, { 背景: refs.map((ref) => [ref]) }, refs);
  const result = presentCitations(record);
  expect(result.content["背景"]).toEqual(refs.map((ref) => [ref]));
  expect(groupCitationLocations(refs)).toHaveLength(5);
  expect(result.extra).toEqual([]);
});

it("KV隐藏的字段依据合并到正文同位置，独立的条件依据仍可定位", () => {
  const label = { ...source, quote: "本项目实施要求：" };
  const condition = { ...source, element_id: 2, quote: "实施前须报批。" };
  const record = item({ 字段: "实施要求", 内容: ["实施迁移", "制定计划"] },
    { 字段: [[label]], 内容: [[source], [source]] }, [label, source, condition, condition]);
  const result = presentCitations(record);
  expect(result.content).toEqual({ 内容: [[source, label], []] });
  expect(result.extra).toEqual([condition]);
});

it("评分优先在满分入口合并同位置摘录，空内容不占用定位入口", () => {
  const second = { ...source, element_id: 2, quote: "第二档要求。" };
  const record = item({ 评分项: "业绩", 满分分值: "6分", 评分标准: ["每项2分", "最高6分"], 备注: "" },
    { 评分项: [[source]], 满分分值: [[source]], 评分标准: [[source], [second]], 备注: [[second]] }, [source, second]);
  expect(presentCitations(record).content).toEqual({ 评分项: [[]], 满分分值: [[source]], 评分标准: [[], [second]], 备注: [] });
  const empty = item({ 背景: "" }, { 背景: [[source]] }, [source]);
  expect(presentCitations(empty)).toEqual({ content: { 背景: [] }, extra: [source] });
});

it("同一长元素的大块区域分别定位，后续条件不能被首块的坐标覆盖", () => {
  const first: Citation = { ...source, bbox: [0.1, 0.1, 0.8, 0.8] };
  const second: Citation = { ...source, bbox: [0.1, 0.1, 0.8, 0.95], quote: "补充条件须提交证明材料。" };
  const record = item({ 要求摘要: "实施要求" }, { 要求摘要: [[first]] }, [first, second]);
  const result = presentCitations(record);
  expect(result.content["要求摘要"]).toEqual([[first]]);
  expect(result.extra).toEqual([second]);
  expect(groupCitationLocations([first, second])).toHaveLength(2);
  expect(viewerCitations([first, second], first)).toEqual([first, second]);
  expect(viewerCitations([first, second], second)).toEqual([first, second]);
  const modules = [module(1, [citedItem("first", first), citedItem("second", second)])];
  expect(findCitationResult(modules, second, "first")?.item.id).toBe("second");
});

it("同区域只保留一个入口和框，跨页仍独立且当前点击摘录优先", () => {
  const detail: Citation = { ...source, quote: "同位置的补充说明。" };
  const nextPage: Citation = { ...source, page_no: 2 };
  expect(groupCitationLocations([source, detail, nextPage])).toHaveLength(2);
  expect(viewerCitations([source, nextPage], detail)).toEqual([detail, nextPage]);
});
