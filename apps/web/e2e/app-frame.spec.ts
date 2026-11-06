import { test, expect } from "@playwright/test";
import { collections, mockApi, project } from "./fixtures";

let pageErrors: string[];
test.beforeEach(async ({ page }) => {
  pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await mockApi(page);
  // 项目列表按返回的 limit 补页，夹具也须提供分页字段，避免无限请求。
  const projects = Array.from({ length: 18 }, (_, index) => ({
    ...project, id: index + 1, name: `${project.name} ${index + 1}`,
  }));
  await page.route("**/api/v1/projects?**", (route) => {
    const query = new URL(route.request().url()).searchParams;
    const offset = Number(query.get("offset"));
    const limit = Number(query.get("limit"));
    return route.fulfill({ json: { items: projects.slice(offset, offset + limit), offset, limit } });
  });
  await page.route("**/api/v1/versions/1", (route) => route.fulfill({
    json: { id: 1, project_id: 1, parse_runs: [] },
  }));
  await page.route("**/api/v1/versions/1/pages", (route) => route.fulfill({ json: { pages: [
    { page_no: 1, width_pt: 595, height_pt: 842, rotation: 0, has_text_layer: true },
  ] } }));
  await page.route("**/api/v1/versions/1/elements", (route) => route.fulfill({
    json: { elements: [] },
  }));
  await page.route("**/api/v1/versions/1/outline", (route) => route.fulfill({
    json: { run_id: null, items: [] },
  }));
  await page.route("**/api/v1/versions/1/file", (route) => route.fulfill({
    path: "public/samples/sample-tender.pdf", contentType: "application/pdf",
  }));
});
test.afterEach(() => expect(pageErrors).toEqual([]));

