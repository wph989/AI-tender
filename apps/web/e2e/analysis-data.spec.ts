import { test, expect, type Page } from "@playwright/test";
import type { AnalysisContext, AnalysisDataSnapshot, BusinessRecord, Citation } from "../src/types/knowledge";
import { mockApi } from "./fixtures";

const citation: Citation = {
  source_id: 1, collection_id: 1, project_id: 1, project_file_id: 1,
  version_id: 1, parse_run_id: 1, element_id: 1, anchor: "p1b1", page_no: 1,
  bbox: [0.1, 0.1, 0.8, 0.2], file_name: "编制依据样本.pdf", purpose: "tender",
  quote: "所有标段须提供营业执照",
};

function record(key: string, text: string, lotId?: number): BusinessRecord {
  return {
    id: key, key, kind: "requirement", title: key, text, content: { 内容: text },
    module_key: "project_basic_info_parsing", group: "", sort_order: 0,
    verification: "supported", structuring: "complete", effective_status: "active",
    scope: lotId ? { kind: "lots", lot_ids: [lotId], lot_refs: [lotId === 1 ? "A" : "B"] }
      : { kind: "common", lot_ids: [], lot_refs: [] },
    citations: [{ ...citation, quote: text }],
  };
}

function snapshot(reportId = 1): AnalysisDataSnapshot {
  return {
    report_id: reportId, snapshot_id: reportId * 10, revision: 1, schema_version: "1", stale: false,
    data: {
      schema_version: "1", readiness: "partial", quality_status: "needs_review",
      lots: [
        { ...record("lot-a", "A标段"), kind: "lot", lot_id: 1, code: "A", title: "A标段", aliases: [] },
        { ...record("lot-b", "B标段"), kind: "lot", lot_id: 2, code: "B", title: "B标段", aliases: [] },
      ],
      facts: [{ ...record("project", "采购交换机项目"), kind: "fact" }],
      requirements: [
        record("common", "所有标段须提供营业执照"),
        ...Array.from({ length: 101 }, (_, i) => record(`a-${i}`, `A标段要求${i}`, 1)),
        record("b", "B标段专用要求", 2),
      ],
      format_nodes: [], relations: [],
      gaps: [{ code: "incomplete_structure", detail: "质保起算点待核对",
        scope: { kind: "common", lot_ids: [], lot_refs: [] } }],
    },
  };
}

function context(lotId: number, offset = 0): AnalysisContext {
  const data = snapshot().data;
  const requirements = data.requirements.filter((r) => r.scope.kind === "common" || r.scope.lot_ids.includes(lotId));
  const page = requirements.slice(offset, offset + 100);
  return {
    ...data, snapshot_id: 10, purpose: "outline", lot_id: lotId,
    requirements: page, requirement_manifest: requirements.map((r) => r.id),
    total_requirements: requirements.length, next_offset: offset + page.length < requirements.length ? offset + page.length : null,
    unresolved: [], references: [],
  };
}

async function openPreview(page: Page) {
  await page.goto("/projects/1");
  await page.getByRole("button", { name: "按标段查看要求", exact: true }).click();
  return page.getByRole("dialog", { name: "按标段查看投标要求", exact: true });
}

async function selectLot(page: Page, title: string) {
  await page.getByRole("combobox", { name: "投标标段", exact: true }).click();
  await page.locator(".ant-select-dropdown").getByText(title, { exact: true }).click();
}

let errors: string[];
test.beforeEach(async ({ page }) => {
  errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  // 通用兜底和新增路由全部拦截，浏览器不依赖业务库迁移或真实模型。
  await mockApi(page);
  await page.route("**/api/v1/projects/1/analysis", (route) => route.fulfill({ json: {
    analysis_category: "goods", analysis_topics: [], lots: [], sources: [],
    reports: [{ id: 1, status: "completed" }, { id: 2, status: "completed" }],
    categories: { goods: "货物" }, topics: {},
  } }));
  await page.route(/\/api\/v1\/analysis\/reports\/\d+$/, (route) => route.fulfill({ json: {
    id: Number(route.request().url().split("/").at(-1)), status: "completed",
    category: "goods", topics: [], coverage: {}, modules: [],
    finished_at: "2026-10-11T10:00:00Z", data_schema_version: "1", stale: false,
  } }));
  await page.route(/\/api\/v1\/analysis\/reports\/\d+\/data$/, (route) => route.fulfill({
    json: snapshot(Number(route.request().url().split("/").at(-2))),
  }));
  await page.route("**/api/v1/analysis/reports/1/context", (route) => {
    const request = route.request().postDataJSON();
    return route.fulfill({ json: context(request.lot_id, request.offset) });
  });
});
test.afterEach(() => expect(errors, "浏览器未捕获异常").toEqual([]));

