import { test, expect } from "@playwright/test";
import { collections, mockApi, project } from "./fixtures";

let pageErrors: string[];

test.beforeEach(async ({ page }) => {
  pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await mockApi(page);
});

test.afterEach(() => {
  expect(pageErrors, "操作失败和重试均不能触发浏览器未处理异常").toEqual([]);
});

test("管理列表在桌面和窄屏保持可读", async ({ page }, info) => {
  for (const [name, path] of [["projects", "/projects"], ["files", "/projects/1/files"],
    ["knowledge", "/knowledge"], ["sources", "/knowledge/1"]] as const) {
    await page.goto(path);
    await expect(page.locator("h1")).toBeVisible();
    if (name === "projects") await expect(page.getByText(`${project.name} 1`, { exact: true })).toBeVisible();
    if (name === "files") await expect(page.getByText("招标文件.pdf", { exact: true })).toBeVisible();
    if (name === "knowledge") await expect(page.getByText("测试知识库", { exact: true })).toBeVisible();
    if (name === "sources") await expect(page.getByRole("button", { name: "删除知识库", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true });
  }
  await page.goto("/settings/models");
  const modelsTab = page.getByRole("tab", { name: /管理模型/ });
  await modelsTab.click();
  await expect(modelsTab).toHaveAttribute("aria-selected", "true");
  const modelsPanel = page.getByRole("tabpanel", { name: /管理模型/ });
  await expect(modelsPanel.getByText("测试模型 1", { exact: true })).toBeVisible();
  const row = modelsPanel.getByRole("row").filter({ has: page.getByText("测试模型 1", { exact: true }) });
  expect((await row.boundingBox())!.height).toBeLessThan(120);
  await page.screenshot({ path: info.outputPath("models.png"), fullPage: true });
  const viewport = page.locator(".app-viewport");
  await viewport.evaluate((element) => { element.scrollTop = 400; });
  const menu = page.locator(".page-tabs > .ant-tabs-nav").first();
  await expect.poll(async () => Math.round((await menu.boundingBox())!.y - (await viewport.boundingBox())!.y)).toBe(0);
  await page.screenshot({ path: info.outputPath("models-scrolled.png"), fullPage: true });
});

test("项目编辑、删除确认和失败重试可用", async ({ page }) => {
  let current = { ...project };
  let deleted = false;
  let attempts = 0;
  await page.route("**/api/v1/projects?**", (route) => route.fulfill({ json: { items: deleted ? [] : [current], limit: 100 } }));
  await page.route("**/api/v1/projects/1", async (route) => {
    if (route.request().method() === "PATCH") {
      current = { ...current, ...route.request().postDataJSON() };
      return route.fulfill({ json: current });
    }
    if (route.request().method() === "DELETE") {
      attempts++;
      if (attempts === 1) return route.fulfill({ status: 409, json: { error: { message: "请稍后重试" } } });
      deleted = true;
      return route.fulfill({ status: 204 });
    }
    return route.fallback();
  });
  await page.goto("/projects");
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  const editor = page.getByRole("dialog", { name: "编辑项目" });
  await editor.getByLabel("项目名称", { exact: true }).fill("已修改项目");
  await editor.getByRole("button", { name: "保存修改" }).click();
  await expect(editor).not.toBeVisible();
  await expect(page.getByText("已修改项目", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "删除", exact: true }).click();
  let confirm = page.getByRole("dialog");
  await confirm.getByRole("button", { name: "取消", exact: true }).click();
  await expect(confirm).not.toBeVisible();
  expect(attempts).toBe(0);
  await page.getByRole("button", { name: "删除", exact: true }).click();
  confirm = page.getByRole("dialog");
  const retryDelete = confirm.getByRole("button", { name: /删除项目/ });
  await expect(retryDelete).toBeEnabled();
  await retryDelete.click();
  await expect(page.getByText("请稍后重试")).toBeVisible();
  await expect(confirm).toBeVisible();
  await expect(retryDelete).toBeEnabled();
  await retryDelete.click();
  await expect(confirm).not.toBeVisible();
  await expect(page.getByText("暂无项目，点击新建项目")).toBeVisible();
  expect(attempts).toBe(2);
});

test("卡片与表格保留相同分页并可切换", async ({ page }) => {
  await page.route("**/api/v1/projects?**", (route) => route.fulfill({ json: {
    items: Array.from({ length: 15 }, (_, i) => ({ ...project, id: i + 1, name: `项目 ${i + 1}` })), limit: 100,
  } }));
  await page.goto("/projects");
  await expect(page.getByText("项目 1", { exact: true })).toBeVisible();
  await page.locator(".ant-pagination-item-2").click();
  await expect(page.getByText("项目 13", { exact: true })).toBeVisible();
  await expect(page.getByText("第 13–15 项，共 15 项")).toBeVisible();
  await page.getByText("列表视图", { exact: true }).click();
  await expect(page.getByRole("columnheader", { name: "项目名称 / 编号" })).toBeVisible();
  await expect(page.getByText("项目 13", { exact: true })).toBeVisible();
  await expect(page.getByText("第 13–15 项，共 15 项")).toBeVisible();
  await page.getByText("卡片视图", { exact: true }).click();
  await expect(page.locator(".project-summary-card")).toHaveCount(3);
});

test("知识库删除失败可重试，项目资料库提供项目入口", async ({ page }) => {
  let deleted = false;
  let attempts = 0;
  await page.route("**/api/v1/knowledge/collections", (route) => route.fulfill({ json: { items: [
    ...(deleted ? [] : collections), { ...collections[0], id: 2, is_project: true, name: "项目资料" },
  ] } }));
  await page.route("**/api/v1/knowledge/collections/1", async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    if (++attempts === 1) return route.fulfill({
      status: 409, json: { error: { message: "知识库删除失败，请重试" } },
    });
    deleted = true; return route.fulfill({ json: { deleted: true } });
  });
  await page.goto("/knowledge");
  await page.getByRole("button", { name: "删除", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByRole("button", { name: /删除知识库/ });
  await confirm.click();
  await expect(page.getByText("知识库删除失败，请重试", { exact: true })).toBeVisible();
  await expect(dialog).toBeVisible();
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page.getByText("测试知识库", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "查看项目", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "删除", exact: true })).toHaveCount(0);
  expect(attempts).toBe(2);
});

