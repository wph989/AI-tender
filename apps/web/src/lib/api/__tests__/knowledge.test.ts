import { afterEach, expect, it, vi } from "vitest";
import type { AnalysisReport, ModuleRecords, ReportRecords } from "@/types/knowledge";
import { loadReportRecords } from "@/lib/api/knowledge";
import { recordItems } from "@/lib/analysis/records";

afterEach(() => vi.unstubAllGlobals());

const data: ModuleRecords = {
  schema_version: "1", module_key: "tech_requirement_parsing", status: "completed",
  quality_status: "self_check_passed", quality_issues: [],
  output_schema: { version: "1", sections: [{
    title: "技术方案要求", layout: "list", columns: ["要求摘要", "关键要求"],
  }] },
  evidence: {}, records: [],
};
const report: AnalysisReport = {
  id: 1, project_id: 1, allow_partial: false, quality_status: "self_check_passed",
  runtime_version: "agent-led-v1", status: "completed", category: "goods", topics: [], created_at: "",
  stale: false, error_message: null, coverage: {}, data_schema_version: "1",
  modules: [1, 2].map((id) => ({
    id, module_key: id === 1 ? "tech_requirement_parsing" : "scoring_standard_parsing",
    title: "专题" + id, status: "completed", error_message: null,
    items: [{ id: "cached", field: "缓存正文", group: "", sort_order: 0,
      values: [], note: "", verification: "supported" }],
  })),
};

const version = "a".repeat(64);
function batch(first: ModuleRecords, second: ModuleRecords = data): ReportRecords {
  return { modules: report.modules.map((module, index) => ({
    module_key: module.module_key, version,
    data: { ...(index === 0 ? first : second), module_key: module.module_key },
  })) };
}

it("读取失败清除本专题缓存正文，其它专题仍正常加载", async () => {
  const response = batch(data);
  response.modules[1] = { module_key: report.modules[1]!.module_key, error: "暂时不可用" };
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(response)));
  vi.stubGlobal("fetch", fetch);
  const loaded = await loadReportRecords(report);
  expect(loaded.modules[0]?.items).toEqual([]);
  expect(loaded.modules[1]?.items).toEqual([]);
  expect(loaded.modules[1]?.records_error).toBe("暂时不可用");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0]?.[0]).toBe("/api/v1/analysis/reports/1/records");
});

it("逐条绑定校验失败只标记当前专题，其它有效专题仍正常加载", async () => {
  const ref = {
    source_id: 1, collection_id: 1, project_id: 1, project_file_id: 1, version_id: 1,
    parse_run_id: 1, element_id: 1, anchor: "p1b1", page_no: 1,
    bbox: null, file_name: "原文.pdf", purpose: "tender", quote: "迁移与回退要求",
  };
  const valid: ModuleRecords = { ...data, evidence: { source: ref }, records: [{
    id: "valid", key: "valid", title: "实施任务", text: "辅助正文", group: "技术方案要求",
    sort_order: 0, module_key: data.module_key, kind: "requirement",
    content: { 要求摘要: "迁移与回退", 关键要求: ["实施迁移", "保留回退方案"] },
    content_evidence: { 要求摘要: [["source"]], 关键要求: [["source"], ["source"]] },
    evidence_ids: ["source"], scope: { kind: "common", lot_refs: [] },
    verification: "supported", structuring: "complete",
  }] };
  const invalid = structuredClone(valid);
  invalid.records[0]!.content_evidence!.关键要求 = [["source"]];
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(batch(invalid, valid)))));
  const loaded = await loadReportRecords(report);
  expect(loaded.modules[0]?.items).toEqual([]);
  expect(loaded.modules[0]?.records_error).toBe("专题结果的逐条依据不完整，请重新解析本模块");
  expect(loaded.modules[0]?.records_loading).toBe(false);
  expect(loaded.modules[1]?.items[0]?.id).toBe("valid");
  expect(loaded.modules[1]?.records_error).toBeUndefined();
  expect(loaded.modules[1]?.records_loading).toBe(false);
});

it("未变化专题复用正文，最新报告进度继续更新", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(batch(data))))
    .mockResolvedValueOnce(new Response(JSON.stringify({ modules: report.modules.map((module) => ({
      module_key: module.module_key, version,
    })) })));
  vi.stubGlobal("fetch", fetch);
  const previous = await loadReportRecords(report);
  const updated = { ...report, modules: report.modules.map((module) => ({ ...module,
    progress: { protocol: "skill-agent-v1" as const,
      draft_count: 8, reviewed_count: 5, unresolved_issues: 1 },
  })) };
  const loaded = await loadReportRecords(updated, undefined, previous);
  expect(loaded.modules[0]?.items).toBe(previous.modules[0]?.items);
  expect(loaded.modules[0]?.progress?.draft_count).toBe(8);
  expect(JSON.parse(fetch.mock.calls[1]?.[1].body)).toEqual({
    module_keys: report.modules.map((module) => module.module_key),
    versions: Object.fromEntries(report.modules.map((module) => [module.module_key, version])),
  });
});