test("顶部导航常驻，长页面独立滚动且切换页面保留同一框架", async ({ page }, info) => {
  await page.goto("/projects");
  const navigation = page.getByRole("navigation", { name: "主导航", exact: true });
  await expect(navigation).toHaveCount(1);
  const header = page.locator(".app-header");
  const originalHeader = await header.elementHandle();
  const viewport = page.locator(".app-viewport");
  await expect(page.getByText("界面验收项目 1", { exact: true })).toBeVisible();
  await viewport.hover();
  await page.mouse.wheel(0, 700);
  await expect.poll(() => viewport.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  await expect.poll(() => header.evaluate((element) => element.getBoundingClientRect().top)).toBe(0);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await navigation.getByRole("link", { name: "知识库", exact: true }).click();
  await expect(page).toHaveURL(/\/knowledge$/, { timeout: 15_000 });
  await expect(navigation.getByRole("link", { name: "知识库", exact: true }))
    .toHaveAttribute("aria-current", "page");
  // 客户端切换应保留原导航节点，并把新页面内容带回顶部。
  expect(await originalHeader!.evaluate((element) => element.isConnected)).toBe(true);
  await expect.poll(() => viewport.evaluate((element) => element.scrollTop)).toBe(0);
  await page.screenshot({ path: info.outputPath("app-frame-navigation.png"), fullPage: true });
});

test("键盘可跳到正文，长页面弹窗不受固定导航遮挡", async ({ page }) => {
  await page.goto("/projects");
  await page.getByRole("link", { name: "跳到主要内容", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
  await page.goto("/settings/models");
  await page.getByRole("tab", { name: /管理模型/ }).click();
  const edit = page.getByRole("button", { name: "编辑", exact: true }).last();
  await edit.scrollIntoViewIfNeeded();
  await edit.click();
  const dialog = page.getByRole("dialog", { name: "编辑模型", exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "保存", exact: true })).toBeInViewport();
  const viewport = page.locator(".app-viewport");
  const previousScroll = await viewport.evaluate((element) => element.scrollTop);
  await dialog.hover();
  await page.mouse.wheel(0, 500);
  expect(await viewport.evaluate((element) => element.scrollTop)).toBe(previousScroll);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(edit).toBeInViewport();
});

test("长页面切换回顶部，前进后退按历史条目恢复各自滚动位置", async ({ page }) => {
  // 两个页面都必须足够长，才能发现持久视口把上一页位置带到下一页的问题。
  await page.route("**/api/v1/knowledge/collections", (route) => route.fulfill({
    json: { items: Array.from({ length: 12 }, (_, index) => ({
      ...collections[0], id: index + 1, name: `滚动验收资料库 ${index + 1}`,
    })) },
  }));
  await page.goto("/projects");
  const viewport = page.locator(".app-viewport");
  const navigation = page.getByRole("navigation", { name: "主导航", exact: true });
  const scrollTop = () => viewport.evaluate((element) => element.scrollTop);
  await expect(page.getByText("界面验收项目 1", { exact: true })).toBeVisible();
  await viewport.evaluate((element) => { element.scrollTop = 450; });
  await expect.poll(scrollTop).toBe(450);
  await navigation.getByRole("link", { name: "知识库", exact: true }).click();
  await expect(page.getByText("滚动验收资料库 1", { exact: true })).toBeVisible();
  await expect.poll(scrollTop).toBe(0);
  // 桌面知识库只略超一屏，使用两端都可到达且与项目页不同的位置。
  await viewport.evaluate((element) => { element.scrollTop = 80; });
  await expect.poll(scrollTop).toBe(80);
  await page.goBack();
  await expect(page).toHaveURL(/\/projects$/);
  await expect.poll(scrollTop).toBe(450);
  await page.goForward();
  await expect(page).toHaveURL(/\/knowledge$/);
  await expect.poll(scrollTop).toBe(80);
  // 再次点击相同入口创建新历史条目，不能套用该 URL 上次留下的位置。
  await navigation.getByRole("link", { name: "项目空间", exact: true }).click();
  await expect(page).toHaveURL(/\/projects$/);
  await expect.poll(scrollTop).toBe(0);
  await viewport.evaluate((element) => { element.scrollTop = 250; });
  await expect.poll(scrollTop).toBe(250);
  await page.goBack();
  await expect(page).toHaveURL(/\/knowledge$/);
  await expect.poll(scrollTop).toBe(80);
  await page.goBack();
  await expect(page).toHaveURL(/\/projects$/);
  await expect.poll(scrollTop).toBe(450);
  await expect.poll(() => page.locator(".app-header")
    .evaluate((element) => element.getBoundingClientRect().top)).toBe(0);
});

test("返回长列表等待异步数据撑开后恢复，并保持正文锚点可用", async ({ page }) => {
  let releaseProjects: () => void = () => {};
  let waitForProjects: Promise<void> | null = null;
  let projectsBlocked = false;
  const projects = Array.from({ length: 18 }, (_, index) => ({
    ...project, id: index + 1, name: `${project.name} ${index + 1}`,
  }));
  await page.route("**/api/v1/projects?**", async (route) => {
    if (waitForProjects) projectsBlocked = true;
    await waitForProjects;
    const query = new URL(route.request().url()).searchParams;
    const offset = Number(query.get("offset")), limit = Number(query.get("limit"));
    await route.fulfill({ json: { items: projects.slice(offset, offset + limit), offset, limit } });
  });
  await page.goto("/projects");
  const viewport = page.locator(".app-viewport");
  const scrollTop = () => viewport.evaluate((element) => element.scrollTop);
  await expect(page.getByText("界面验收项目 1", { exact: true })).toBeVisible();
  await viewport.evaluate((element) => { element.scrollTop = 450; });
  await expect.poll(scrollTop).toBe(450);
  await page.getByRole("navigation", { name: "主导航", exact: true })
    .getByRole("link", { name: "知识库", exact: true }).click();
  await expect(page).toHaveURL(/\/knowledge$/);
  waitForProjects = new Promise<void>((resolve) => { releaseProjects = resolve; });
  await page.goBack();
  await expect(page).toHaveURL(/\/projects$/);
  await expect.poll(() => projectsBlocked).toBe(true);
  await expect(page.getByText("界面验收项目 1", { exact: true })).toHaveCount(0);
  // 明确模拟较慢响应，验证恢复不会因动画结束而过早放弃；位置断言仍等待实际内容。
  await page.waitForTimeout(800);
  releaseProjects();
  await expect(page.getByText("界面验收项目 1", { exact: true })).toBeAttached();
  await expect.poll(scrollTop).toBe(450);
  await page.getByRole("link", { name: "跳到主要内容", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
  await expect.poll(scrollTop).toBe(0);
  await expect.poll(() => page.locator(".app-header")
    .evaluate((element) => element.getBoundingClientRect().top)).toBe(0);
});

test("分析与文档工作台使用导航下方剩余高度，原文滚动不带动外框", async ({ page }, info) => {
  for (const path of ["/projects/1", "/projects/1?view=document"]) {
    await page.goto(path);
    await expect(page.getByRole("navigation", { name: "主导航", exact: true })).toHaveCount(1);
    const workspace = page.locator(".workspace");
    await expect(workspace).toBeVisible();
    await expect.poll(() => page.evaluate(() => {
      const frameViewport = document.querySelector(".app-viewport")!;
      const header = document.querySelector(".app-header")!;
      const workspace = document.querySelector(".workspace")!;
      return Math.abs(workspace.getBoundingClientRect().height -
        (innerHeight - header.getBoundingClientRect().height)) < 1 &&
        frameViewport.scrollHeight <= frameViewport.clientHeight + 1 &&
        document.documentElement.scrollHeight <= innerHeight + 1;
    })).toBe(true);
  }
  const canvas = page.locator(".workspace-body canvas").first();
  await expect(canvas).toBeVisible();
  await page.locator(".workspace-body .viewer-surface").hover();
  await page.mouse.wheel(0, 500);
  await expect.poll(() => page.locator(".app-header")
    .evaluate((element) => element.getBoundingClientRect().top)).toBe(0);
  expect(await page.locator(".app-viewport").evaluate((element) => element.scrollTop)).toBe(0);
  await page.screenshot({ path: info.outputPath("app-frame-workbench.png"), fullPage: true });
});
