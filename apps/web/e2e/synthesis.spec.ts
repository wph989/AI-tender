import { test, expect } from "@playwright/test";
import type { AnalysisField, AnalysisModule, AnalysisOutput, Citation, ModuleRecords } from "../src/types/knowledge";
import { mockApi } from "./fixtures";

const citation: Citation = {
  source_id: 1, collection_id: 1, project_id: 1, project_file_id: 1,
  version_id: 1, parse_run_id: 1, element_id: 1, anchor: "p1b1", page_no: 1,
  bbox: [0.1, 0.1, 0.8, 0.2], file_name: "综合测试原文.pdf", purpose: "tender",
  quote: "原始段落：系统迁移须分阶段实施，并配置回退方案，验收后提供三年质保。",
};

function item(id: string, title: string, group: string, layout: AnalysisOutput["layout"],
  columns: string[], content: AnalysisOutput["content"], parent: string | null = null): AnalysisField {
  return {
    id, field: title, group, sort_order: 0, note: "适用范围：公共要求", verification: "supported",
    values: [{ value: "内部业务投影不应作为正文显示", citations: [citation] }],
    output: { version: "1", key: id, layout, columns, content,
      parent_key: parent, node_type: layout === "tree" ? "section" : null },
  };
}

const modules: AnalysisModule[] = [
  {
    id: 1, title: "技术要求", module_key: "tech_requirement_parsing", status: "completed",
    error_message: null, research_summary: "已核对主文件、技术附件与全部技术主题。",
    research_gaps: [{ key: "reference:0", detail: "附件B未提供，兼容性细则待核对。" }],
    items: [
      item("background", "建设目标", "项目背景", "list", ["背景"], { 背景: "完成现有平台升级与迁移。" }),
      item("migration", "平台迁移任务", "技术方案要求", "list", ["章节来源", "要求摘要", "关键要求"], {
        章节来源: "第五章 技术要求", 要求摘要: "制定分阶段迁移方案并说明回退与服务保障。",
        关键要求: ["迁移实施分阶段组织。", "必须提供可执行的回退方案。", "验收后提供三年质保。"],
      }),
    ],
  },
  {
    id: 2, title: "评分办法", module_key: "scoring_standard_parsing", status: "completed",
    error_message: null,
    items: [item("score", "业绩评分", "商务评分标准", "table", ["评分项", "满分分值", "评分标准（原文摘录）"], {
      评分项: "同类项目业绩", 满分分值: "6分",
      "评分标准（原文摘录）": ["每提供1项符合定义的业绩得2分。", "最高6分；须提供合同及验收证明。"],
    })],
  },
  {
    id: 3, title: "投标文件格式", module_key: "bid_format_outline_parsing", status: "completed",
    error_message: null,
    items: [
      item("technical", "技术文件", "", "tree", ["编制要求"], { 编制要求: ["独立编制技术文件。"] }),
      item("plan", "实施方案", "", "tree", ["编制要求"], { 编制要求: ["列明实施步骤及里程碑。"] }, "technical"),
      item("fallback", "回退计划", "", "tree", ["编制要求"], { 编制要求: ["说明回退条件与操作顺序。"] }, "plan"),
    ],
  },
];

let errors: string[];
function records(module: AnalysisModule): ModuleRecords {
  return {
    schema_version: "1", module_key: module.module_key, status: module.status,
    evidence: { source: citation },
    output_schema: { version: "1", sections: module.items.map((item) => ({
      title: item.output!.layout === "tree" ? "*" : item.group,
      layout: item.output!.layout, columns: item.output!.columns,
    })) },
    records: module.items.map((item) => ({
      id: item.id, key: item.id, title: item.field, text: "JSON业务正文",
      group: item.group, sort_order: item.sort_order, module_key: module.module_key,
      kind: item.output!.layout === "tree" ? "format_node" : "requirement",
      content: item.output!.content, parent_key: item.output!.parent_key,
      node_type: item.output!.node_type, evidence_ids: ["source"],
      scope: { kind: "common", lot_refs: [] }, structuring: "complete", verification: "supported",
      category: "other", materials: [], scoring: null,
      conditions: { expression: "", logic: "text", terms: [], exceptions: [] },
    })),
  };
}

