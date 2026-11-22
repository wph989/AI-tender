import { test, expect } from "@playwright/test";
import { calls, collections, mockApi, selectModule, models, profile } from "./fixtures";
import type { KnowledgeSource } from "../src/types/knowledge";

let pageErrors: string[];
test.beforeEach(async ({ page }) => {
  pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await mockApi(page);
});
test.afterEach(() => {
  expect(pageErrors, "浏览器未捕获异常").toEqual([]);
});

test("配置范围由服务端下发，大预算可保存且只读项不可修改", async ({ page }) => {
  let saved: unknown;
  await page.route("**/api/v1/config/items", (route) => route.fulfill({ json: {
    active: { release_id: 1, version_no: 1 },
    items: [
      { key: "analysis.max_output_tokens", layer: "L1", value_type: "int",
        description: "单次模型输出上限（Token）", default: 8192, value: 8192, writable: true,
        minimum: 1, overridden: false, requires_gate: false },
      { key: "mineru.ocr_mode", layer: "L2", value_type: "string",
        description: "默认文字识别方式", default: "auto", value: "auto", writable: false,
        choices: ["auto", "ocr"], overridden: false, requires_gate: true },
    ],
  } }));
  await page.route("**/api/v1/config/releases", async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    saved = route.request().postDataJSON();
    await route.fulfill({ json: { id: 2, version_no: 2, status: "active" } });
  });
  await page.goto("/settings/models");
  // 窄屏标签会自动滚动；键盘激活避免在滚动过程中点击到旧坐标。
  await page.getByRole("tab", { name: "分析参数", exact: true }).focus();
  await page.keyboard.press("Enter");
  const budget = page.getByLabel("单次模型输出上限（Token）", { exact: true });
  await expect(budget).toHaveAttribute("min", "1");
  await expect(budget).not.toHaveAttribute("max");
  await budget.fill("262144");
  await page.getByRole("button", { name: "保存并立即生效", exact: true }).click();
  await expect.poll(() => saved).toMatchObject({ values: { "analysis.max_output_tokens": 262144 } });
  await page.goto("/settings/config");
  await expect(page.getByLabel("单次模型输出上限（Token）", { exact: true })).toHaveCount(0);
  await page.getByRole("tab", { name: "解析配置", exact: true }).click();
  await expect(page.getByLabel("默认文字识别方式", { exact: true })).toBeDisabled();
});

test("模型超时允许小数并移除预算人工上限", async ({ page }) => {
  let saved: unknown;
  await page.route("**/api/v1/llm/settings", (route) => route.fulfill({ json: {
    secret_key_ready: true, test_valid_seconds: 3600,
    adapter_profiles: [{ ...profile, parameter_schema: {
      ...profile.parameter_schema,
      max_tokens: { label: "输出上限", type: "integer", min: 1 },
    } }],
    model_fields: {
      timeout_seconds: { label: "超时", type: "number", min: 0, exclusive_min: true },
      extra_retries: { label: "额外重试", type: "integer", min: 0 },
    },
  } }));
  await page.route("**/api/v1/llm/models/1", async (route) => {
    saved = route.request().postDataJSON();
    await route.fulfill({ json: models[0] });
  });
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: /管理模型/ }).click();
  await page.getByRole("button", { name: "编辑", exact: true }).first().click();
  const dialog = page.getByRole("dialog", { name: "编辑模型", exact: true });
  const timeout = dialog.getByLabel("响应间隔超时（秒）", { exact: true });
  await expect(timeout).not.toHaveAttribute("max");
  await timeout.fill("0");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog.getByText("请输入大于 0 的秒数", { exact: true })).toBeVisible();
  expect(saved).toBeUndefined();
  await timeout.fill("0.01");
  await dialog.getByLabel("失败后额外重试次数", { exact: true }).fill("99");
  await dialog.getByLabel("输出上限", { exact: true }).fill("262144");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(saved).toMatchObject({ timeout_seconds: 0.01, extra_retries: 99, max_tokens: 262144 });
});

