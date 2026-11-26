import { test, expect, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import type {
  AnalysisField, AnalysisModule, AnalysisOutput, AnalysisReport, AnalysisReportDetail, Citation, KnowledgeSource, ModuleRecords,
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
    quality_issues: [{ issue_id: "missing-attachment-b", kind: "reference", action: "provide_input",
      topic: "附件B", target: "兼容性细则", detail: "附件B未提供，兼容性细则待核对。" }],
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

/** 夹具保留独立记录正文；HTTP详情按现行契约只返回状态，防止旧投影掩盖取数错误。 */
function report(id: number, overrides: Partial<AnalysisReport> = {}): AnalysisReportDetail {
  const result: AnalysisReport = {
    id, project_id: 1, allow_partial: false, quality_status: "self_check_passed",
    runtime_version: "agent-led-v1", status: "completed", category: "goods", topics: [], coverage: {},
    modules, data_schema_version: "1",
    created_at: "2026-10-14T10:00:00Z", stale: false,
    error_message: null, ...overrides,
  };
  return { ...result, modules: result.modules.map(({ items: _items, ...module }) => module) };
}

let errors: string[];

test("单Agent进度展示草稿与自查，保留上一轮正文", async ({ page }) => {
  const selected: AnalysisModule = { ...modules[0]!, status: "partial", progress: {
    protocol: "skill-agent-v1", activity: "record_review",
    draft_count: 4, reviewed_count: 3, unresolved_issues: 1,
  } };
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: report(1, {
    status: "partial", modules: [{ ...selected, items: [] }],
  }) }));
  // records接口仍是上一轮正式数据，不能覆盖报告携带的最新工作进度。
  await mockRecords(page, 1, records(selected));
  await page.goto("/projects/1");
  await selectModule(page, 1);
  await expect(page.getByText(/已保存 4 条草稿.*当前版本已自查 3 条/)).toBeVisible();
  await expect(page.getByText(/未决问题 1 项/)).toBeVisible();
  await expect(page.getByText(/本次执行已中断，可补跑继续处理/)).toBeVisible();
  await expect(page.getByText("完成现有平台升级与迁移。", { exact: true })).toBeVisible();
  await expect(page.getByText(/已用修复.*次/)).toHaveCount(0);
});

function records(module: AnalysisModule): ModuleRecords {
  return {
    schema_version: "1", module_key: module.module_key, status: module.status,
    quality_status: module.quality_status ?? "self_check_passed", quality_issues: module.quality_issues ?? [],
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
    })),
  };
}

async function mockRecords(
  page: Page, reportId: number,
  value: ModuleRecords | ((key: string) => ModuleRecords | { error: string }
    | Promise<ModuleRecords | { error: string }>),
  onlyKey?: string,
) {
  await page.route(`**/api/v1/analysis/reports/${reportId}/records`, async (route) => {
    const payload = route.request().postDataJSON() as {
      module_keys: string[]; versions: Record<string, string>;
    };
    const updates = await Promise.all(payload.module_keys.map(async (key) => {
      const data = onlyKey && key !== onlyKey ? records(modules.find((module) => module.module_key === key)!)
        : typeof value === "function" ? await value(key) : value;
      if ("error" in data) return { module_key: key, error: data.error };
      const body = { ...data, module_key: key };
      // 模拟服务端核验后按完整响应生成版本，轮询用例实际经历省略与刷新正文。
      const version = createHash("sha256").update(JSON.stringify(body)).digest("hex");
      return { module_key: key, version, ...(payload.versions[key] === version ? {} : { data: body }) };
    }));
    await route.fulfill({ json: { modules: updates } });
  });
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
  await mockRecords(page, 1, (key) => records(modules.find((module) => module.module_key === key)!));
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

for (const failedStep of ["status", "report"] as const) {
  test(`${failedStep}前置读取失败清除旧正文与缓存，恢复后重新读取完整结果`, async ({ page }) => {
    await expect(page.locator('[data-report-item="background"]')).toBeVisible();
    let failed = true;
    await page.route("**/api/v1/projects/1/analysis", (route) =>
      failed && failedStep === "status"
        ? route.fulfill({ status: 403, json: { error: { message: "分析状态不可访问" } } })
        : route.fulfill({ json: {
          analysis_category: "goods", analysis_topics: [], lots: [], sources: [],
          reports: [{ id: 1, status: "completed" }], categories: { goods: "货物" }, topics: {},
        } }));
    await page.route("**/api/v1/analysis/reports/1", (route) =>
      failed && failedStep === "report"
        ? route.fulfill({ status: 404, json: { error: { message: "报告不可访问" } } })
        : route.fulfill({ json: report(1) }));
    await page.getByRole("button", { name: "刷新结果", exact: true }).click();
    await expect(page.getByRole("alert").filter({
      has: page.getByRole("button", { name: "刷新状态", exact: true }),
    })).toContainText("不可访问");
    await expect(page.locator('[data-report-item="background"]')).toHaveCount(0);
    failed = false;
    const recovered = page.waitForRequest("**/api/v1/analysis/reports/1/records");
    await page.getByRole("button", { name: "刷新状态", exact: true }).click();
    expect((await recovered).postDataJSON().versions).toEqual({});
    await expect(page.locator('[data-report-item="background"]')).toBeVisible();
  });
}

for (const message of ["服务暂时无法处理请求", "关联资料保存失败"]) {
  test(`关联操作失败提示不被刷新恢复清除：${message}`, async ({ page }) => {
    await expect(page.locator('[data-report-item="background"]')).toBeVisible();
    let readFailed = true;
    await page.route("**/api/v1/analysis/reports/1", (route) => readFailed
      ? route.fulfill({ status: 500, json: { error: { message: "服务暂时无法处理请求" } } })
      : route.fulfill({ json: report(1) }));
    await page.getByRole("button", { name: "刷新结果", exact: true }).click();
    const alert = page.getByRole("alert").filter({
      has: page.getByRole("button", { name: "刷新状态", exact: true }),
    });
    await expect(alert).toContainText("服务暂时无法处理请求");
    await expect(page.locator('[data-report-item="background"]')).toHaveCount(0);
    readFailed = false;
    let writes = 0;
    await page.route("**/api/v1/projects/1/knowledge/collections", (route) => {
      writes += 1;
      return route.fulfill({ status: 500, json: { error: { message } } });
    });
    const checkbox = page.getByLabel("测试知识库", { exact: true });
    // 保存失败会恢复受控复选框，不能用check()假定这次操作已经成功。
    await checkbox.click();
    await expect(page.locator('[data-report-item="background"]')).toBeVisible();
    await expect(alert).toContainText(message);
    await expect(checkbox).not.toBeChecked();
    expect(writes).toBe(1);
  });
}

for (const scenario of [
  { step: "status", work: "analysis", network: false },
  { step: "report", work: "analysis", network: false },
  { step: "status", work: "analysis", network: true },
  { step: "report", work: "files", network: false },
] as const) {
  test(`${scenario.work}/${scenario.step}/${scenario.network}临时失败清除正文后自动恢复轮询`, async ({ page }) => {
    let failed = false;
    await page.route("**/api/v1/projects/1/analysis", (route) => {
      if (failed && scenario.step === "status") {
        return scenario.network ? route.abort("failed") : route.fulfill({ status: 503,
          json: { error: { message: "网关暂时不可用" } } });
      }
      return route.fulfill({ json: {
        analysis_category: "goods", analysis_topics: [], lots: [],
        sources: scenario.work === "files" ? [{ ...citation, state: "processing",
          index_status: null, index_error: null, error_message: null, embedding_model_id: null }] : [],
        reports: [{ id: 1, status: scenario.work === "analysis" ? "running" : "completed" }],
        categories: { goods: "货物" }, topics: {},
      } });
    });
    await page.route("**/api/v1/analysis/reports/1", (route) =>
      failed && scenario.step === "report"
        ? route.fulfill({ status: 503, json: { error: { message: "网关暂时不可用" } } })
        : route.fulfill({ json: report(1, { status: scenario.work === "analysis" ? "running" : "completed" }) }));
    await page.reload();
    await expect(page.locator('[data-report-item="background"]')).toBeVisible();
    failed = true;
    await page.getByRole("button", { name: "刷新结果", exact: true }).click();
    const error = page.getByRole("alert").filter({
      has: page.getByRole("button", { name: "刷新状态", exact: true }),
    });
    await expect(error).toBeVisible();
    await expect(page.locator('[data-report-item="background"]')).toHaveCount(0);
    failed = false;
    // 不触发用户操作，只有仍在运行的定时器才能发起恢复请求。
    const recovered = await page.waitForRequest("**/api/v1/analysis/reports/1/records", { timeout: 10000 });
    expect(recovered.postDataJSON().versions).toEqual({});
    await expect(page.locator('[data-report-item="background"]')).toBeVisible();
    await expect(error).toHaveCount(0);
  });
}

test("运行中遇到永久访问错误停止轮询并清除正文", async ({ page }) => {
  await page.route("**/api/v1/projects/1/analysis", (route) => route.fulfill({ json: {
    analysis_category: "goods", analysis_topics: [], lots: [], sources: [],
    reports: [{ id: 1, status: "running" }], categories: { goods: "货物" }, topics: {},
  } }));
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: report(1, { status: "running" }) }));
  await page.reload();
  await expect(page.locator('[data-report-item="background"]')).toBeVisible();
  let rejected = 0;
  await page.route("**/api/v1/projects/1/analysis", (route) => {
    rejected += 1;
    return route.fulfill({ status: 403, json: { error: { message: "项目访问已撤销" } } });
  });
  await page.getByRole("button", { name: "刷新结果", exact: true }).click();
  await expect(page.locator('[data-report-item="background"]')).toHaveCount(0);
  await page.waitForTimeout(3500);
  expect(rejected).toBe(1);
});

