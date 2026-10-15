import { test, expect } from "@playwright/test";
import type { AnalysisField, AnalysisModule, AnalysisOutput, Citation } from "../src/types/knowledge";
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
test.beforeEach(async ({ page }) => {
  errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await mockApi(page);
  await page.route("**/api/v1/projects/1/analysis", (route) => route.fulfill({ json: {
    analysis_category: "goods", analysis_topics: [], lots: [], sources: [],
    reports: [{ id: 1, status: "completed" }], categories: { goods: "货物" }, topics: {},
  } }));
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: {
    id: 1, status: "completed", category: "goods", topics: [], coverage: {}, modules,
    created_at: "2026-10-14T10:00:00Z", finished_at: "2026-10-14T10:05:00Z", stale: false,
    error_message: null, runtime_retired: false,
  } }));
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