test("新增模型默认启用，编辑配置不改变启停状态", async ({ page }) => {
  let created: Record<string, unknown> | undefined;
  let edited: Record<string, unknown> | undefined;
  const disabledModel = { ...models[0], enabled: false };
  await page.route("**/api/v1/llm/models", async (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: { items: [disabledModel] } });
    }
    created = route.request().postDataJSON();
    await route.fulfill({ json: { ...models[0], id: 100 } });
  });
  await page.route("**/api/v1/llm/models/1", async (route) => {
    edited = route.request().postDataJSON();
    await route.fulfill({ json: disabledModel });
  });
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: /管理模型/ }).click();
  await page.getByRole("button", { name: "新增模型", exact: true }).click();
  const createDialog = page.getByRole("dialog", { name: "新增模型", exact: true });
  await createDialog.getByLabel("模型 ID", { exact: true }).fill("new-model");
  await createDialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(createDialog).not.toBeVisible();
  expect(created).toMatchObject({ model_id: "new-model", enabled: true,
    timeout_seconds: 10, total_timeout_seconds: null });
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  const editDialog = page.getByRole("dialog", { name: "编辑模型", exact: true });
  await expect(editDialog.getByRole("switch")).toHaveCount(0);
  await editDialog.getByLabel("名称", { exact: true }).fill("仍然停用的模型");
  await editDialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(editDialog).not.toBeVisible();
  expect(edited).toMatchObject({ display_name: "仍然停用的模型", revision: 7 });
  expect(edited).not.toHaveProperty("enabled");
  await expect(page.getByRole("switch", { name: "测试模型 1启用状态" })).not.toBeChecked();
});

test("模型单次总时限允许清空，零值不能保存", async ({ page }, testInfo) => {
  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/v1/llm/models", (route) => route.fulfill({ json: {
    items: [{ ...models[0], total_timeout_seconds: 120 }],
  } }));
  await page.route("**/api/v1/llm/models/1", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ json: { ...models[0], total_timeout_seconds: null } });
  });
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: /管理模型/ }).click();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "编辑模型", exact: true });
  const total = dialog.getByLabel("单次请求总时限（秒）", { exact: true });
  await expect(total).toHaveValue("120");
  await expect(dialog.getByLabel("响应间隔超时（秒）", { exact: true })).toHaveValue("90");
  await total.fill("0");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog.getByText("请输入大于 0 的秒数，或留空关闭", { exact: true })).toBeVisible();
  expect(submitted).toBeUndefined();
  await total.fill("");
  await dialog.screenshot({ path: testInfo.outputPath("model-timeouts.png") });
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(submitted).toMatchObject({ total_timeout_seconds: null, timeout_seconds: 90 });
});

test("模型列表直接启停，失败保留原状态并使用当前版本", async ({ page }) => {
  let current = { ...models[0]! };
  const updates: { enabled: boolean; revision: number }[] = [];
  await page.route("**/api/v1/llm/models", (route) =>
    route.fulfill({ json: { items: [current] } }),
  );
  await page.route("**/api/v1/llm/models/1", async (route) => {
    const update = route.request().postDataJSON();
    updates.push(update);
    if (updates.length === 2) {
      return route.fulfill({
        status: 412, json: { error: { message: "模型状态更新失败，请重试" } },
      });
    }
    current = { ...current, enabled: update.enabled, revision: current.revision + 1 };
    await route.fulfill({ json: current });
  });
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: /管理模型/ }).click();
  const toggle = page.getByRole("switch", { name: "测试模型 1启用状态", exact: true });
  await expect(toggle).toBeChecked();
  await toggle.click();
  await expect(toggle).not.toBeChecked();
  await expect(toggle).toBeEnabled();
  await toggle.click();
  await expect(page.getByRole("alert").filter({ hasText: "模型状态更新失败，请重试" }).first()).toBeVisible();
  await expect(toggle).not.toBeChecked();
  await expect(toggle).toBeEnabled();
  await toggle.click();
  await expect(toggle).toBeChecked();
  expect(updates).toEqual([
    { enabled: false, revision: 7 }, { enabled: true, revision: 8 },
    { enabled: true, revision: 8 },
  ]);
  await expect(page.getByRole("dialog", { name: "编辑模型", exact: true })).toHaveCount(0);
});