test("状态列表已无报告时清除旧正文", async ({ page }) => {
  await expect(page.locator('[data-report-item="background"]')).toBeVisible();
  await page.route("**/api/v1/projects/1/analysis", (route) => route.fulfill({ json: {
    analysis_category: "goods", analysis_topics: [], lots: [], sources: [],
    reports: [],
    categories: { goods: "货物" }, topics: {},
  } }));
  await page.getByRole("button", { name: "刷新结果", exact: true }).click();
  await expect(page.locator('[data-report-item="background"]')).toHaveCount(0);
});

test("一次刷新合并全部专题，未变化正文只返回版本并保留跨专题结果", async ({ page }) => {
  await expect(page.locator('[data-report-item="background"]')).toBeVisible();
  const requests: string[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (/^\/api\/v1\/(projects\/1\/analysis|analysis\/reports\/1(?:\/records)?)$/.test(path)) {
      requests.push(path);
    }
  });
  const first = page.waitForResponse("**/api/v1/analysis/reports/1/records");
  await page.reload();
  expect((await (await first).json()).modules).toHaveLength(3);
  await expect(page.locator('[data-report-item="background"]')).toBeVisible();
  expect(requests.filter((path) => path.endsWith("/records"))).toHaveLength(1);
  // 开发模式首次挂载可能取消一次状态请求；统计完成初始化后的手动刷新。
  requests.length = 0;
  const next = page.waitForResponse("**/api/v1/analysis/reports/1/records");
  await page.getByRole("button", { name: "刷新结果", exact: true }).click();
  const unchanged = await (await next).json();
  expect(unchanged.modules.every((module: { data?: unknown }) => module.data === undefined)).toBe(true);
  expect(requests).toHaveLength(3);
  await selectModule(page, 2);
  await expect(page.locator('[data-report-item="score"]')).toContainText("同类项目业绩");
  await selectModule(page, 3);
  await expect(page.locator('[data-report-item="technical"]')).toContainText("独立编制技术文件");
});

test("执行完成与资料质量分别展示，缺件在材料未变化时不重复补跑", async ({ page }) => {
  const selected = { ...modules[0]!, quality_status: "needs_input" as const, quality_issues: [{
    issue_id: "missing-announcement", kind: "reference", action: "provide_input" as const,
    topic: "opening", detail: "第一章招标公告未提供，具体日期待核对", target: "第一章招标公告",
  }] };
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: report(1, {
    status: "completed", quality_status: "needs_input", modules: [{ ...selected, items: [] }],
  }) }));
  await mockRecords(page, 1, { ...records(selected), quality_status: selected.quality_status,
      quality_issues: selected.quality_issues });
  await page.reload();
  await expect(page.locator(".results-report-bar")).toContainText("已完成");
  await expect(page.locator(".results-report-bar")).toContainText("资料待核对");
  await expect(page.getByRole("button", { name: "补跑未完成模块", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "重新解析本模块", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: /待核对/ }).click();
  await expect(page.getByText("第一章招标公告未提供，具体日期待核对", { exact: true })).toBeVisible();
});