test("多标段必须显式单选，分页完整加载，原文入口先校验引用", async ({ page }, info) => {
  const requests: { lot_id: number; snapshot_id: number; offset: number }[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/context")) requests.push(request.postDataJSON());
  });
  const dialog = await openPreview(page);
  await expect(dialog.getByRole("button", { name: "查看要求", exact: true })).toBeDisabled();
  expect(requests).toHaveLength(0);
  await selectLot(page, "A标段");
  await dialog.getByRole("button", { name: "查看要求", exact: true }).click();
  await expect(dialog.getByRole("cell", { name: /采购交换机项目/ })).toBeVisible();
  await expect(dialog.getByRole("cell", { name: /所有标段须提供营业执照/ })).toBeVisible();
  await expect(dialog.getByRole("cell", { name: /B标段专用要求/ })).toHaveCount(0);
  await dialog.getByRole("button", { name: "加载更多要求", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "加载更多要求", exact: true })).toHaveCount(0);
  await dialog.locator('.analysis-context-requirements .ant-pagination-item[title="11"]').click();
  await expect(dialog.getByRole("cell", { name: /A标段要求100/ })).toBeVisible();
  expect(requests.map((r) => [r.snapshot_id, r.lot_id, r.offset])).toEqual([[10, 1, 0], [10, 1, 100]]);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: info.outputPath("analysis-preview.png"), fullPage: true });

  await page.route("**/api/v1/knowledge/citations/resolve", (route) => route.fulfill({ json: citation }));
  await page.route("**/api/v1/versions/1/pages", (route) => route.fulfill({ json: { pages: [
    { page_no: 1, width_pt: 595, height_pt: 842, rotation: 0, has_text_layer: true },
  ] } }));
  await page.route("**/api/v1/versions/1/file", (route) => route.fulfill({
    path: "public/samples/sample-tender.pdf", contentType: "application/pdf",
  }));
  const resolved = page.waitForRequest("**/knowledge/citations/resolve");
  await dialog.getByRole("button", { name: /^定位：/ }).first().click();
  expect((await resolved).postDataJSON()).toMatchObject({ source_id: 1, parse_run_id: 1, anchor: "p1b1" });
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("region", { name: "引用原文", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "引用原文", exact: true }).locator("canvas").first()).toBeVisible();
});

test("切换标段后丢弃仍在途中的旧依据", async ({ page }) => {
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/v1/analysis/reports/1/context", async (route) => {
    const request = route.request().postDataJSON();
    if (request.lot_id === 1) await delayed;
    await route.fulfill({ json: context(request.lot_id) });
  });
  const dialog = await openPreview(page);
  await selectLot(page, "A标段");
  const first = page.waitForRequest("**/analysis/reports/1/context");
  await dialog.getByRole("button", { name: "查看要求", exact: true }).click();
  await first;
  await selectLot(page, "B标段");
  await dialog.getByRole("button", { name: "查看要求", exact: true }).click();
  await expect(dialog.getByRole("cell", { name: /B标段专用要求/ })).toBeVisible();
  release();
  await expect(dialog.getByRole("cell", { name: /A标段要求0/ })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "加载更多要求", exact: true })).toHaveCount(0);
});

test("更换报告清除标段选择，过期快照错误不显示旧依据", async ({ page }) => {
  const dialog = await openPreview(page);
  await selectLot(page, "A标段");
  await dialog.getByRole("button", { name: "查看要求", exact: true }).click();
  await expect(dialog.getByRole("cell", { name: /A标段要求0/ })).toBeVisible();
  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  const nextData = page.waitForResponse("**/analysis/reports/2/data");
  await page.getByRole("combobox", { name: "选择报告版本", exact: true }).click();
  await page.locator(".ant-select-dropdown").getByText("报告 #2 · 已完成", { exact: true }).click();
  await nextData;
  await page.getByRole("button", { name: "按标段查看要求", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "查看要求", exact: true })).toBeDisabled();
  await expect(dialog.getByRole("cell", { name: /A标段要求0/ })).toHaveCount(0);
  await page.route("**/api/v1/analysis/reports/2/context", (route) => route.fulfill({
    status: 409, json: { error: { code: "data_stale", message: "依据已更新，请使用当前有效分析快照" } },
  }));
  await selectLot(page, "B标段");
  await dialog.getByRole("button", { name: "查看要求", exact: true }).click();
  await expect(dialog.getByText("依据已更新，请使用当前有效分析快照", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("cell", { name: /B标段专用要求/ })).toHaveCount(0);
});