test("模型删除失败保留确认框，重试成功后移除模型", async ({ page }) => {
  let attempts = 0;
  let deleted = false;
  await page.route("**/api/v1/llm/models", (route) => route.fulfill({
    json: { items: deleted ? models.filter((model) => model.id !== 1) : models },
  }));
  await page.route("**/api/v1/llm/models/1", (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    if (++attempts === 1) return route.fulfill({
      status: 409, json: { error: { message: "模型删除失败，请重试" } },
    });
    deleted = true;
    return route.fulfill({ json: { status: "deleted" } });
  });
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: /管理模型/ }).click();
  const panel = page.getByRole("tabpanel", { name: /管理模型/ });
  const row = panel.getByRole("row").filter({ has: page.getByText("测试模型 1", { exact: true }) });
  await row.getByRole("button", { name: "删除", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByRole("button", { name: /删除/ });
  await confirm.click();
  await expect(page.getByRole("alert").filter({ hasText: "模型删除失败，请重试" }).first()).toBeVisible();
  await expect(dialog).toBeVisible();
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(dialog).not.toBeVisible();
  await expect(panel.getByText("测试模型 1", { exact: true })).toHaveCount(0);
  expect(attempts).toBe(2);
});

test("功能大预算可保存，候选上限继续读取服务端规则", async ({ page }) => {
  let saved: unknown;
  await page.route("**/api/v1/llm/settings", (route) => route.fulfill({ json: {
    secret_key_ready: true, test_valid_seconds: 3600, adapter_profiles: [profile],
    max_bindings: 10,
    feature_fields: {
      failover_limit: { type: "integer", min: 1, max: 10 },
      max_total_requests: { type: "integer", min: 1 },
    },
  } }));
  await page.route("**/api/v1/llm/features/analysis/models", async (route) => {
    saved = route.request().postDataJSON();
    await route.fulfill({ json: {} });
  });
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: "分配功能", exact: true }).click();
  const candidates = page.getByLabel("不同候选上限", { exact: true });
  await expect(candidates).toHaveAttribute("max", "10");
  await candidates.fill("11");
  await expect(page.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await candidates.fill("10");
  await page.getByLabel("总请求上限", { exact: true }).fill("1000");
  await expect(page.getByLabel("调用总时间", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect.poll(() => saved).toMatchObject({
    failover_limit: 10, max_total_requests: 1000,
  });
});

test("功能顺序支持置顶、置底和直接选第10位，保存顺序与界面一致", async ({ page }) => {
  let submitted: { model_ids: number[] } | undefined;
  await page.route("**/api/v1/llm/features", (route) => route.fulfill({ json: { items: [{
    key: "analysis", name: "招标专题解析", required_kind: "language", revision: 1,
    description: "指定专题重新解析也使用此绑定。", failover_limit: 3,
    max_total_requests: 6,
    bindings: models.slice(0, 10).map((model, index) => ({
      model_row_id: model.id, priority: index + 1,
    })),
  }] } }));
  await page.route("**/api/v1/llm/features/analysis/models", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ json: {} });
  });
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: "分配功能", exact: true }).click();
  await expect(page.getByText("指定专题重新解析也使用此绑定。", { exact: true })).toBeVisible();
  const rows = page.getByRole("region", { name: "功能模型列表" }).locator("tbody tr");
  await page.getByRole("button", { name: "测试模型 10置顶", exact: true }).click();
  await expect(rows.first()).toContainText("model-10");
  await page.getByRole("button", { name: "测试模型 10置底", exact: true }).click();
  await expect(rows.last()).toContainText("model-10");
  await page.getByRole("combobox", { name: "测试模型 1优先级", exact: true }).click();
  await page.locator(".ant-select-dropdown:visible").getByTitle("10 · 备选", { exact: true }).click();
  await expect(rows.last().locator(".font-medium")).toHaveText("测试模型 1");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect.poll(() => submitted?.model_ids).toEqual([2, 3, 4, 5, 6, 7, 8, 9, 10, 1]);
});