test("无可靠摘录时仍直接打开真实原文块，不展示空摘录或切片选择器", async ({ page }) => {
  const data = records(modules[0]!);
  data.evidence.source = { ...citation, quote: "", excerpts: [], excerpt_status: "block_only" };
  await mockRecords(page, 1, data, "tech_requirement_parsing");
  await page.reload();
  await page.locator('[data-report-item="background"]').getByRole("button", { name: /^定位/ }).click();
  const viewer = page.getByRole("region", { name: "引用原文", exact: true });
  await expect(viewer.locator("canvas").first()).toBeVisible();
  await expect(viewer.locator(".citation-excerpt")).toHaveCount(0);
  await expect(viewer.locator("[data-active-evidence]")).toHaveCount(1);
});

test("逐条依据校验失败只阻断当前专题，仍能切换到其它有效专题", async ({ page }) => {
  const invalid = records(modules[0]!);
  invalid.records[0]!.content_evidence = { 背景: [] };
  await mockRecords(page, 1, invalid, "tech_requirement_parsing");
  await page.reload();
  await selectModule(page, 1);
  await expect(page.getByRole("region", { name: "技术要求", exact: true }))
    .toContainText("专题结果的逐条依据不完整，请重新解析本模块");
  await selectModule(page, 2);
  await expect(page.locator('[data-report-item="score"]')).toContainText("同类项目业绩");
});

test("点击合并定位后可打开当前事项的全部摘录，切换事项与位置不混入其它摘录", async ({ page }, info) => {
  const first = { ...citation, quote: "本项目预算为2130万元。" };
  const label = { ...citation, quote: "本项目建设预算：" };
  const condition = { ...citation, quote: "预算调整须提交审批记录。" };
  const unrelated = { ...citation, quote: "另一事项的质保说明。" };
  const next = { ...citation, element_id: 2, anchor: "p1b2", quote: "服务期为2年。" };
  const data = records(modules[0]!);
  data.evidence = { first, label, condition, unrelated, next };
  data.records = [
    { ...data.records[0]!, content: { 背景: ["预算2130万元", "服务期2年"] },
      evidence_ids: ["first", "label", "condition", "next"], content_evidence: { 背景: [["first", "label"], ["next"]] } },
    { ...data.records[0]!, id: "another", key: "another", title: "质保事项", content: { 背景: "质保说明" },
      evidence_ids: ["unrelated"], content_evidence: { 背景: [["unrelated"]] } },
  ];
  await mockRecords(page, 1, data, "tech_requirement_parsing");
  // 正式 resolve 只返回位置身份，摘录应继续来自当前事项，不能被其它事项的同位置引用替代。
  await page.route("**/api/v1/knowledge/citations/resolve", (route) => {
    const { quote: _quote, ...resolved } = route.request().postDataJSON().element_id === 2 ? next : first;
    return route.fulfill({ json: resolved });
  });
  await page.reload();
  const buttons = page.locator('[data-report-item="background"] .value-locates-inline button');
  await expect(buttons).toHaveCount(2);
  const viewer = page.getByRole("region", { name: "引用原文", exact: true });
  await buttons.first().click();
  const summary = viewer.getByText("查看本事项的 3 条原文摘录", { exact: true });
  await summary.click();
  await expect(viewer.locator(".citation-excerpt blockquote")).toHaveText([first.quote, label.quote, condition.quote]);
  await expect(viewer.locator(".citation-excerpt")).not.toContainText(unrelated.quote);
  await expect(viewer.locator(".citation-excerpt")).not.toContainText(next.quote);
  await expect(viewer.locator("[data-active-evidence]")).toHaveCount(1);
  await viewer.screenshot({ path: info.outputPath("merged-citation-excerpts.png") });
  // 多段摘录共用有限高度，手机也必须能在该区域滚到最后一段。
  const lastQuote = viewer.locator(".citation-excerpt blockquote").last();
  await lastQuote.scrollIntoViewIfNeeded();
  await expect(lastQuote).toBeInViewport();
  await viewer.screenshot({ path: info.outputPath("merged-citation-excerpts-last.png") });
  await summary.click();
  await expect(lastQuote).not.toBeVisible();
  await summary.focus();
  await page.keyboard.press("Enter");
  await expect(lastQuote).toBeVisible();
  if (info.project.name === "mobile") await page.getByRole("button", { name: "分析内容", exact: true }).click();
  await buttons.nth(1).click();
  await expect(viewer.locator(".citation-excerpt")).toHaveText(next.quote);
  if (info.project.name === "mobile") await page.getByRole("button", { name: "分析内容", exact: true }).click();
  await page.locator('[data-report-item="another"] .value-locates-inline button').click();
  await expect(viewer.locator(".citation-excerpt")).toHaveText(unrelated.quote);
});

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
  await expect(preview.locator("[data-active-evidence], [data-annotation-badge]")).toHaveCount(0);
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
  await expect(body.getByRole("table")).toHaveCount(2);
  await expect(body.getByRole("table", { name: "技术方案要求", exact: true }).getByRole("columnheader"))
    .toHaveText(["章节来源", "要求摘要", "关键要求"]);
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
    .getByRole("table", { name: "商务评分标准", exact: true });
  await expect(table.getByRole("heading", { name: "业绩评分" })).toBeVisible();
  await expect(table.locator('td[data-label="满分分值"]')).toHaveText("6分");
  await expect(table.getByRole("columnheader")).toHaveText(["评分项", "满分分值", "评分标准（原文摘录）"]);
  await expect(table.getByRole("listitem")).toHaveCount(2);
  await expect(table).toContainText("最高6分；须提供合同及验收证明。");
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await table.scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("synthesis-scoring.png"), fullPage: true });
});

test("共享原文的评分事项往返定位仍回到评分，图标保留页码提示", async ({ page }) => {
  await selectModule(page, 2);
  const row = page.locator('[data-report-item="score"]');
  const locate = row.getByRole("button", { name: /^定位：/ });
  await expect(locate).toHaveText("");
  await expect(locate).toHaveAttribute("title", /第 1 页/);
  await expect(locate.locator("svg")).toHaveCount(1);
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
  await mockRecords(page, 1, () => failed ? { error: "专题接口暂时不可用" }
    : records(modules[0]!), "tech_requirement_parsing");
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
  await mockRecords(page, 1, () => {
    const data = records(modules[0]!);
    if (withdrawn || ++reads === 1) data.records = [];
    return data;
  }, "tech_requirement_parsing");
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
  await mockRecords(page, 2, () => {
    const data = records(modules[0]!);
    data.records = [data.records[1]!];
    data.records[0]!.content = { 要求摘要: "新报告独立结果", 关键要求: ["新报告要求"] };
    return data;
  });
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => { release = resolve; });
  await mockRecords(page, 1, async () => {
    await delayed;
    return records(modules[0]!);
  }, "tech_requirement_parsing");
  const pending = page.waitForRequest("**/analysis/reports/1/records");
  await page.reload();
  await pending;
  await page.getByRole("combobox", { name: "选择报告版本", exact: true }).click();
  await page.locator(".ant-select-dropdown").getByText("报告 #2 · 已完成", { exact: true }).click();
  await expect(page.getByText("新报告独立结果", { exact: true })).toBeVisible();
  release();
  await expect(page.getByText("制定分阶段迁移方案并说明回退与服务保障。", { exact: true })).toHaveCount(0);
});