test("文件重命名、下载、换版和删除入口完整", async ({ page }) => {
  let files = [...project.files];
  let replaceBody = "";
  await page.route("**/api/v1/projects/1", (route) => route.fulfill({ json: { ...project, files } }));
  await page.route("**/api/v1/projects/1/files/1", async (route) => {
    if (route.request().method() === "PATCH") {
      files = [{ ...files[0], ...route.request().postDataJSON() }];
      return route.fulfill({ json: files[0] });
    }
    files = []; return route.fulfill({ status: 204 });
  });
  await page.route("**/api/v1/projects/1/files/1/replace", async (route) => {
    replaceBody = route.request().postData() ?? "";
    return route.fulfill({ json: { added: { project_file_id: 2 }, jobs: [] } });
  });
  await page.goto("/projects/1/files");
  await expect(page.getByRole("link", { name: "下载原件" })).toHaveAttribute("href", "/api/v1/projects/1/files/1/original");
  await page.getByRole("button", { name: "重命名", exact: true }).click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel("文件名称", { exact: true }).fill("修改后的标书");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("修改后的标书.pdf", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "上传新版本", exact: true }).click();
  dialog = page.getByRole("dialog");
  await dialog.locator('input[type="file"]').setInputFiles({ name: "新版.pdf", mimeType: "application/pdf", buffer: Buffer.from("sample") });
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(replaceBody).toContain('name="tier"\r\n\r\nadvanced');
  expect(replaceBody).toContain('name="ocr_mode"\r\n\r\nocr');
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByText("这个项目还没有文件")).toBeVisible();
});

test("窄屏操作列不遮挡文件和模型名称", async ({ page }) => {
  test.skip((page.viewportSize()?.width ?? 1440) > 767, "仅检查窄屏固定列的覆盖行为");
  for (const [path, name] of [["/projects/1/files", "招标文件.pdf"], ["/settings/models", "测试模型 1"]] as const) {
    await page.goto(path);
    if (path === "/settings/models") await page.getByRole("tab", { name: /管理模型/ }).click();
    const title = page.getByText(name, { exact: true });
    await title.scrollIntoViewIfNeeded();
    // 可见性断言不会识别兄弟单元格遮挡；命中测试必须落在名称所在的单元格。
    await expect.poll(() => title.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.left + 4, rect.top + rect.height / 2);
      return hit?.closest("td") === element.closest("td");
    })).toBe(true);
  }
});

test("换版拒绝不同格式，纠正后允许扩展名大小写不同", async ({ page }) => {
  let writes = 0;
  await page.route("**/api/v1/projects/1/files/1/replace", (route) => {
    writes++;
    return route.fulfill({ json: { added: { project_file_id: 2 }, jobs: [] } });
  });
  await page.goto("/projects/1/files");
  await page.getByRole("button", { name: "上传新版本", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const input = dialog.locator('input[type="file"]');
  await input.setInputFiles({ name: "新版.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: Buffer.from("sample") });
  await expect(dialog.getByText("新版本须使用 .pdf 格式，请重新选择文件")).toBeVisible();
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog.getByText("请先选择新版本文件")).toBeVisible();
  expect(writes).toBe(0);
  await input.setInputFiles({ name: "新版.PDF", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7 sample") });
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(writes).toBe(1);
});

test("图纸换版拒绝 PDF，保留原归档格式", async ({ page }) => {
  let writes = 0;
  await page.route("**/api/v1/projects/1", (route) => route.fulfill({ json: {
    ...project, files: [{ ...project.files[0], display_name: "图纸.dwg", is_parseable: false,
      mime: "application/octet-stream", version_id: null, parse_status: null, latest_job: null }],
  } }));
  await page.route("**/api/v1/projects/1/files/1/replace", (route) => {
    writes++;
    return route.fulfill({ json: { added: { project_file_id: 2 }, jobs: [] } });
  });
  await page.goto("/projects/1/files");
  await page.getByRole("button", { name: "上传新版本", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.locator('input[type="file"]').setInputFiles({ name: "新版.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7 sample") });
  await expect(dialog.getByText("新版本须使用 .dwg 格式，请重新选择文件")).toBeVisible();
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog.getByText("请先选择新版本文件")).toBeVisible();
  expect(writes).toBe(0);
});
