import { expect, it } from "vitest";
import { findCitationResult } from "../citations";
import type { AnalysisField, AnalysisModule, Citation } from "@/types/knowledge";

const ref: Citation = {
  source_id: 1, collection_id: 1, project_id: 1, project_file_id: 1,
  version_id: 2, parse_run_id: 3, element_id: 4, anchor: "p1b1", page_no: 1,
  bbox: null, file_name: "原文.pdf", purpose: "tender", quote: "共有的原文依据",
};
function item(id: string, citation: Citation = ref): AnalysisField {
  return { id, field: id, group: "", sort_order: 0, note: "", verification: "supported",
    values: [{ value: id, citations: [citation] }] };
}
function module(id: number, items: AnalysisField[]): AnalysisModule {
  return { id, module_key: String(id), title: "专题", status: "completed", error_message: null, items };
}

it("多个专题共享原文时返回刚刚点击的事项，而不是第一个匹配项", () => {
  const modules = [module(1, [item("background")]), module(2, [item("score")])];
  expect(findCitationResult(modules, ref, "score", 2)?.item.id).toBe("score");
  expect(findCitationResult(modules, ref, undefined, 2)?.item.id).toBe("score");
});

it("同名元素不能跨文档版本或解析批次反向定位", () => {
  const modules = [module(1, [item("old-version", { ...ref, version_id: 1 }),
    item("old-parse", { ...ref, parse_run_id: 2 }), item("current")])];
  expect(findCitationResult(modules, ref, "old-version")?.item.id).toBe("current");
  expect(findCitationResult(modules, { ...ref, version_id: 99 })).toBeUndefined();
});

it("未选中事项时优先匹配摘录，撤销事项不再成为返回目标", () => {
  const modules = [module(1, [item("another", { ...ref, quote: "另一项要求" }), item("exact")])];
  expect(findCitationResult(modules, ref, "withdrawn")?.item.id).toBe("exact");
});