test("KV 表格逐行对应，单字段保留多条内容，数量不符可从待核对跳回", async ({ page }) => {
  const data = records(modules[0]!);
  data.output_schema.sections = [{ title: "项目信息", layout: "table", columns: ["字段", "内容"] }];
  data.records = [
    { ...data.records[0]!, id: "single", key: "single", kind: "fact", group: "项目信息",
      title: "采购名称", content: { 字段: "项目名称", 内容: "通信采购项目" } },
    { ...data.records[0]!, id: "compound", key: "compound", kind: "fact", group: "项目信息",
      title: "项目概况", content: { 字段: ["预算", "服务期"], 内容: ["100万元", "三年"] } },
    { ...data.records[0]!, id: "multi", key: "multi", kind: "fact", group: "项目信息",
      title: "项目范围", content: { 字段: ["项目范围"], 内容: ["安装", "调试"] } },
    { ...data.records[0]!, id: "incomplete", key: "incomplete", kind: "fact", group: "项目信息",
      title: "地点与工期", content: { 字段: ["地点", "工期"], 内容: ["浙江省内"] } },
  ];
  await mockRecords(page, 1, data, "tech_requirement_parsing");
  await page.reload();
  const single = page.locator('[data-report-item="single"]');
  const table = page.getByRole("table", { name: "项目信息", exact: true });
  await expect(table.getByRole("columnheader")).toHaveText(["字段", "内容"]);
  await expect(single.getByRole("rowheader")).toHaveText("项目名称");
  await expect(single.locator(".result-kv-value")).toHaveText("通信采购项目");
  const compound = page.locator('[data-report-item="compound"]');
  await expect(compound.locator(".record-attention")).toHaveCount(0);
  await expect(compound.getByRole("rowheader")).toHaveText(["预算", "服务期"]);
  await expect(compound.locator(".result-kv-value")).toHaveText(["100万元", "三年"]);
  const multi = page.locator('[data-report-item="multi"]');
  await expect(multi.getByRole("rowheader")).toHaveText("项目范围");
  await expect(multi.locator(".result-points > li")).toHaveText(["安装", "调试"]);
  const incomplete = page.locator('[data-report-item="incomplete"]');
  await expect(incomplete.getByRole("rowheader")).toHaveText(["地点", "工期"]);
  await expect(incomplete.locator(".result-kv-value")).toHaveText(["浙江省内", "未提供内容"]);
  await page.getByRole("checkbox", { name: "仅待核对条目" }).check();
  await expect(single).toHaveCount(0);
  await expect(compound).toHaveCount(0);
  await expect(multi).toHaveCount(0);
  await expect(incomplete).toBeVisible();
  await page.getByRole("button", { name: "查看本专题待核对事项" }).click();
  await page.getByRole("button", { name: "查看相关事项", exact: true }).click();
  await expect(incomplete).toHaveClass(/report-item-active/);
  await expect(page.getByRole("checkbox", { name: "仅待核对条目" })).not.toBeChecked();
});