test("执行中取消持续刷新，退出后只补跑选中的已取消模块", async ({ page }) => {
  let phase = "running";
  let retried: unknown;
  await page.route("**/api/v1/projects/1/analysis", (route) => route.fulfill({ json: {
    analysis_category: "goods", analysis_topics: [], lots: [], sources: [],
    categories: { goods: "货物" }, topics: {},
    reports: [{ id: 1, status: phase === "running" ? "running" : "canceled" }],
  } }));
  await page.route("**/api/v1/analysis/reports/1", (route) => route.fulfill({ json: {
    id: 1, status: phase === "running" ? "running" : "canceled",
    canceling: phase === "stopping", category: "goods", topics: [], coverage: {},
    modules: [
      { id: 1, module_key: "project_basic_info_parsing", title: "项目概况",
        status: phase === "stopped" ? "canceled" : "running", items: [] },
      { id: 2, module_key: "deposit_requirement_parsing", title: "保证金要求",
        status: phase === "running" ? "pending" : "canceled", items: [] },
    ],
  } }));
  await page.route("**/api/v1/analysis/reports/1/cancel", async (route) => {
    phase = "stopping";
    await route.fulfill({ json: { status: "canceled", canceling: true } });
  });
  await page.route("**/api/v1/analysis/reports/1/retry", async (route) => {
    retried = route.request().postDataJSON();
    await route.fulfill({ json: { id: 1, status: "pending" } });
  });
  await page.goto("/projects/1");
  await page.getByRole("button", { name: "取消任务", exact: true }).click();
  await expect(page.getByText("正在停止分析，结束后可继续未完成的专题。")).toBeVisible();
  await selectModule(page, 2);
  await page.locator(".module-operations > summary").click();
  const retry = page.getByRole("button", { name: "重新解析本模块", exact: true });
  await expect(retry).toBeDisabled();
  phase = "stopped";
  await expect(retry).toBeEnabled({ timeout: 10000 });
  await retry.click();
  await expect.poll(() => retried).toEqual({
    module_keys: ["deposit_requirement_parsing"], mode: "restart",
  });
});

test("上传默认省略解析参数，让配置中心决定任务默认值", async ({ page }) => {
  let multipart = "";
  await page.route("**/api/v1/projects/1/files", async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    multipart = route.request().postData() ?? "";
    await route.fulfill({ json: { added: [], jobs: [], skipped: [] } });
  });
  await page.goto("/projects/1/files");
  await page.getByText("解析选项与上传限制", { exact: false }).click();
  await expect(page.getByLabel("解析方式", { exact: true }).locator("xpath=..")).toContainText("使用配置中心默认值");
  await page.locator('input[type="file"]').setInputFiles({
    name: "预算测试.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-fixture"),
  });
  await page.getByRole("button", { name: "上传 1 个文件", exact: true }).click();
  await expect.poll(() => multipart).toContain('name="files"');
  expect(multipart).not.toContain('name="tier"');
  expect(multipart).not.toContain('name="ocr_mode"');
});

test("长列表底部编辑模型，弹窗和保存按钮可见，关闭后返回原操作", async ({
  page,
}) => {
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: /管理模型/ }).click();
  const edit = page.getByRole("button", { name: "编辑", exact: true }).last();
  await edit.scrollIntoViewIfNeeded();
  await edit.click();
  const dialog = page.getByRole("dialog", { name: "编辑模型", exact: true });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "保存", exact: true }),
  ).toBeInViewport();
  await expect(dialog.getByLabel("名称", { exact: true })).toHaveValue(
    "测试模型 10",
  );
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(edit).toBeInViewport();
});

test("保存失败保留模型草稿；重试成功只发送一次保存", async ({ page }) => {
  let writes = 0;
  let fail = true;
  await page.route("**/api/v1/llm/models/1", async (route) => {
    writes++;
    await route.fulfill(
      fail
        ? {
            status: 409,
            json: { error: { message: "版本已变化，请刷新后重试" } },
          }
        : { json: models[0] },
    );
  });
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: /管理模型/ }).click();
  await page.getByRole("button", { name: "编辑", exact: true }).first().click();
  const dialog = page.getByRole("dialog", { name: "编辑模型", exact: true });
  await dialog.getByLabel("名称", { exact: true }).fill("修改后的模型名");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog.getByText("版本已变化，请刷新后重试")).toBeVisible();
  await expect(dialog.getByLabel("名称", { exact: true })).toHaveValue(
    "修改后的模型名",
  );
  expect(writes).toBe(1);
  fail = false;
  const save = dialog.getByRole("button", { name: /保存/ });
  await expect(save).toBeEnabled();
  await save.click();
  await expect(dialog).not.toBeVisible();
  expect(writes).toBe(2);
});

