import { test, expect } from "@playwright/test";
import type {
  AnalysisField, AnalysisModule, AnalysisOutput, AnalysisReport, Citation, KnowledgeSource, ModuleRecords,
} from "../src/types/knowledge";
import { mockApi, selectModule } from "./fixtures";

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

/**
 * 报告投影故意与独立记录不同，证明页面真的接入新接口；
 * 各用例只覆盖差异化字段，避免重复维护同一份骨架。
 */
function report(id: number, overrides: Partial<AnalysisReport> = {}): AnalysisReport {
  return {
    id, status: "completed", category: "goods", topics: [], coverage: {},
    modules: modules.map((module) => ({ ...module, items: [] })), data_schema_version: "1",
    created_at: "2026-10-14T10:00:00Z", stale: false, runtime_retired: false,
    error_message: null, ...overrides,
  };
}

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
  await page.route("**/api/v1/analysis/reports/1", (route) =>
    route.fulfill({ json: report(1, { finished_at: "2026-10-14T10:05:00Z" }) }));
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

function source(versionId: number | null, name: string): KnowledgeSource {
  return {
    source_id: 2, collection_id: 1, project_id: 1, project_file_id: 2,
    version_id: versionId, parse_run_id: null, file_name: name, purpose: "tender",
    state: "processing", index_status: null, index_error: null, error_message: null,
    embedding_model_id: null,
  };
}

test("默认预览首个文档，点击引用后轮询不抢回默认文件", async ({ page }, info) => {
  await page.route("**/api/v1/projects/1/analysis", (route) => route.fulfill({ json: {
    analysis_category: "goods", analysis_topics: [], lots: [],
    // 第一个文件尚未解析，预览仍应打开它；报告引用指向第二个文件。
    sources: [source(2, "第一份文档.pdf"), { ...source(1, citation.file_name), source_id: 1 }],
    reports: [{ id: 1, status: "completed" }], categories: { goods: "货物" }, topics: {},
  } }));
  await page.route("**/api/v1/versions/2/pages", (route) => route.fulfill({ json: { pages: [
    { page_no: 1, width_pt: 595, height_pt: 842, rotation: 0, has_text_layer: true },
  ] } }));
  await page.route("**/api/v1/versions/2/file", (route) => route.fulfill({
    path: "public/samples/sample-tender.pdf", contentType: "application/pdf",
  }));
  await page.reload();
  if (info.project.name === "mobile") {
    await page.getByRole("button", { name: "文档预览", exact: true }).click();
  }
  const preview = page.getByRole("region", { name: "文档预览", exact: true });
  await expect(preview).toBeVisible();
  await expect(preview).toContainText("第一份文档.pdf");
  await expect(preview.locator("canvas").first()).toBeVisible();
  await expect(preview.locator(".citation-excerpt")).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("default-document-preview.png"), fullPage: true });
  if (info.project.name === "mobile") {
    await page.getByRole("button", { name: "分析内容", exact: true }).click();
  }
  await page.getByRole("region", { name: "技术要求", exact: true })
    .getByRole("button", { name: /^定位：/ }).first().click();
  const cited = page.getByRole("region", { name: "引用原文", exact: true });
  await expect(cited).toBeVisible();
  await expect(cited).toContainText(citation.file_name);
  await expect(cited.locator("canvas").first()).toBeVisible();
  await page.waitForResponse("**/api/v1/projects/1/analysis");
  await expect(cited).toContainText(citation.file_name);
  await expect(preview).toHaveCount(0);
});

test("没有报告时也能在文件准备完成后自动展示预览", async ({ page }, info) => {
  let prepared = false;
  await page.route("**/api/v1/projects/1/analysis", (route) => route.fulfill({ json: {
    analysis_category: "goods", analysis_topics: [], lots: [],
    sources: [source(prepared ? 1 : null, "等待转换的文档.docx")], reports: [],
    categories: { goods: "货物" }, topics: {},
  } }));
  await page.reload();
  await expect(page.getByRole("region", { name: "文档预览", exact: true })).toHaveCount(0);
  if (info.project.name === "desktop") {
    await expect(page.getByText("文件准备完成后会自动显示预览。", { exact: true })).toBeVisible();
  } else {
    await expect(page.getByRole("button", { name: "文档预览", exact: true })).toBeDisabled();
  }
  prepared = true;
  if (info.project.name === "mobile") {
    await page.getByRole("button", { name: "文档预览", exact: true }).click();
  }
  const preview = page.getByRole("region", { name: "文档预览", exact: true });
  await expect(preview.locator("canvas").first()).toBeVisible({ timeout: 12000 });
  await expect(preview).toContainText("等待转换的文档.docx");
});