test("KV 每行仅显示定位图标，拆行后仍定位本行原文", async ({ page }, info) => {
  const data = records(modules[0]!);
  const second = { ...citation, element_id: 2, anchor: "p1b2", quote: "服务期为三年。" };
  data.output_schema.sections = [{ title: "项目基本信息", layout: "table", columns: ["字段", "内容"] }];
  data.evidence = { source: citation, term: second };
  data.records = [{ ...data.records[0]!, id: "kv-record", key: "kv-record", kind: "fact", group: "项目基本信息",
    content: { 字段: ["项目预算", "服务期限"], 内容: ["2130万元", "三年"] }, evidence_ids: ["source", "term"],
    content_evidence: { 字段: [["source"], ["term"]], 内容: [["source"], ["term"]] },
  }];
  await mockRecords(page, 1, data, "tech_requirement_parsing");
  await page.route("**/api/v1/knowledge/citations/resolve", (route) => route.fulfill({ json: second }));
  await page.reload();
  const table = page.getByRole("table", { name: "项目基本信息", exact: true });
  const record = table.locator('[data-report-item="kv-record"]');
  await expect(record.getByRole("rowheader")).toHaveText(["项目预算", "服务期限"]);
  await expect(record.locator(".result-kv-value")).toHaveText(["2130万元", "三年"]);
  await expect(record.locator(".value-locates button")).toHaveText(["", ""]);
  await expect(record.locator(".value-locates button svg")).toHaveCount(2);
  await expect(page.locator("#report-item-kv-record")).toHaveCount(1);
  await expect(record.locator(".record-attention, .compound-labels")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await table.screenshot({ path: info.outputPath("kv-icon-locators.png") });
  const term = record.getByRole("row").nth(1).getByRole("button", { name: /^定位：/ });
  await expect(term).toHaveAttribute("title", /服务期为三年/);
  const resolved = page.waitForRequest("**/knowledge/citations/resolve");
  await term.click();
  expect((await resolved).postDataJSON()).toMatchObject({ element_id: 2, anchor: "p1b2" });
  const viewer = page.getByRole("region", { name: "引用原文", exact: true });
  await expect(viewer.locator("[data-active-evidence]")).toHaveAttribute("data-active-anchor", "p1b2");
});

test("多处同页依据分别直接定位，去重后仍能准确定位第二处", async ({ page }) => {
  const data = records(modules[0]!);
  const second = { ...citation, element_id: 2, anchor: "p1b2", quote: "第二处完整依据：例外条件仍须保留。" };
  data.evidence = { source: citation, duplicate: citation, second };
  data.records[1]!.evidence_ids = ["source", "duplicate", "second"];
  await mockRecords(page, 1, data, "tech_requirement_parsing");
  await page.route("**/api/v1/knowledge/citations/resolve", (route) => route.fulfill({ json: second }));
  await page.reload();
  const locators = page.locator('[data-report-item="migration"]').getByRole("button", { name: /^定位：/ });
  await expect(locators).toHaveCount(2);
  await expect(locators.first()).toHaveAttribute("title", new RegExp(citation.quote));
  await expect(locators.last()).toHaveAttribute("title", new RegExp(second.quote));
  const resolved = page.waitForRequest("**/knowledge/citations/resolve");
  await locators.last().click();
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
  await mockRecords(page, 1, data, "tech_requirement_parsing");
  // 明确的修订跳转以已通过范围与端点校验的快照为准。
  const resolved = data.records.map((record) => ({ ...record, citations: [citation],
    scope: { ...record.scope, lot_ids: record.scope.lot_refs.map((ref) => ref === "A" ? 1 : 2) } }));
  await page.route("**/api/v1/analysis/reports/1/data", (route) => route.fulfill({ json: {
    report_id: 1, snapshot_id: 1, revision: 1, schema_version: "1", stale: false,
    data: { schema_version: "1", readiness: "partial", facts: [], format_nodes: [], gaps: [],
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

test("记录级缺口按事项归回专题，数量与当前范围一致", async ({ page }) => {
  const scope = { kind: "common", lot_refs: [], lot_ids: [] };
  const gap = { code: "unresolved_reference", detail: "缺少迁移附件", module_key: "tech_requirement_parsing", topic: "migration", scope };
  await page.route("**/api/v1/analysis/reports/1/data", (route) => route.fulfill({ json: {
    report_id: 1, snapshot_id: 1, revision: 1, schema_version: "1", stale: false,
    data: { schema_version: "1", lots: [], facts: [], requirements: [], format_nodes: [], relations: [], readiness: "partial",
      gaps: [gap, { ...gap }, { code: "unknown_condition", record_id: "score", detail: "业绩时间边界待核对", scope }],
    },
  } }));
  await page.reload();
  await page.getByRole("tab", { name: "待核对 · 1 组", exact: true }).click();
  await expect(page.getByText("缺少迁移附件", { exact: true })).toHaveCount(1);
  await expect(page.getByText("业绩时间边界待核对", { exact: true })).toHaveCount(0);
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
  const detail = "模型甲（本次失败2次）：\nHTTP 429 上游限流：每分钟配额已用尽\n\n"
    + "模型乙（本次失败2次）：\n首个有效增量等待超时（10秒） request_id=真实请求";
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: report(1, {
    status: "failed", modules: [], error_message: detail, data_schema_version: null,
  }) }));
  await page.reload();
  await expect(page.getByText("模型服务暂时限流", { exact: true })).toBeVisible();
  const error = page.locator(".analysis-failure-detail");
  await expect(error).toHaveAttribute("open", "");
  await expect(error.locator("p")).toHaveText(detail);
  await expect(error.locator("p")).toHaveCSS("white-space", "pre-wrap");
  await expect(error.locator("p")).toHaveCSS("overflow-wrap", "anywhere");
  await expect(page.getByRole("button", { name: "补跑未完成模块" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "全部重新解析" })).toHaveCount(0);
  await error.screenshot({ path: info.outputPath("model-actual-errors.png") });
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
  await mockRecords(page, 1, data, "tech_requirement_parsing");
  await page.route("**/api/v1/analysis/reports/1/data", (route) => route.fulfill({ json: {
    report_id: 1, snapshot_id: 1, revision: 1, schema_version: "1", stale: false,
    data: { schema_version: "1", lots: [], facts: [], requirements: [], format_nodes: [], relations: [], readiness: "partial",
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
    data: { schema_version: "1", lots: [], facts: [], requirements: [], format_nodes: [], relations: [], readiness: "partial",
      gaps: ["A标段", "B标段", "A标段"].map((ref) => ({ code: "scope_unknown", detail: "此主题范围尚未完成核对",
        module_key: "tech_requirement_parsing", topic: "实施条件", scope: { kind: "unknown", lot_ids: [], lot_refs: [ref] } })),
    },
  } }));
  await page.reload();
  await page.getByRole("tab", { name: "待核对 · 2 组", exact: true }).click();
  const board = page.getByRole("region", { name: "待核对事项" });
  await expect(board.getByText("此主题范围尚未完成核对", { exact: true })).toHaveCount(2);
  await expect(board).toContainText("A标段");
  await expect(board).toContainText("B标段");
});

test("重复点击同一原文角标仍滚回已选结果", async ({ page }, info) => {
  const data = records(modules[0]!);
  data.records = Array.from({ length: 16 }, (_, index) => ({ ...data.records[1]!, id: `item-${index}`, key: `item-${index}`,
    title: `任务 ${index}`, content: { 要求摘要: `任务 ${index} 的要求` } }));
  await mockRecords(page, 1, data, "tech_requirement_parsing");
  await page.reload();
  const target = page.locator('[data-report-item="item-0"]');
  await target.getByRole("button", { name: /^定位：/ }).click();
  const badge = page.locator("[data-annotation-badge]").first();
  await expect(badge).toBeVisible();
  await badge.click();
  await expect(target).toBeInViewport();
  // 反向定位会延迟到正文布局完成后滚动；轮询手动移开，避免与这次滚动抢时序。
  await expect(async () => {
    await page.locator(".analysis-content").evaluate((element) => { element.scrollTop = element.scrollHeight; });
    await expect(target).not.toBeInViewport({ timeout: 300 });
  }).toPass({ timeout: 5000 });
  if (info.project.name === "mobile") await page.getByRole("button", { name: "引用原文", exact: true }).click();
  await badge.click();
  await expect(target).toBeInViewport();
  await expect(target).toHaveClass(/report-item-active/);
});

test("父子材料同时命中关键词时展开全部命中节点", async ({ page }) => {
  const data = records(modules[2]!);
  for (const record of data.records) record.content = { 编制要求: `共同关键词：${record.title}的编制要求` };
  await mockRecords(page, 1, data, "bid_format_outline_parsing");
  await page.reload();
  await selectModule(page, 3);
  await page.getByRole("button", { name: "收起全部材料" }).click();
  await page.getByLabel("搜索解析结果").fill("共同关键词");
  await expect(page.locator(".results-subfilters")).toContainText("3 条匹配");
  await expect(page.getByText("共同关键词：回退计划的编制要求", { exact: true })).toBeVisible();
});

test("模块标签和三种重解析操作直接可用，提交范围互不混淆", async ({ page }) => {
  const requests: unknown[] = [];
  const retryModules = modules.map((module, index) => ({ ...module,
    status: ["completed", "failed", "canceled"][index]!,
  }));
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: report(1, {
    status: "partial", modules: retryModules.map((module) => ({ ...module, items: [] })),
  }) }));
  // 页面以记录接口的最新状态更新按钮，两个接口需描述同一次运行。
  await mockRecords(page, 1, (key) => records(retryModules.find((module) => module.module_key === key)!));
  await page.route("**/api/v1/analysis/reports/1/retry", (route) => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({ json: { id: 1, status: "pending" } });
  });
  await page.reload();
  const tabs = page.getByRole("tablist", { name: "解析专题", exact: true });
  await expect(tabs.getByRole("tab")).toHaveCount(4);
  await expect(page.getByRole("combobox", { name: "解析专题" })).toHaveCount(0);
  const actions = page.getByRole("group", { name: "报告操作", exact: true });
  await expect(actions.getByRole("button")).toHaveText(["刷新结果", "重新解析本模块", "补跑未完成模块", "全部重新解析"]);
  await expect(page.locator(".report-module-heading").getByRole("button", { name: "重新解析本模块" })).toHaveCount(0);
  await tabs.locator('[data-module-id="1"]').focus();
  await page.keyboard.press("ArrowRight");
  await expect(tabs.locator('[data-module-id="2"]')).toHaveAttribute("aria-selected", "true");
  await page.getByRole("button", { name: "重新解析本模块", exact: true }).click();
  await expect.poll(() => requests).toEqual([{ module_keys: ["scoring_standard_parsing"], mode: "restart" }]);
  await page.getByRole("button", { name: "补跑未完成模块", exact: true }).click();
  await expect.poll(() => requests).toHaveLength(2);
  expect(requests[1]).toEqual({ mode: "resume" });
  await page.getByRole("button", { name: "全部重新解析", exact: true }).click();
  await expect.poll(() => requests).toHaveLength(3);
  expect(requests[2]).toEqual({ module_keys: modules.map((module) => module.module_key), mode: "restart" });
  await selectModule(page, 0);
  await expect(actions.getByRole("button", { name: "重新解析本模块", exact: true })).toBeDisabled();
});

test("正文同一事项的位置跨条去重，不同出处直接定位且原文框保持透明", async ({ page }, info) => {
  const data = records(modules[0]!);
  const first = { ...citation, quote: "本项目预算为2130万元。", bbox: [0.1, 0.12, 0.8, 0.18] as [number, number, number, number] };
  const second = { ...citation, element_id: 2, anchor: "p1b2", quote: "服务期为2年。",
    bbox: [0.1, 0.25, 0.8, 0.31] as [number, number, number, number] };
  data.records = [{ ...data.records[0]!, content: { 背景: ["本项目预算为**2130万元**。", "服务期为2年。", "本项目预算2130万元，服务期2年。"] },
    evidence_ids: ["source", "duplicate", "term"], content_evidence: { 背景: [["source", "duplicate"], ["term"], ["source", "term"]] } }];
  // 同一原文块的摘录不同也只显示一个图标，完整摘录仍保留，定位请求使用真实原始引用。
  const duplicate = { ...first, quote: "同一预算原文块中的另一段摘录。" };
  data.evidence = { source: first, duplicate, term: second };
  await mockRecords(page, 1, data, "tech_requirement_parsing");
  await page.route("**/api/v1/knowledge/citations/resolve", (route) => route.fulfill({
    json: route.request().postDataJSON().element_id === 2 ? second : first,
  }));
  await page.reload();
  const record = page.locator('[data-report-item="background"]');
  const points = record.locator(".result-points > li");
  await expect(points).toHaveCount(3);
  await expect(points.nth(0).getByRole("button")).toHaveCount(1);
  await expect(points.nth(0).getByRole("button")).toHaveAttribute("title", new RegExp(duplicate.quote));
  await expect(points.nth(0).getByRole("button")).toHaveAttribute("title", new RegExp(first.quote));
  await expect(points.nth(1).getByRole("button")).toHaveCount(1);
  await expect(points.nth(2).getByRole("button")).toHaveCount(0);
  await expect(points.getByRole("button")).toHaveText(["", ""]);
  await expect(points.nth(0).locator("strong")).toHaveText("2130万元");
  await expect(record.locator(".result-points > li > p > .value-locates-inline")).toHaveCount(2);
  await expect(record.locator(":scope > .value-locates")).toHaveCount(0);
  await expect(record.getByRole("button", { name: /查看 .* 处依据/ })).toHaveCount(0);
  await record.screenshot({ path: info.outputPath("inline-citations.png") });
  const resolved = page.waitForRequest("**/knowledge/citations/resolve");
  await points.nth(1).getByRole("button").click();
  expect((await resolved).postDataJSON()).toMatchObject({ element_id: 2, anchor: "p1b2" });
  const viewer = page.getByRole("region", { name: "引用原文", exact: true });
  await expect(viewer.locator("[data-active-evidence]")).toHaveAttribute("data-active-anchor", "p1b2");
  const styles = await viewer.locator("[data-evidence-anchor], [data-active-evidence]").evaluateAll((frames) =>
    frames.map((frame) => { const style = getComputedStyle(frame); return {
      background: style.backgroundColor, shadow: style.boxShadow, border: parseFloat(style.borderTopWidth),
    }; }));
  expect(styles).toHaveLength(1);
  for (const style of styles) {
    expect(style.background).toBe("rgba(0, 0, 0, 0)");
    expect(style.shadow).toBe("none");
    expect(style.border).toBeGreaterThanOrEqual(3);
  }
  await expect(viewer.locator("[data-annotation-badge]")).toHaveCount(1);
  await expect(viewer.locator('[data-evidence-anchor="p1b1"]')).toHaveCount(0);
  await viewer.screenshot({ path: info.outputPath("outline-only-location.png") });
  if (info.project.name === "mobile") await page.getByRole("button", { name: "分析内容", exact: true }).click();
  const firstResolved = page.waitForRequest("**/knowledge/citations/resolve");
  await points.nth(0).getByRole("button").click();
  expect((await firstResolved).postDataJSON()).toMatchObject({ element_id: 1, anchor: "p1b1" });
  await expect(viewer.locator("[data-active-evidence]")).toHaveCount(1);
  await expect(viewer.locator("[data-active-evidence]")).toHaveAttribute("data-active-anchor", "p1b1");
  await expect(viewer.locator('[data-active-anchor="p1b2"]')).toHaveCount(0);
  await expect(viewer.locator("[data-annotation-badge]")).toHaveCount(1);
  // 重复点击也应重播定位动画，但不能累积新的框。
  const previous = await viewer.locator("[data-active-evidence]").elementHandle();
  if (info.project.name === "mobile") await page.getByRole("button", { name: "分析内容", exact: true }).click();
  await points.nth(0).getByRole("button").click();
  await expect.poll(() => previous!.evaluate((frame) => frame.isConnected)).toBe(false);
  await expect(viewer.locator("[data-active-evidence]")).toHaveCount(1);
});

test("跨页切换定位只显示当前页的一个框，缺失坐标保留页级框", async ({ page }, info) => {
  const data = records(modules[0]!);
  const next = { ...citation, element_id: 2, anchor: "p2b1", page_no: 2 };
  const pageOnly = { ...next, element_id: 3, anchor: "p2b2", bbox: null };
  const refs = [citation, next, pageOnly];
  data.evidence = { source: citation, next, pageOnly };
  data.records = [{ ...data.records[0]!, content: { 背景: ["第一页依据。", "第二页依据。", "第二页无块坐标。"] },
    evidence_ids: ["source", "next", "pageOnly"], content_evidence: { 背景: [["source"], ["next"], ["pageOnly"]] } }];
  await mockRecords(page, 1, data, "tech_requirement_parsing");
  await page.route("**/api/v1/versions/1/pages", (route) => route.fulfill({ json: { pages: [1, 2].map((page_no) =>
    ({ page_no, width_pt: 595, height_pt: 842, rotation: 0, has_text_layer: true })) } }));
  await page.route("**/api/v1/knowledge/citations/resolve", (route) => route.fulfill({
    json: refs.find((ref) => ref.element_id === route.request().postDataJSON().element_id),
  }));
  await page.reload();
  const buttons = page.locator('[data-report-item="background"] .result-points button');
  const viewer = page.getByRole("region", { name: "引用原文", exact: true });
  for (const index of [0, 1, 2, 0]) {
    if (index !== 0 || await viewer.count()) {
      if (info.project.name === "mobile") await page.getByRole("button", { name: "分析内容", exact: true }).click();
    }
    await buttons.nth(index).click();
    const ref = refs[index]!;
    await expect(viewer.locator("[data-active-evidence]")).toHaveCount(1);
    await expect(viewer.locator("[data-active-evidence]")).toHaveAttribute("data-active-anchor", ref.anchor);
    await expect(viewer.locator(`[data-page-no="${ref.page_no === 1 ? 2 : 1}"] [data-active-evidence]`)).toHaveCount(0);
    await expect(viewer.locator("[data-annotation-badge]")).toHaveCount(ref.bbox ? 1 : 0);
    if (!ref.bbox) await expect(viewer.locator("[data-active-evidence]")).toHaveCSS("border-top-style", "dashed");
  }
});

for (const module of [
  { id: 4, title: "报价要求", module_key: "price_requirement_parsing", status: "completed", error_message: null,
    items: [item("price", "报价组成", "报价要求", "table", ["事项", "要求"],
      { 事项: "报价组成", 要求: ["包含税费。", "包含运输费用。"] })] },
  modules[1]!, modules[2]!,
]) test(`${module.title}同一事项跨列合并重复定位，不同事项各自保留入口`, async ({ page }) => {
  const data = records(module);
  if (module.module_key === "scoring_standard_parsing") {
    data.records[0]!.content = { ...data.records[0]!.content, 满分分值: "**6分**" };
  }
  const second = { ...citation, element_id: 2, anchor: "p1b2", quote: "第二条独立原文。" };
  data.evidence = { source: citation, second };
  for (const record of data.records) {
    record.evidence_ids = ["source", "second"];
    record.content_evidence = Object.fromEntries(Object.entries(record.content!).map(([column, value]) =>
      [column, (Array.isArray(value) ? value : [value]).map((_, index) => [index ? "second" : "source"])]));
  }
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: report(1, { modules: [{ ...module, items: [] }] }) }));
  await mockRecords(page, 1, data, module.module_key);
  await page.reload();
  if (module.module_key === "bid_format_outline_parsing") await page.getByRole("button", { name: "展开全部材料" }).click();
  const first = page.locator(`[data-report-item="${module.items[0]!.id}"]`);
  if (module.module_key === "scoring_standard_parsing") {
    await expect(first.locator(".result-score .value-locates-inline")).toBeVisible();
    await expect(first.locator(".result-score strong")).toHaveText("6分");
    await expect(first.locator(".result-score")).not.toContainText("**");
  }
  if (module.module_key === "price_requirement_parsing") await expect(first.locator('td[data-label="要求"] .result-points > li .value-locates-inline')).toHaveCount(1);
  if (module.module_key !== "bid_format_outline_parsing") {
    await expect(first.locator(".value-locates-inline button")).toHaveCount(2);
  }
  await expect(first.getByRole("button", { name: /查看 .* 处依据/ })).toHaveCount(0);
  for (const record of data.records) {
    const element = page.locator(`[data-report-item="${record.id}"]`);
    await expect(element.locator(".value-locates-inline").first()).toBeVisible();
    if (module.module_key === "bid_format_outline_parsing") {
      // 父节点包含子节点 DOM，按当前节点计数，确保共用出处不会吞掉子事项自己的入口。
      await expect(element.locator(":scope > details > .module-markdown-body .value-locates-inline button, :scope > details > .record-extra-evidence button")).toHaveCount(2);
    }
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("逐条正文依据之外的补充原文可独立定位，正文来源不重复集中展示", async ({ page }) => {
  const data = records(modules[0]!);
  const second = { ...citation, element_id: 2, anchor: "p1b2", quote: "仅在业务低谷窗口实施，并提交审批记录。" };
  data.evidence = { source: citation, condition: second };
  data.records = [{ ...data.records[0]!, content: { 背景: ["实施平台迁移。"] },
    evidence_ids: ["source", "condition"], content_evidence: { 背景: [["source"]] },
  }];
  await mockRecords(page, 1, data, "tech_requirement_parsing");
  await page.route("**/api/v1/knowledge/citations/resolve", (route) => route.fulfill({ json: second }));
  await page.reload();
  const record = page.locator('[data-report-item="background"]');
  await expect(record.locator(".result-points > li button")).toHaveCount(1);
  const extra = record.getByRole("group", { name: "补充依据", exact: true });
  await expect(extra.getByRole("button")).toHaveCount(1);
  await expect(extra.getByRole("button")).toHaveAttribute("title", /仅在业务低谷窗口/);
  const resolved = page.waitForRequest("**/knowledge/citations/resolve");
  await extra.getByRole("button").click();
  expect((await resolved).postDataJSON()).toMatchObject({ element_id: 2, anchor: "p1b2" });
});

test("字段名和补充条件的同位置摘录合并到正文图标，完整提示保留", async ({ page }) => {
  const module: AnalysisModule = { ...modules[0]!, module_key: "project_basic_info_parsing", title: "项目概况",
    items: [item("project-name", "项目名称", "项目基本信息", "table", ["字段", "内容"],
      { 字段: "项目名称", 内容: "平台改造项目" })] };
  const data = records(module);
  // 不同摘录仍是独立证据，但同位置只留一个图标，合并后的提示必须全部保留。
  const label = { ...citation, quote: "本次采购项目名称：" };
  const condition = { ...citation, quote: "实施前须提交审批记录。" };
  data.evidence = { source: citation, label, condition };
  data.records[0] = { ...data.records[0]!, evidence_ids: ["source", "label", "condition"],
    content_evidence: { 字段: [["label"]], 内容: [["source"]] },
  };
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: report(1, { modules: [{ ...module, items: [] }] }) }));
  await mockRecords(page, 1, data, "project_basic_info_parsing");
  await page.reload();
  const record = page.locator('[data-report-item="project-name"]');
  await expect(record.locator(".result-kv-value button")).toHaveCount(1);
  const extra = record.getByRole("group", { name: "补充依据", exact: true });
  await expect(extra).toHaveCount(0);
  await expect(record.locator(".result-kv-value button")).toHaveAttribute("title", /本次采购项目名称/);
  await expect(record.locator(".result-kv-value button")).toHaveAttribute("title", /实施前须提交审批记录/);
  await expect(record.locator(".result-kv-value button")).toHaveAttribute("title", new RegExp(citation.quote));
});