test.beforeEach(async ({ page }) => {
  errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await mockApi(page);
  await page.route("**/api/v1/projects/1/analysis", (route) => route.fulfill({ json: {
    analysis_category: "goods", analysis_topics: [], lots: [], sources: [],
    reports: [{ id: 1, status: "completed" }], categories: { goods: "货物" }, topics: {},
  } }));
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: {
    // 报告投影故意与独立记录不同，证明页面真的接入新接口。
    id: 1, status: "completed", category: "goods", topics: [], coverage: {},
    modules: modules.map((module) => ({ ...module, items: [] })), data_schema_version: "1",
    created_at: "2026-10-14T10:00:00Z", finished_at: "2026-10-14T10:05:00Z", stale: false,
    error_message: null, runtime_retired: false,
  } }));
  await page.route("**/api/v1/analysis/reports/1/data", (route) => route.fulfill({
    status: 409, json: { error: { message: "快照未就绪" } },
  }));
  await page.route("**/api/v1/analysis/reports/1/modules/*/records", (route) => {
    const key = route.request().url().split("/").at(-2);
    return route.fulfill({ json: records(modules.find((module) => module.module_key === key)!) });
  });
  await page.route("**/api/v1/knowledge/citations/resolve", (route) => route.fulfill({ json: citation }));
  await page.route("**/api/v1/versions/1/pages", (route) => route.fulfill({ json: { pages: [
    { page_no: 1, width_pt: 595, height_pt: 842, rotation: 0, has_text_layer: true },
  ] } }));
  await page.route("**/api/v1/versions/1/file", (route) => route.fulfill({
    path: "public/samples/sample-tender.pdf", contentType: "application/pdf",
  }));
  await page.goto("/projects/1");
});
test.afterEach(() => expect(errors).toEqual([]));

test("技术专题展示综合摘要、独立任务和逐条要求，并能打开原文", async ({ page }, info) => {
  // 按语义定位当前专题，避免依赖组件库的内部活动面板类名。
  const body = page.getByRole("tabpanel", { name: "技术要求 2 项", exact: true })
    .locator(".module-markdown");
  await expect(body.getByRole("heading", { name: "技术方案要求", exact: true })).toBeVisible();
  await expect(body.getByText("制定分阶段迁移方案并说明回退与服务保障。", { exact: true })).toBeVisible();
  await expect(body.getByText("必须提供可执行的回退方案。", { exact: true })).toBeVisible();
  await expect(body).not.toContainText("内部业务投影");
  await expect(body).not.toContainText("原始段落：");
  await page.getByText("检索范围与未决事项", { exact: true }).click();
  await expect(page.getByText("附件B未提供，兼容性细则待核对。", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: info.outputPath("synthesis-technical.png"), fullPage: true });
  const resolved = page.waitForRequest("**/knowledge/citations/resolve");
  await body.getByRole("button", { name: /^定位：/ }).last().click();
  expect((await resolved).postDataJSON()).toMatchObject({ source_id: 1, parse_run_id: 1, anchor: "p1b1" });
  const viewer = page.getByRole("region", { name: "引用原文", exact: true });
  await expect(viewer).toBeVisible();
  await expect(viewer.locator("canvas").first()).toBeVisible();
});

test("评分专题使用 Skill 的列名并保留各评分档次", async ({ page }, info) => {
  await page.getByRole("tab", { name: /评分办法/ }).click();
  const table = page.getByRole("tabpanel", { name: "评分办法 1 项", exact: true })
    .locator(".module-structured-table");
  await expect(table.getByRole("columnheader")).toHaveText(["评分项", "满分分值", "评分标准（原文摘录）"]);
  await expect(table.getByRole("listitem")).toHaveCount(2);
  await expect(table).toContainText("最高6分；须提供合同及验收证明。");
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: info.outputPath("synthesis-scoring.png"), fullPage: true });
});

test("格式专题保留三层材料结构，项目提供文档预览入口", async ({ page }, info) => {
  await page.getByRole("tab", { name: /投标文件格式/ }).click();
  const root = page.locator('[data-report-item="technical"]');
  await expect(root.locator('[data-report-item="plan"] [data-report-item="fallback"]')).toBeVisible();
  await expect(root).toContainText("说明回退条件与操作顺序。");
  await expect(page.getByRole("link", { name: "文档预览", exact: true })).toHaveAttribute("href", "/projects/1?view=document");
  await expect(page.getByRole("link", { name: "字段复核", exact: true })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("synthesis-format.png"), fullPage: true });
});