test("技术专题展示综合摘要、独立任务和逐条要求，并能打开原文", async ({ page }, info) => {
  // 按语义定位当前专题，避免依赖组件库的内部活动面板类名。
  const body = page.getByRole("region", { name: "技术要求", exact: true })
    .locator(".module-markdown");
  await expect(body.getByRole("heading", { name: "技术方案要求", exact: true })).toBeVisible();
  await expect(body.getByText("制定分阶段迁移方案并说明回退与服务保障。", { exact: true })).toBeVisible();
  await expect(body.getByText("必须提供可执行的回退方案。", { exact: true })).toBeVisible();
  await expect(body).not.toContainText("内部业务投影");
  await expect(body).not.toContainText("原始段落：");
  await page.screenshot({ path: info.outputPath("synthesis-review-collapsed.png"), fullPage: true });
  await expect(page.getByText("附件B未提供，兼容性细则待核对。", { exact: true })).not.toBeVisible();
  await page.getByRole("button", { name: "查看本专题待核对事项" }).click();
  await expect(page.getByText("附件B未提供，兼容性细则待核对。", { exact: true })).toBeVisible();
  await expect(page.getByText(modules[0]!.research_summary!, { exact: true })).not.toBeVisible();
  await page.getByRole("tab", { name: "解析正文", exact: true }).click();
  await page.locator(".module-operations > summary").click();
  await page.getByText("查看分析过程", { exact: true }).click();
  await expect(page.getByText(modules[0]!.research_summary!, { exact: true })).toBeVisible();
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
  await selectModule(page, 2);
  const table = page.getByRole("region", { name: "评分办法", exact: true })
    .locator(".module-result-list");
  await expect(table.getByRole("heading", { name: "业绩评分" })).toBeVisible();
  await expect(table.locator(".result-score")).toHaveText("满分 6分");
  await expect(table.locator("dt")).toHaveText(["评分项", "评分标准（原文摘录）"]);
  await expect(table.getByRole("listitem")).toHaveCount(2);
  await expect(table).toContainText("最高6分；须提供合同及验收证明。");
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await table.scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("synthesis-scoring.png"), fullPage: true });
});

test("共享原文的评分事项往返定位仍回到评分，页码入口可见", async ({ page }) => {
  await selectModule(page, 2);
  const row = page.locator('[data-report-item="score"]');
  const locate = row.getByRole("button", { name: /^定位：/ });
  await expect(locate).toContainText("第 1 页");
  await locate.click();
  const viewer = page.getByRole("region", { name: "引用原文", exact: true });
  await expect(viewer).toBeVisible();
  const badge = viewer.locator("[data-annotation-badge]").first();
  await expect(badge).toBeVisible();
  await badge.click();
  await expect(page.getByRole("tablist", { name: "解析专题", exact: true }).locator('[data-module-id="2"]')).toHaveAttribute("aria-selected", "true");
  await expect(row).toBeVisible();
  await expect(row).toHaveClass(/report-item-active/);
});

test("格式专题保留三层材料结构，项目提供文档预览入口", async ({ page }, info) => {
  await selectModule(page, 3);
  await page.getByRole("button", { name: "展开全部材料" }).click();
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
  await selectModule(page, 1);
  await expect(page.getByText("专题接口暂时不可用", { exact: true })).toBeVisible();
  await expect(page.getByText("制定分阶段迁移方案并说明回退与服务保障。", { exact: true })).toHaveCount(0);
  failed = false;
  await page.getByRole("button", { name: "重新加载", exact: true }).click();
  await expect(page.getByText("制定分阶段迁移方案并说明回退与服务保障。", { exact: true })).toBeVisible();
});