test.describe("每次分析的时间与原因", () => {
  test.use({ timezoneId: "Asia/Singapore" });

  test("最后一次成功仍保留各次失败原因，缺失时间不伪造", async ({ page }, info) => {
    const run = {
      id: 1, attempt: 1, status: "failed", thread_id: "run-1", started_at: "2026-10-19T01:01:01Z",
      finished_at: "2026-10-19T01:02:03Z", deadline_at: "2026-10-19T01:30:00Z",
      model_calls: 10, tool_calls: 8, prompt_tokens: 100, completion_tokens: 50,
      successful_model_calls: 6, successful_tool_calls: 5,
      limits: { max_model_calls: 80, max_tool_calls: 100, timeout_seconds: 1800, max_output_tokens: 8192 },
      error_message: "HTTP 429：模型服务限流。\n请稍后重试。",
    };
    const runs = [run,
      { ...run, id: 2, attempt: 2, status: "canceled", error_message: "用户取消了本次分析。" },
      { ...run, id: 3, attempt: 3, started_at: null, finished_at: null, error_message: null },
      { ...run, id: 4, attempt: 4, status: "completed", error_message: null },
    ];
    await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: report(1, {
      modules: modules.map((module, index) => ({ ...module, items: [], runs: index === 0 ? runs : [] })),
    }) }));
    await page.reload();
    await page.locator(".module-operations > summary").click();
    const history = page.getByRole("list", { name: "历次分析记录", exact: true });
    await expect(history.getByRole("listitem")).toHaveCount(4);
    const failed = history.getByRole("listitem", { name: "第 1 次分析", exact: true });
    // 成功次数独立展示，不能拿包含失败的尝试次数或执行上限作为分母。
    await expect(failed.locator(".run-summary")).toContainText("模型请求成功 6 次 · 工具执行成功 5 次");
    await expect(failed.locator(".run-summary")).not.toContainText("10/80");
    await expect(failed.locator(".run-summary")).not.toContainText("8/100");
    await expect(failed).toContainText("2026/10/19 09:01:01");
    await expect(failed).toContainText("2026/10/19 09:02:03");
    await expect(failed.locator(".run-error")).toHaveText("失败原因：HTTP 429：模型服务限流。 请稍后重试。");
    await expect(failed.locator(".run-error")).toHaveCSS("white-space", "pre-wrap");
    await expect(history.getByRole("listitem", { name: "第 2 次分析", exact: true })).toContainText("停止原因：用户取消了本次分析。");
    const missing = history.getByRole("listitem", { name: "第 3 次分析", exact: true });
    await expect(missing.locator(".run-times dd")).toHaveText(["未记录", "未记录"]);
    await expect(missing).toContainText("失败原因：未记录");
    await expect(history.getByRole("listitem", { name: "第 4 次分析", exact: true }).locator(".run-error")).toHaveCount(0);
    await history.screenshot({ path: info.outputPath("analysis-run-history.png") });
  });

  test("运行中的结束时间显示尚未结束，不能用截止时间替代", async ({ page }) => {
    await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: report(1, {
      status: "running", modules: [{ ...modules[0]!, items: [], status: "running", runs: [{
        id: 1, attempt: 1, status: "running", thread_id: "run-1", started_at: "2026-10-19T01:01:01Z",
        finished_at: null, deadline_at: "2026-10-19T01:30:00Z", model_calls: 1, tool_calls: 1,
        successful_model_calls: 0, successful_tool_calls: 0,
        prompt_tokens: 100, completion_tokens: 50, error_message: null,
        limits: { max_model_calls: 80, max_tool_calls: 100, timeout_seconds: 1800, max_output_tokens: 8192 },
      }] }],
    }) }));
    await page.reload();
    await page.locator(".module-operations > summary").click();
    const history = page.getByRole("list", { name: "历次分析记录", exact: true });
    await expect(history).toContainText("尚未结束");
    await expect(history).toContainText("模型请求成功 0 次 · 工具执行成功 0 次");
    await expect(history).not.toContainText("09:30:00");
    await expect(page.getByRole("button", { name: "重新解析本模块", exact: true })).toBeDisabled();
  });

  test("每次运行分别展示结算成功次数，不能用尝试数代替", async ({ page }) => {
    const run = {
      id: 1, attempt: 4, status: "partial", thread_id: "run-4", started_at: "2026-11-08T08:25:22Z",
      finished_at: "2026-11-08T08:58:51Z", deadline_at: "2026-11-08T09:25:22Z",
      model_calls: 48, tool_calls: 39, prompt_tokens: 100, completion_tokens: 50,
      successful_model_calls: 8, successful_tool_calls: 0,
      limits: { max_model_calls: 80, max_tool_calls: 100, timeout_seconds: 3600, max_output_tokens: 8192 },
      error_message: "本次分析的模型请求预算已耗尽",
    };
    await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: report(1, {
      modules: [{ ...modules[0]!, items: [], runs: [
        run, { ...run, id: 2, attempt: 5, successful_model_calls: 0, successful_tool_calls: 3 },
      ] }],
    }) }));
    await page.reload();
    await page.locator(".module-operations > summary").click();
    const history = page.getByRole("list", { name: "历次分析记录", exact: true });
    const first = history.getByRole("listitem", { name: "第 4 次分析", exact: true });
    await expect(first.locator(".run-summary")).toContainText("模型请求成功 8 次 · 工具执行成功 0 次");
    await expect(first.locator(".run-summary")).not.toContainText("48");
    await expect(first.locator(".run-summary")).not.toContainText("39");
    await expect(history.getByRole("listitem", { name: "第 5 次分析", exact: true }).locator(".run-summary"))
      .toContainText("模型请求成功 0 次 · 工具执行成功 3 次");
  });
});