test("供应商表单校验地址，未保存修改关闭前可选择继续编辑", async ({ page }) => {
  await page.goto("/settings/models");
  await page.getByRole("button", { name: "新增供应商", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "新增供应商", exact: true });
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog.getByText("请输入供应商名称")).toBeVisible();
  await dialog.getByLabel("名称", { exact: true }).fill("新供应商");
  await dialog.getByLabel("服务地址（Base URL）").fill("invalid-url");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(
    dialog.getByText("请输入完整的 http:// 或 https:// 地址"),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("button", { name: "继续编辑", exact: true }).click();
  await expect(dialog.getByLabel("名称", { exact: true })).toHaveValue(
    "新供应商",
  );
});

test("项目弹窗校验空白名称，提交期间禁止重复请求", async ({ page }) => {
  let writes = 0;
  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() === "GET") {
      await route.fallback();
      return;
    }
    writes++;
    await new Promise((resolve) => setTimeout(resolve, 500));
    await route.fulfill({ json: { id: 100 } });
  });
  await page.goto("/projects");
  await page
    .getByRole("button", { name: "新建项目", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog", { name: "新建项目", exact: true });
  await dialog.getByLabel("项目名称", { exact: true }).fill("   ");
  await dialog.getByRole("button", { name: "创建项目", exact: true }).click();
  await expect(dialog.getByText("请输入项目名称")).toBeVisible();
  expect(writes).toBe(0);
  await dialog.getByLabel("项目名称", { exact: true }).fill("项目甲");
  await dialog.getByRole("button", { name: "创建项目", exact: true }).click();
  await expect(dialog.getByLabel("项目名称", { exact: true })).toBeDisabled();
  await expect(dialog).not.toBeVisible();
  expect(writes).toBe(1);
});

test("知识库首次加载失败可重试，新建在弹窗中完成", async ({ page }) => {
  let first = true;
  await page.route("**/api/v1/knowledge/collections", async (route) => {
    if (first) {
      first = false;
      await route.fulfill({
        status: 503,
        json: { error: { message: "服务暂时不可用" } },
      });
    } else await route.fallback();
  });
  await page.goto("/knowledge");
  await expect(page.getByText("服务暂时不可用")).toBeVisible();
  await expect(page.getByText("正在加载知识库")).not.toBeVisible();
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.getByRole("link", { name: "测试知识库" })).toBeVisible();
  await page.getByRole("button", { name: "新建知识库", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "新建知识库", exact: true });
  await dialog.getByLabel("知识库名称").fill("新资料库");
  await dialog.getByRole("button", { name: "创建知识库", exact: true }).click();
  await expect(dialog).not.toBeVisible();
});

test("文件重解析与删除都显示确认弹窗，取消不发送写请求", async ({ page }) => {
  let writes = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/") && request.method() !== "GET")
      writes++;
  });
  await page.goto("/projects/1/files");
  await page.getByRole("button", { name: "重新解析", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("重新生成解析批次和原文位置");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("报告引用会标记为不可用");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "取消", exact: true })
    .click();
  expect(writes).toBe(0);
});

test("配置版本详情使用抽屉，切换版本不会沿用旧内容", async ({ page }) => {
  await page.goto("/settings/config");
  await page.getByRole("tab", { name: "版本与发布" }).click();
  await page.getByRole("button", { name: "查看详情" }).nth(1).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("配置版本 v2");
  await expect(dialog).toBeInViewport();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "查看详情" }).nth(2).click();
  await expect(page.getByRole("dialog")).toContainText("配置版本 v3");
});

test("调用链抽屉读取全部分页，超过 25 次请求不会截断", async ({ page }) => {
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: "调用记录" }).click();
  await page.getByRole("button", { name: "查看调用链" }).first().click();
  const dialog = page.getByRole("dialog", { name: "完整调用链" });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByText("请求模型 30 · 测试供应商", { exact: true }),
  ).toBeAttached();
});