test("运行中的维度通过轮询显示新保存的记录，依据撤销后清除正文", async ({ page }) => {
  let withdrawn = false;
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({
    json: report(1, { status: "running", created_at: "2026-10-16T10:00:00Z" }),
  }));
  let reads = 0;
  await page.route("**/api/v1/analysis/reports/1/modules/tech_requirement_parsing/records", (route) => {
    const data = records(modules[0]!);
    if (withdrawn || ++reads === 1) data.records = [];
    return route.fulfill({ json: data });
  });
  await page.reload();
  await selectModule(page, 1);
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
  await page.route("**/api/v1/analysis/reports/2", (route) => route.fulfill({
    json: report(2, { modules: [{ ...modules[0]!, items: [] }] }),
  }));
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

test("字段逐项显示，历史数组保留原内容且能从待核对跳回", async ({ page }) => {
  const data = records(modules[0]!);
  data.output_schema.sections = [{ title: "项目信息", layout: "table", columns: ["字段", "内容"] }];
  data.records = [
    { ...data.records[0]!, id: "single", key: "single", kind: "fact", group: "项目信息",
      title: "采购名称", content: { 字段: "项目名称", 内容: "通信采购项目" } },
    { ...data.records[0]!, id: "compound", key: "compound", kind: "fact", group: "项目信息",
      title: "历史概况", content: { 字段: ["预算", "服务期"], 内容: ["100万元", "三年"] } },
  ];
  await page.route("**/api/v1/analysis/reports/1/modules/tech_requirement_parsing/records", (route) => route.fulfill({ json: data }));
  await page.reload();
  const single = page.locator('[data-report-item="single"]');
  await expect(single.locator("dt")).toHaveText("项目名称");
  await expect(single.locator("dd")).toHaveText("通信采购项目");
  const compound = page.locator('[data-report-item="compound"]');
  await expect(compound.locator(".record-attention")).toContainText("未声明逐项对应关系");
  await expect(compound.locator(".compound-labels > span")).toHaveText(["预算", "服务期"]);
  await expect(compound.locator(".result-points > li")).toHaveText(["100万元", "三年"]);
  await page.getByRole("checkbox", { name: "仅待核对条目" }).check();
  await expect(single).toHaveCount(0);
  await expect(compound).toBeVisible();
  await page.getByRole("button", { name: "查看本专题待核对事项" }).click();
  await page.getByRole("button", { name: "查看相关事项", exact: true }).click();
  await expect(compound).toHaveClass(/report-item-active/);
  await expect(page.getByRole("checkbox", { name: "仅待核对条目" })).not.toBeChecked();
});

test("多处同页依据保留完整摘录，去重后仍能准确定位第二处", async ({ page }) => {
  const data = records(modules[0]!);
  const second = { ...citation, element_id: 2, anchor: "p1b2", quote: "第二处完整依据：例外条件仍须保留。" };
  data.evidence = { source: citation, duplicate: citation, second };
  data.records[1]!.evidence_ids = ["source", "duplicate", "second"];
  await page.route("**/api/v1/analysis/reports/1/modules/tech_requirement_parsing/records", (route) => route.fulfill({ json: data }));
  await page.route("**/api/v1/knowledge/citations/resolve", (route) => route.fulfill({ json: second }));
  await page.reload();
  await page.locator('[data-report-item="migration"]').getByRole("button", { name: "查看 2 处依据" }).click();
  const picker = page.getByRole("region", { name: "选择原文依据" });
  await expect(picker.getByRole("button")).toHaveCount(2);
  await expect(picker).toContainText(citation.quote);
  await expect(picker).toContainText(second.quote);
  const resolved = page.waitForRequest("**/knowledge/citations/resolve");
  await picker.getByRole("button").filter({ hasText: second.quote }).click();
  expect((await resolved).postDataJSON()).toMatchObject({ element_id: 2, anchor: "p1b2" });
  await expect(page.getByRole("region", { name: "引用原文", exact: true })).toContainText(second.quote);
});

test("折叠材料命中搜索后展开父链，清除筛选恢复完整目录", async ({ page }) => {
  await selectModule(page, 3);
  await page.getByRole("button", { name: "收起全部材料" }).click();
  await page.getByLabel("搜索解析结果").fill("回退条件");
  await expect(page.locator('[data-report-item="fallback"]')).toBeVisible();
  await expect(page.getByText("说明回退条件与操作顺序。", { exact: true })).toBeVisible();
  await expect(page.locator(".results-subfilters")).toContainText("1 条匹配");
  await expect(page.locator('[data-report-item="technical"] > details > summary')).toContainText("仅供定位");
  await page.getByRole("button", { name: "清除筛选" }).click();
  await expect(page.locator(".results-subfilters")).toContainText("3 条匹配");
});

test("标段筛选含公共要求且排除未知范围，修订入口清除筛选并跳转", async ({ page }) => {
  const data = records(modules[0]!);
  const base = data.records[1]!;
  data.records = [
    { ...base, id: "old", key: "old", title: "原服务期限", scope: { kind: "lots", lot_refs: ["A"] } },
    { ...base, id: "new", key: "new", title: "新服务期限", scope: { kind: "lots", lot_refs: ["A"] } },
    { ...base, id: "other", key: "other", title: "其它标段要求", scope: { kind: "lots", lot_refs: ["A1"] } },
    { ...base, id: "common", key: "common", title: "公共要求" },
    { ...base, id: "unknown", key: "unknown", title: "范围未决", scope: { kind: "unknown", lot_refs: [] } },
    { ...base, id: "revision", key: "revision", title: "期限修订关系", kind: "relation",
      predicate: "supersedes", subject_key: "new", object_key: "old", scope: { kind: "lots", lot_refs: ["A"] } },
  ];
  await page.route("**/api/v1/analysis/reports/1/modules/tech_requirement_parsing/records", (route) => route.fulfill({ json: data }));
  // 明确的修订跳转以已通过范围与端点校验的快照为准。
  const resolved = data.records.map((record) => ({ ...record, citations: [citation],
    scope: { ...record.scope, lot_ids: record.scope.lot_refs.map((ref) => ref === "A" ? 1 : 2) } }));
  await page.route("**/api/v1/analysis/reports/1/data", (route) => route.fulfill({ json: {
    report_id: 1, snapshot_id: 1, revision: 1, schema_version: "1", stale: false,
    data: { schema_version: "1", readiness: "partial", facts: [], format_nodes: [], coverage: [], gaps: [],
      lots: [1, 2].map((id) => ({ ...resolved[0], id: `lot-${id}`, key: `lot-${id}`, kind: "lot", lot_id: id,
        title: id === 1 ? "A" : "A1", code: id === 1 ? "A" : "A1", aliases: [] })),
      requirements: resolved.filter((record) => record.kind === "requirement"),
      relations: resolved.filter((record) => record.kind === "relation").map((record) => ({
        ...record, subject_id: "new", object_id: "old",
      })),
    },
  } }));
  await page.reload();
  await page.getByLabel("筛选适用范围").selectOption("id:1");
  await expect(page.locator('[data-report-item="common"]')).toBeVisible();
  await expect(page.locator('[data-report-item="other"]')).toHaveCount(0);
  await expect(page.locator('[data-report-item="unknown"]')).toHaveCount(0);
  await page.getByLabel("搜索解析结果").fill("原服务期限");
  await expect(page.locator('[data-report-item="new"]')).toHaveCount(0);
  await page.locator('[data-report-item="old"]').getByRole("button", { name: "修订条款：新服务期限" }).click();
  await expect(page.getByLabel("筛选适用范围")).toHaveValue("");
  await expect(page.getByLabel("搜索解析结果")).toHaveValue("");
  await expect(page.locator('[data-report-item="new"]')).toHaveClass(/report-item-active/);
});

test("记录级缺口按事项归回专题，数量与当前范围一致并保留检查进度", async ({ page }) => {
  const scope = { kind: "common", lot_refs: [], lot_ids: [] };
  const gap = { code: "unresolved_reference", detail: "缺少迁移附件", module_key: "tech_requirement_parsing", topic: "migration", scope };
  await page.route("**/api/v1/analysis/reports/1/data", (route) => route.fulfill({ json: {
    report_id: 1, snapshot_id: 1, revision: 1, schema_version: "1", stale: false,
    data: { schema_version: "1", lots: [], facts: [], requirements: [], format_nodes: [], relations: [], readiness: "partial",
      gaps: [gap, { ...gap }, { code: "unknown_condition", record_id: "score", detail: "业绩时间边界待核对", scope }],
      coverage: [{ module_key: "tech_requirement_parsing", topic: "migration", title: "迁移附件", status: "pending", scope, detail: "附件本体尚未提供" }],
    },
  } }));
  await page.reload();
  await page.getByRole("tab", { name: "待核对 · 1 组", exact: true }).click();
  await expect(page.getByText("缺少迁移附件", { exact: true })).toHaveCount(1);
  await expect(page.getByText("业绩时间边界待核对", { exact: true })).toHaveCount(0);
  await page.getByText("查看专题检查进度", { exact: true }).click();
  await expect(page.getByText("附件本体尚未提供", { exact: true })).toBeVisible();
  await selectModule(page, 2);
  await expect(page.getByText("业绩时间边界待核对", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "查看相关事项", exact: true }).click();
  await expect(page.locator('[data-report-item="score"]')).toHaveClass(/report-item-active/);
  await selectModule(page, 0);
  await expect(page.getByRole("tab", { name: "待核对 · 2 组", exact: true })).toBeVisible();
});

test("无专题的失败报告显示原因，桌面原文可收起并由引用重新展开", async ({ page }, info) => {
  if (info.project.name === "desktop") {
    await page.getByRole("button", { name: "收起原文，专注结果" }).click();
    await expect(page.locator(".analysis-document")).not.toBeVisible();
    await page.locator('[data-report-item="migration"]').getByRole("button", { name: /^定位：/ }).click();
    await expect(page.locator(".analysis-document")).toBeVisible();
    await page.getByLabel("原文区域宽度").fill("45");
    await expect(page.locator(".analysis-split")).toHaveAttribute("style", /45%/);
  }
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: report(1, {
    status: "failed", modules: [], error_message: "HTTP 429 上游限流", data_schema_version: null,
  }) }));
  await page.reload();
  await expect(page.getByText("模型服务暂时限流", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "补跑未完成模块" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "全部重新解析" })).toHaveCount(0);
});