it("整批核验失败清空所有缓存，下次请求不再携带旧版本", async () => {
  const previous = { ...report, modules: report.modules.map((module) => ({ ...module, records_version: version })) };
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({
    error: { message: "访问已撤销" },
  }), { status: 403 })).mockResolvedValueOnce(new Response(JSON.stringify(batch(data))));
  vi.stubGlobal("fetch", fetch);
  const failed = await loadReportRecords(previous, undefined, previous);
  expect(failed.modules.every((module) => module.items.length === 0 && !module.records_version)).toBe(true);
  expect(failed.modules[0]?.records_error).toBe("访问已撤销");
  await loadReportRecords(report, undefined, failed);
  expect(JSON.parse(fetch.mock.calls[1]?.[1].body).versions).toEqual({});
});

it("切换报告不携带旧版本，无完整正文的错误回执不能复用缓存", async () => {
  const previous = { ...report, modules: report.modules.map((module) => ({ ...module, records_version: version })) };
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({
    modules: report.modules.map((module) => ({ module_key: module.module_key, version })),
  })));
  vi.stubGlobal("fetch", fetch);
  const loaded = await loadReportRecords({ ...report, id: 2 }, undefined, previous);
  expect(JSON.parse(fetch.mock.calls[0]?.[1].body).versions).toEqual({});
  expect(loaded.modules.every((module) => module.items.length === 0 && !module.records_version)).toBe(true);
});

it("一份合并回执只替换有变化的专题，并清除撤销后的正文", async () => {
  const previous = { ...report, modules: report.modules.map((module) => ({ ...module, records_version: version })) };
  const response = batch(data);
  response.modules[0] = { module_key: report.modules[0]!.module_key, version };
  response.modules[1]!.version = "b".repeat(64);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(response))));
  const loaded = await loadReportRecords(report, undefined, previous);
  expect(loaded.modules[0]?.items).toBe(previous.modules[0]?.items);
  expect(loaded.modules[1]?.items).toEqual([]);
  expect(loaded.modules[1]?.records_version).toBe("b".repeat(64));
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
    group: "技术方案要求", sort_order: 1,
  };
  const result = recordItems({ ...data, evidence: { evidence: ref }, records: [record] });
  expect(result[0]?.output?.content).toEqual(record.content);
  expect(result[0]?.output?.columns).toEqual(["要求摘要", "关键要求"]);
  expect(result[0]?.values[0]?.citations).toEqual([ref]);
  expect(result[0]?.note).toBe("适用范围：A标段");
  expect(result[0]?.record).toEqual(record);
  expect(recordItems({ ...data, evidence: {}, records: [record] })).toEqual([]);
});

it("逐条依据按正文位置解析，拒绝数量不符或借用其它事项的引用", () => {
  const first = {
    source_id: 1, collection_id: 2, project_id: 3, project_file_id: 4, version_id: 5,
    parse_run_id: 6, element_id: 7, anchor: "p8b1", page_no: 8,
    bbox: null, file_name: "原文.pdf", purpose: "tender", quote: "迁移要求",
  };
  const second = { ...first, element_id: 8, anchor: "p8b2", quote: "回退要求" };
  const record = {
    id: "task", key: "task", kind: "requirement" as const, title: "独立任务",
    text: "辅助文本", content: { 要求摘要: "迁移与回退", 关键要求: ["迁移要求", "回退要求"] },
    evidence_ids: ["first", "second"], scope: { kind: "common" as const, lot_refs: [] },
    content_evidence: { 要求摘要: [["first", "second"]], 关键要求: [["first"], ["second"]] },
    structuring: "complete" as const, module_key: data.module_key, verification: "supported" as const,
    group: "技术方案要求", sort_order: 1,
  };
  const input = { ...data, evidence: { first, second, unrelated: second }, records: [record] };
  const result = recordItems(input)[0]!;
  expect(result.output?.citations).toEqual({ 要求摘要: [[first, second]], 关键要求: [[first], [second]] });
  expect(result.values).toHaveLength(1);
  record.content_evidence.关键要求 = [["first"]];
  expect(() => recordItems(input)).toThrow("逐条依据不完整");
  record.content_evidence.关键要求 = [["first"], ["unrelated"]];
  expect(() => recordItems(input)).toThrow("逐条依据不完整");
});