test("失败请求在记录详情和调用链中展示完整上游响应", async ({ page }) => {
  const body = JSON.stringify({ error: {
    message: "账户余额不足" + "x".repeat(700),
    code: "insufficient_quota", request_id: "upstream-123",
    detail: "<script>window.upstreamExecuted=true</script>",
  } }, null, 2);
  const errorMessage = `Agent 模型连接失败或暂不可用（RateLimitError）：HTTP 429\n上游响应：\n${body}`;
  await page.route("**/api/v1/llm/calls**", (route) => route.fulfill({ json: {
    total: 1, items: [{ ...calls[0], status: "error", http_status: 429, error_message: errorMessage }],
  } }));
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: "调用记录" }).click();
  await page.getByRole("button", { name: "展开行" }).first().click();
  const detail = page.locator(".ant-table-expanded-row article");
  await expect(detail).toContainText("HTTP 429");
  await expect(detail.getByText(errorMessage, { exact: true })).toBeVisible();
  await expect(detail).toContainText("upstream-123");
  await page.getByRole("button", { name: "查看调用链" }).first().click();
  const dialog = page.getByRole("dialog", { name: "完整调用链" });
  await expect(dialog.getByText(errorMessage, { exact: true })).toBeVisible();
  // 上游可能返回 HTML；只能作为可读文本展示，不能执行供应商返回的脚本。
  expect(await page.evaluate(() => "upstreamExecuted" in window)).toBe(false);
  const error = dialog.locator("article p").filter({ hasText: "上游响应：" });
  expect(await error.evaluate((node) => getComputedStyle(node).whiteSpace)).toBe("pre-wrap");
  expect(await dialog.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
});

test("主要页面和长表单不撑破窄屏", async ({ page }) => {
  for (const path of [
    "/projects",
    "/knowledge",
    "/settings/models",
    "/settings/config",
    "/projects/1/files",
    "/knowledge/1",
    "/projects/1",
  ]) {
    await page.goto(path);
    await expect(page.locator("#main-content")).toBeVisible();
    await expect
      .poll(
        () =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth + 1,
          ),
        { message: path },
      )
      .toBe(true);
  }
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: /管理模型/ }).click();
  await page.getByRole("button", { name: "新增模型", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "新增模型", exact: true });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "保存", exact: true }),
  ).toBeInViewport();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    )
    .toBe(true);
});

test("导入模型的选择和提交位于弹窗，保留选中的模型 ID", async ({ page }) => {
  let submitted: { model_ids: string[] } | undefined;
  await page.route("**/api/v1/llm/providers/1/models/import", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ json: { imported: 1 } });
  });
  await page.goto("/settings/models");
  await page.getByRole("button", { name: "拉取模型", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "导入模型 · 测试供应商" });
  await expect(dialog).toBeVisible();
  await dialog
    .getByRole("row")
    .filter({ hasText: "model-a" })
    .getByRole("checkbox")
    .check();
  await dialog.getByRole("button", { name: "导入 1 个模型" }).click();
  await expect(dialog).not.toBeVisible();
  expect(submitted?.model_ids).toEqual(["model-a"]);
});

test("知识库重命名预填当前名称，删除失败与取消后仍可操作", async ({ page }) => {
  let attempts = 0;
  await page.route("**/api/v1/knowledge/collections/1", (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    attempts++;
    return route.fulfill({ status: 409, json: { error: { message: "知识库删除失败，请重试" } } });
  });
  await page.goto("/knowledge/1");
  await page.getByRole("button", { name: "重命名", exact: true }).click();
  const dialog = page.getByRole("dialog", {
    name: "重命名知识库",
    exact: true,
  });
  await expect(dialog.getByLabel("知识库名称")).toHaveValue("测试知识库");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("button", { name: "删除知识库", exact: true }).click();
  const confirm = page.getByRole("dialog");
  await confirm.getByRole("button", { name: "删除知识库", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "知识库删除失败，请重试" }).first()).toBeVisible();
  await expect(confirm).toBeVisible();
  await expect(confirm.getByRole("button", { name: /删除知识库/ })).toBeEnabled();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "取消", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "重命名", exact: true }),
  ).toBeEnabled();
  expect(attempts).toBe(1);
});