test("未决关系保留正文与依据，但不按旧 key 连接已更新条款", async ({ page }) => {
  const data = records(modules[0]!);
  const base = data.records[1]!;
  data.records = [
    { ...base, id: "old", key: "old", title: "原期限", content: { 要求摘要: "服务一年" } },
    { ...base, id: "new", key: "new", title: "现条款", content: { 要求摘要: "服务三年" } },
    { ...base, id: "relation", key: "relation", title: "旧修订关系", kind: "relation",
      content: { 要求摘要: "服务两年替代服务一年" }, predicate: "supersedes", subject_key: "new", object_key: "old" },
  ];
  await page.route("**/api/v1/analysis/reports/1/modules/tech_requirement_parsing/records", (route) => route.fulfill({ json: data }));
  await page.route("**/api/v1/analysis/reports/1/data", (route) => route.fulfill({ json: {
    report_id: 1, snapshot_id: 1, revision: 1, schema_version: "1", stale: false,
    data: { schema_version: "1", lots: [], facts: [], requirements: [], format_nodes: [], relations: [], coverage: [], readiness: "partial",
      gaps: [{ code: "unresolved_relation", record_id: "relation", detail: "关系端点或适用范围未确认",
        scope: { kind: "common", lot_ids: [], lot_refs: [] } }],
    },
  } }));
  await page.reload();
  await expect(page.getByRole("tab", { name: "待核对 · 1 组", exact: true })).toBeVisible();
  const relation = page.locator('[data-report-item="relation"]');
  await expect(relation).toContainText("服务两年替代服务一年");
  await expect(page.getByRole("button", { name: "修订条款：现条款" })).toHaveCount(0);
  await expect(relation).toContainText("关系端点或适用范围尚未确认");
  await expect(relation.getByRole("button", { name: /^定位：/ })).toBeVisible();
});

