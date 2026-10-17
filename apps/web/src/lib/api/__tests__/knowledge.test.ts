import { afterEach, expect, it, vi } from "vitest";
import type { AnalysisReport, ModuleRecords } from "@/types/knowledge";
import { loadReportRecords } from "@/lib/api/knowledge";
import { recordItems } from "@/lib/analysis/records";

afterEach(() => vi.unstubAllGlobals());

const data: ModuleRecords = {
  schema_version: "1", module_key: "tech_requirement_parsing", status: "completed",
  output_schema: { version: "1", sections: [{
    title: "技术方案要求", layout: "list", columns: ["要求摘要", "关键要求"],
  }] },
  evidence: {}, records: [],
};
const report: AnalysisReport = {
  id: 1, status: "completed", category: "goods", topics: [], created_at: "",
  stale: false, error_message: null, coverage: {}, data_schema_version: "1",
  modules: [1, 2].map((id) => ({
    id, module_key: id === 1 ? "tech_requirement_parsing" : "scoring_standard_parsing",
    title: "专题" + id, status: "completed", error_message: null,
    items: [{ id: "old", field: "旧投影", group: "", sort_order: 0,
      values: [], note: "", verification: "supported" }],
  })),
};

it("一个维度读取失败不阻断其它维度，也不回退旧报告正文", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(data)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ error: { message: "暂时不可用" } }), { status: 503 }));
  vi.stubGlobal("fetch", fetch);
  const loaded = await loadReportRecords(report);
  expect(loaded.modules[0]?.items).toEqual([]);
  expect(loaded.modules[1]?.items).toEqual([]);
  expect(loaded.modules[1]?.records_error).toBe("暂时不可用");
  expect(fetch.mock.calls[0]?.[0]).toBe("/api/v1/analysis/reports/1/modules/tech_requirement_parsing/records");
});

it("历史报告保留原来展示，不请求新版独立结果接口", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const old = { ...report, runtime_retired: true };
  expect(await loadReportRecords(old)).toBe(old);
  expect(fetch).not.toHaveBeenCalled();
});

it("正文只用独立 content，Skill 列顺序及证据身份完整保留", () => {
  const ref = {
    source_id: 1, collection_id: 2, project_id: 3, project_file_id: 4, version_id: 5,
    parse_run_id: 6, element_id: 7, anchor: "anchor", page_no: 8,
    bbox: null, file_name: "原文.pdf", purpose: "tender", quote: "原文要求",
  };
  const record = {
    id: "record", key: "task", kind: "requirement" as const, title: "独立任务",
    text: "辅助文本", content: { 要求摘要: "结果摘要", 关键要求: ["要求一", "要求二"] },
    evidence_ids: ["evidence"], scope: { kind: "lots" as const, lot_refs: ["A标段"] },
    structuring: "partial" as const, module_key: data.module_key, verification: "supported" as const,
    group: "技术方案要求", sort_order: 1, category: "other", materials: [], scoring: null,
    conditions: { expression: "", logic: "text" as const, terms: [], exceptions: [] },
  };
  const result = recordItems({ ...data, evidence: { evidence: ref }, records: [record] });
  expect(result[0]?.output?.content).toEqual(record.content);
  expect(result[0]?.output?.columns).toEqual(["要求摘要", "关键要求"]);
  expect(result[0]?.values[0]?.citations).toEqual([ref]);
  expect(result[0]?.note).toBe("适用范围：A标段；部分条件待核对");
  expect(recordItems({ ...data, evidence: {}, records: [record] })).toEqual([]);
});