test("知识库资料删除失败可重试，成功后清除已删除资料", async ({ page }) => {
  let attempts = 0;
  let deleted = false;
  const source: KnowledgeSource = {
    source_id: 1, collection_id: 1, project_id: 1, project_file_id: 1,
    file_name: "测试资料.pdf", version_id: 1, parse_run_id: 1, state: "ready", purpose: "company",
    index_status: "completed", index_error: null, error_message: null, embedding_model_id: null,
  };
  await page.route("**/api/v1/knowledge/collections/1", (route) => route.fulfill({
    json: { ...collections[0], file_count: deleted ? 0 : 1, sources: deleted ? [] : [source] },
  }));
  await page.route("**/api/v1/projects/1/files/1", (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    if (++attempts === 1) return route.fulfill({
      status: 409, json: { error: { message: "资料删除失败，请重试" } },
    });
    deleted = true;
    return route.fulfill({ status: 204 });
  });
  await page.goto("/knowledge/1");
  const row = page.getByRole("row").filter({ has: page.getByText("测试资料.pdf", { exact: true }) });
  await row.getByRole("button", { name: "删除", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByRole("button", { name: /删除资料/ });
  await confirm.click();
  await expect(page.getByRole("alert").filter({ hasText: "资料删除失败，请重试" }).first()).toBeVisible();
  await expect(dialog).toBeVisible();
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByText("测试资料.pdf", { exact: true })).toHaveCount(0);
  expect(attempts).toBe(2);
});

test("上传组件选择文件不会自动提交，多个 ZIP 给出明确反馈", async ({
  page,
}) => {
  let writes = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/") && request.method() !== "GET")
      writes++;
  });
  await page.goto("/projects/1/files");
  await page.locator('input[type="file"]').setInputFiles([
    { name: "a.zip", mimeType: "application/zip", buffer: Buffer.from("test") },
    { name: "b.zip", mimeType: "application/zip", buffer: Buffer.from("test") },
  ]);
  await expect(
    page.getByRole("region", { name: "上传文件" }).getByRole("alert").filter({ hasText: "一次只能上传一个 ZIP" }),
  ).toBeVisible();
  await page
    .locator('input[type="file"]')
    .setInputFiles([
      {
        name: "文档.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("test"),
      },
    ]);
  await expect(
    page.getByRole("button", { name: "上传 1 个文件" }),
  ).toBeVisible();
  expect(writes).toBe(0);
});

test("切换报告与问答视图保留问题草稿", async ({ page }) => {
  await page.goto("/projects/1");
  await page.getByText("项目问答", { exact: true }).click();
  await page
    .getByRole("textbox", { name: "输入资料问题" })
    .fill("资格条件需要什么证明？");
  await page.getByText("分析报告", { exact: true }).click();
  await page.getByText("项目问答", { exact: true }).click();
  await expect(page.getByRole("textbox", { name: "输入资料问题" })).toHaveValue(
    "资格条件需要什么证明？",
  );
});

test("标准 Markdown 表格与行内定位同时保留，重复引用只显示一个入口", async ({
  page,
}) => {
  const citation = {
    source_id: 1,
    collection_id: 1,
    project_id: 1,
    project_file_id: 1,
    version_id: 1,
    parse_run_id: 1,
    element_id: 1,
    anchor: "p1b1",
    page_no: 1,
    bbox: null,
    file_name: "招标原文.pdf",
    purpose: "tender",
    quote: "项目预算为 100 万元",
  };
  await page.route("**/api/v1/projects/1/analysis", (route) =>
    route.fulfill({
      json: {
        analysis_category: "goods",
        analysis_topics: [],
        lots: [],
        sources: [],
        reports: [{ id: 1, status: "completed" }],
        categories: { goods: "货物" },
        topics: {},
      },
    }),
  );
  await page.route("**/api/v1/analysis/reports/1", (route) =>
    route.fulfill({
      json: {
        id: 1,
        status: "completed",
        category: "goods",
        topics: [],
        coverage: {},
        modules: [
          {
            id: 1,
            module_key: "base",
            title: "基本信息",
            status: "completed",
            items: [
              {
                id: "budget",
                field: "预算",
                group: "项目",
                sort_order: 1,
                values: [
                  { value: "**100 万元**", citations: [citation, citation] },
                ],
                note: "需核对\n\n补充说明",
                verification: "supported",
              },
              {
                id: "table",
                field: "清单",
                group: "项目",
                sort_order: 2,
                values: [
                  {
                    value: "| 名称 | 数量 |\n| --- | --- |\n| 设备 | 2 |",
                    citations: [],
                  },
                ],
                note: "",
                verification: "supported",
              },
            ],
          },
        ],
      },
    }),
  );
  await page.goto("/projects/1");
  const row = page.locator('[data-report-item="budget"]');
  await expect(row.locator("strong")).toHaveText("100 万元");
  await expect(row.locator(".value-locates button")).toHaveCount(1);
  await expect(row.locator(".field-value > p > .value-locates")).toHaveCount(1);
  await expect(
    page.locator('[data-report-item="table"] td table'),
  ).toContainText("设备");
  await expect(page.locator("p p")).toHaveCount(0);
});