test("目录未核对完整时，一个已识别标段也不能默认选中", async ({ page }) => {
  const data = snapshot();
  data.data.lots = data.data.lots.slice(0, 1);
  data.data.gaps.push({ code: "lot_catalog_unknown", detail: "其它标段尚未核对",
    scope: { kind: "unknown", lot_ids: [], lot_refs: [] } });
  await page.route("**/api/v1/analysis/reports/1/data", (route) => route.fulfill({ json: data }));
  const dialog = await openPreview(page);
  await expect(dialog.getByRole("button", { name: "查看要求", exact: true })).toBeDisabled();
  await selectLot(page, "A标段");
  await expect(dialog.getByRole("button", { name: "查看要求", exact: true })).toBeEnabled();
});

test("依据不足的报告保留正文入口，但禁止进入标段编制预览", async ({ page }) => {
  const data = snapshot();
  data.data.readiness = "unavailable";
  await page.route("**/api/v1/analysis/reports/1/data", (route) => route.fulfill({ json: data }));
  await page.goto("/projects/1");
  await expect(page.getByRole("button", { name: "按标段查看要求", exact: true })).toBeDisabled();
  await expect(page.getByRole("tab", { name: "解析正文", exact: true })).toBeVisible();
});

test("人工确认绑定当前快照和事项版本", async ({ page }) => {
  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/v1/analysis/reports/1/reviews", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ json: { id: 77, decision: "confirmed" } });
  });
  const dialog = await openPreview(page);
  await dialog.getByText("项目事实（1）", { exact: true }).click();
  await dialog.getByRole("button", { name: "确认", exact: true }).click();
  await expect.poll(() => submitted).toMatchObject({
    snapshot_id: 10, record_id: "project", previous_review_id: null,
    decision: "confirmed", corrected_text: null,
  });
});

test("机器自查未通过的事项不能提交人工复核", async ({ page }) => {
  const data = snapshot();
  data.data.facts[0]!.verification = "unsupported";
  await page.route("**/api/v1/analysis/reports/1/data", (route) => route.fulfill({ json: data }));
  let submitted = false;
  await page.route("**/api/v1/analysis/reports/1/reviews", async (route) => {
    submitted = true;
    await route.fulfill({ json: { id: 77 } });
  });
  const dialog = await openPreview(page);
  await dialog.getByText("项目事实（1）", { exact: true }).click();
  const row = dialog.getByRole("row").filter({ hasText: "采购交换机项目" });
  await expect(row.getByRole("button", { name: "确认", exact: true })).toBeDisabled();
  await expect(row.getByText("机器自查未通过，须重跑分析后再复核", { exact: true })).toBeVisible();
  expect(submitted).toBe(false);
});

test("重新打开复核可对照人工修正和机器原文，预览只展示修正正文", async ({ page }, info) => {
  const data = snapshot();
  const fact = data.data.facts[0]!;
  const corrected = "采购核心交换机项目";
  await page.route("**/api/v1/analysis/reports/1/data", (route) => route.fulfill({ json: data }));
  await page.route("**/api/v1/analysis/reports/1/reviews", (route) => {
    const input = route.request().postDataJSON();
    expect(input).toMatchObject({ record_id: fact.id, decision: "corrected", corrected_text: corrected });
    fact.human_review_status = "corrected";
    fact.human_review = { ...input, id: 78, actor: "operator", created_at: "2026-11-21T00:00:00Z" };
    return route.fulfill({ json: fact.human_review });
  });
  await page.route("**/api/v1/analysis/reports/1/context", (route) =>
    route.fulfill({ json: { ...context(1), facts: [{ ...fact, text: corrected }] } }));
  let dialog = await openPreview(page);
  await dialog.getByText("项目事实（1）", { exact: true }).click();
  await dialog.getByRole("textbox", { name: "project 修正或驳回理由" }).fill("与招标公告核对");
  await dialog.getByRole("textbox", { name: "project 修正内容" }).fill(corrected);
  const refetched = page.waitForResponse((response) => response.url().endsWith("/1/data"));
  await dialog.getByRole("button", { name: "保存修正", exact: true }).click();
  await refetched;
  dialog = await openPreview(page);
  await dialog.getByText("项目事实（1）", { exact: true }).click();
  const row = dialog.getByRole("row").filter({ hasText: "机器原文：" });
  await expect(row).toContainText("人工修正：" + corrected);
  await expect(row).toContainText("机器原文：" + fact.text);
  await expect(row.getByRole("button", { name: "定位：编制依据样本.pdf · 第 1 页" })).toBeVisible();
  await page.screenshot({ path: info.outputPath("analysis-correction.png") });
  await dialog.getByText("项目事实（1）", { exact: true }).click();
  await selectLot(page, "A标段");
  await dialog.getByRole("button", { name: "查看要求", exact: true }).click();
  await expect(dialog.getByRole("cell", { name: corrected, exact: false })).toBeVisible();
  await expect(dialog.getByText("机器原文：")).toBeHidden();
});
