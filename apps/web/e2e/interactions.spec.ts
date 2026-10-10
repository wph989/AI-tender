import { test, expect } from "@playwright/test";
import { mockApi, models } from "./fixtures";

let pageErrors: string[];
test.beforeEach(async ({ page }) => {
  pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await mockApi(page);
});
test.afterEach(() => {
  expect(pageErrors, "浏览器未捕获异常").toEqual([]);
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
    "测试模型 8",
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
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
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
  await expect(page.getByRole("heading", { name: "测试知识库" })).toBeVisible();
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
  await expect(dialog).toContainText("3 条已确认结果需要重新复核");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("已抽取的结果");
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

test("知识库重命名预填当前名称，删除取消后仍可操作", async ({ page }) => {
  await page.goto("/knowledge/1");
  await page.getByText("上传与管理资料", { exact: true }).click();
  await page.getByRole("button", { name: "重命名", exact: true }).click();
  const dialog = page.getByRole("dialog", {
    name: "重命名知识库",
    exact: true,
  });
  await expect(dialog.getByLabel("知识库名称")).toHaveValue("测试知识库");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("button", { name: "移除知识库", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "取消", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "重命名", exact: true }),
  ).toBeEnabled();
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