test("未知 A、B 标段的相同缺口分别保留并显示原文指向", async ({ page }) => {
  await page.route("**/api/v1/analysis/reports/1/data", (route) => route.fulfill({ json: {
    report_id: 1, snapshot_id: 1, revision: 1, schema_version: "1", stale: false,
    data: { schema_version: "1", lots: [], facts: [], requirements: [], format_nodes: [], relations: [], coverage: [], readiness: "partial",
      gaps: ["A标段", "B标段", "A标段"].map((ref) => ({ code: "coverage_pending", detail: "此主题尚未完成核对",
        module_key: "tech_requirement_parsing", topic: "实施条件", scope: { kind: "unknown", lot_ids: [], lot_refs: [ref] } })),
    },
  } }));
  await page.reload();
  await page.getByRole("tab", { name: "待核对 · 2 组", exact: true }).click();
  const board = page.getByRole("region", { name: "待核对事项" });
  await expect(board.getByText("此主题尚未完成核对", { exact: true })).toHaveCount(2);
  await expect(board).toContainText("A标段");
  await expect(board).toContainText("B标段");
});

test("重复点击同一原文角标仍滚回已选结果", async ({ page }, info) => {
  const data = records(modules[0]!);
  data.records = Array.from({ length: 16 }, (_, index) => ({ ...data.records[1]!, id: `item-${index}`, key: `item-${index}`,
    title: `任务 ${index}`, content: { 要求摘要: `任务 ${index} 的要求` } }));
  await page.route("**/api/v1/analysis/reports/1/modules/tech_requirement_parsing/records", (route) => route.fulfill({ json: data }));
  await page.reload();
  const target = page.locator('[data-report-item="item-0"]');
  await target.getByRole("button", { name: /^定位：/ }).click();
  const badge = page.locator("[data-annotation-badge]").first();
  await expect(badge).toBeVisible();
  await badge.click();
  await expect(target).toBeInViewport();
  await page.locator(".analysis-content").evaluate((element) => { element.scrollTop = element.scrollHeight; });
  await expect(target).not.toBeInViewport();
  if (info.project.name === "mobile") await page.getByRole("button", { name: "引用原文", exact: true }).click();
  await badge.click();
  await expect(target).toBeInViewport();
  await expect(target).toHaveClass(/report-item-active/);
});