test("独立结果读取失败只影响本专题，重新加载后恢复", async ({ page }) => {
  let failed = true;
  await page.route("**/api/v1/analysis/reports/1/modules/tech_requirement_parsing/records", (route) =>
    failed ? route.fulfill({ status: 503, json: { error: { message: "专题接口暂时不可用" } } })
      : route.fulfill({ json: records(modules[0]!) }));
  await page.reload();
  await page.getByRole("tab", { name: /技术要求/ }).click();
  await expect(page.getByText("专题接口暂时不可用", { exact: true })).toBeVisible();
  await expect(page.getByText("制定分阶段迁移方案并说明回退与服务保障。", { exact: true })).toHaveCount(0);
  failed = false;
  await page.getByRole("button", { name: "重新加载", exact: true }).click();
  await expect(page.getByText("制定分阶段迁移方案并说明回退与服务保障。", { exact: true })).toBeVisible();
});

test("运行中的维度通过轮询显示新保存的记录，依据撤销后清除正文", async ({ page }) => {
  let withdrawn = false;
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: {
    id: 1, status: "running", category: "goods", topics: [], coverage: {},
    modules: modules.map((module) => ({ ...module, items: [] })), data_schema_version: "1",
    created_at: "2026-10-16T10:00:00Z", stale: false, runtime_retired: false,
  } }));
  let reads = 0;
  await page.route("**/api/v1/analysis/reports/1/modules/tech_requirement_parsing/records", (route) => {
    const data = records(modules[0]!);
    if (withdrawn || ++reads === 1) data.records = [];
    return route.fulfill({ json: data });
  });
  await page.reload();
  await page.getByRole("tab", { name: /技术要求/ }).click();
  await expect(page.getByText("制定分阶段迁移方案并说明回退与服务保障。", { exact: true })).toBeVisible({ timeout: 12000 });
  withdrawn = true;
  await expect(page.getByText("制定分阶段迁移方案并说明回退与服务保障。", { exact: true })).toHaveCount(0, { timeout: 12000 });
});

test("切换报告时延迟的旧维度结果不能覆盖新报告", async ({ page }) => {
  await page.route("**/api/v1/projects/1/analysis", (route) => route.fulfill({ json: {
    analysis_category: "goods", analysis_topics: [], lots: [], sources: [],
    reports: [{ id: 1, status: "completed" }, { id: 2, status: "completed" }],
    categories: { goods: "货物" }, topics: {},
  } }));
  await page.route("**/api/v1/analysis/reports/2", (route) => route.fulfill({ json: {
    id: 2, status: "completed", category: "goods", topics: [], coverage: {},
    modules: [{ ...modules[0], items: [] }], data_schema_version: "1",
    created_at: "2026-10-16T10:00:00Z", stale: false, runtime_retired: false,
  } }));
  await page.route("**/api/v1/analysis/reports/2/data", (route) => route.fulfill({ status: 409, json: {} }));
  await page.route("**/api/v1/analysis/reports/2/modules/*/records", (route) => {
    const data = records(modules[0]!);
    data.records = [data.records[1]!];
    data.records[0]!.content = { 要求摘要: "新报告独立结果", 关键要求: ["新报告要求"] };
    return route.fulfill({ json: data });
  });
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/v1/analysis/reports/1/modules/tech_requirement_parsing/records", async (route) => {
    await delayed;
    await route.fulfill({ json: records(modules[0]!) });
  });
  const pending = page.waitForRequest("**/analysis/reports/1/modules/tech_requirement_parsing/records");
  await page.reload();
  await pending;
  await page.getByRole("combobox", { name: "选择报告版本", exact: true }).click();
  await page.locator(".ant-select-dropdown").getByText("报告 #2 · 已完成", { exact: true }).click();
  await expect(page.getByText("新报告独立结果", { exact: true })).toBeVisible();
  release();
  await expect(page.getByText("制定分阶段迁移方案并说明回退与服务保障。", { exact: true })).toHaveCount(0);
});