test("父子材料同时命中关键词时展开全部命中节点", async ({ page }) => {
  const data = records(modules[2]!);
  for (const record of data.records) record.content = { 编制要求: `共同关键词：${record.title}的编制要求` };
  await page.route("**/api/v1/analysis/reports/1/modules/bid_format_outline_parsing/records", (route) => route.fulfill({ json: data }));
  await page.reload();
  await selectModule(page, 3);
  await page.getByRole("button", { name: "收起全部材料" }).click();
  await page.getByLabel("搜索解析结果").fill("共同关键词");
  await expect(page.locator(".results-subfilters")).toContainText("3 条匹配");
  await expect(page.getByText("共同关键词：回退计划的编制要求", { exact: true })).toBeVisible();
});

test("模块标签和三种重解析操作直接可用，提交范围互不混淆", async ({ page }) => {
  const requests: unknown[] = [];
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: report(1, {
    status: "partial", modules: modules.map((module, index) => ({ ...module, items: [],
      status: ["completed", "failed", "canceled"][index]!,
    })),
  }) }));
  await page.route("**/api/v1/analysis/reports/1/retry", (route) => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({ json: { id: 1, status: "pending" } });
  });
  await page.reload();
  const tabs = page.getByRole("tablist", { name: "解析专题", exact: true });
  await expect(tabs.getByRole("tab")).toHaveCount(4);
  await expect(page.getByRole("combobox", { name: "解析专题" })).toHaveCount(0);
  await tabs.locator('[data-module-id="1"]').focus();
  await page.keyboard.press("ArrowRight");
  await expect(tabs.locator('[data-module-id="2"]')).toHaveAttribute("aria-selected", "true");
  await page.getByRole("button", { name: "重新解析本模块", exact: true }).click();
  await expect.poll(() => requests).toEqual([{ module_keys: ["scoring_standard_parsing"] }]);
  await page.getByRole("button", { name: "补跑未完成模块", exact: true }).click();
  await expect.poll(() => requests).toHaveLength(2);
  expect(requests[1]).toEqual({});
  await page.getByRole("button", { name: "全部重新解析", exact: true }).click();
  await expect.poll(() => requests).toHaveLength(3);
  expect(requests[2]).toEqual({ module_keys: modules.map((module) => module.module_key) });
});
