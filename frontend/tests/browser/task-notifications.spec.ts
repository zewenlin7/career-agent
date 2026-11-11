import { test, expect } from "@playwright/test";
import { id } from "../fixtures/product-api";
const root = `/applications/${id(1)}`;
const handle = (n: number) => ({
  key: `product-drafts:${id(n)}`,
  family: "product-drafts",
  id: id(n),
  title: "简历调整",
  href: `${root}/apply/resume`,
});

test("notifications queue, collapse without acknowledgement, survive reload and handle only explicitly", async ({
  page,
}) => {
  await page.addInitScript(
    ({ handles }) => {
      if (!localStorage.getItem("career-task-handles-v1"))
        localStorage.setItem("career-task-handles-v1", JSON.stringify(handles));
    },
    { handles: [handle(901), handle(902)] },
  );
  await page.route("**/api/product/task-status/product-drafts/*", (route) =>
    route.fulfill({
      json: { state: "failure", reason: "output_validation_failed", selection: {} },
    }),
  );
  await page.goto(`${root}/apply/greeting`);
  const notice = page.getByRole("complementary", { name: "任务通知" });
  await expect(
    notice.getByText("简历调整失败：生成内容未通过校验。", { exact: true }),
  ).toBeVisible();
  await expect(notice.getByRole("link")).toHaveCount(0);
  await expect(notice).toHaveCSS("position", "fixed");
  await page.clock.install();
  await page.clock.fastForward(8100);
  await expect(page.getByLabel("未处理通知 2 条")).toBeVisible();
  await page.getByLabel("未处理通知 2 条").click();
  await expect(notice.getByText("简历调整失败：生成内容未通过校验。", { exact: true })).toHaveCount(
    2,
  );
  await page.getByRole("heading", { name: "招呼语", exact: true }).click();
  await expect(page.getByLabel("未处理通知").filter({ hasText: "简历调整" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByLabel("未处理通知 2 条")).toBeVisible();
  await page.getByLabel("未处理通知 2 条").click();
  await notice.getByLabel("关闭简历调整通知").first().click();
  await expect(page.getByLabel("未处理通知 1 条")).toBeVisible();
  await notice.getByLabel("关闭简历调整通知").click();
  await expect(notice).toHaveCount(0);
  await page.reload();
  await expect(notice).toHaveCount(0);
});

test("successful notification carries exact result and dismisses without execution", async ({
  page,
}) => {
  const writes: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST") writes.push(r.url());
  });
  await page.addInitScript(
    ({ task }) => localStorage.setItem("career-task-handles-v1", JSON.stringify([task])),
    { task: handle(903) },
  );
  await page.route("**/api/product/task-status/product-drafts/*", (route) =>
    route.fulfill({ json: { state: "success", selection: { result: id(8101) } } }),
  );
  await page.goto(`${root}/apply/greeting`);
  const result = page
    .getByRole("complementary", { name: "任务通知" })
    .getByRole("link", { name: "查看结果" });
  await expect(result).toHaveAttribute("href", `${root}/apply/resume?result=${id(8101)}`);
  await result.click();
  await expect(page).toHaveURL(new RegExp(`/apply/resume\\?result=${id(8101)}`));
  await expect(page.getByRole("complementary", { name: "任务通知" })).toHaveCount(0);
  expect(writes).toEqual([]);
});

test("hover and keyboard focus pause collapse, while unread remains", async ({ page }) => {
  await page.addInitScript(
    ({ task }) => localStorage.setItem("career-task-handles-v1", JSON.stringify([task])),
    { task: handle(904) },
  );
  await page.route("**/api/product/task-status/product-drafts/*", (route) =>
    route.fulfill({ json: { state: "unknown", reason: "execution_interrupted", selection: {} } }),
  );
  await page.goto(`${root}/apply/greeting`);
  const popup = page.getByLabel("新通知", { exact: true });
  await expect(popup).toBeVisible();
  await page.clock.install();
  await popup.hover();
  await page.clock.fastForward(10000);
  await expect(popup).toBeVisible();
  await popup.getByRole("button").focus();
  await page.mouse.move(0, 0);
  await page.clock.fastForward(10000);
  await expect(popup).toBeVisible();
  await page.getByRole("heading", { name: "招呼语", exact: true }).click();
  await page.clock.fastForward(8100);
  await expect(popup).toHaveCount(0);
  await expect(page.getByLabel("未处理通知 1 条")).toBeVisible();
});

test("replacement dialog uses readable accepted body typography and keeps cancel separate from saving", async ({
  page,
  request,
}, info) => {
  await request.get("http://127.0.0.1:3111/__reset");
  await page.goto(`${root}/research-fit/company`);
  const style = (el: Element) => ({
    size: getComputedStyle(el).fontSize,
    weight: getComputedStyle(el).fontWeight,
    line: getComputedStyle(el).lineHeight,
  });
  const reference = await page.getByText("公司提供数据服务。", { exact: true }).evaluate(style);
  await page.goto(`${root}/apply/resume`);
  await page.getByRole("button", { name: "开始优化", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "替换当前申请简历？", exact: true });
  await expect(dialog).toBeVisible();
  const body = dialog.getByText("优化简历已保存到简历库，是否将当前申请使用的简历替换为这一份？", {
    exact: true,
  });
  expect(await body.evaluate(style)).toEqual(reference);
  await expect(dialog.getByRole("button", { name: "确认替换", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("replacement-desktop.png") });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: info.outputPath("replacement-narrow.png") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await dialog.getByRole("button", { name: "取消替换", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByLabel("优化记录", { exact: true })).toBeVisible();
});

test("visibility events defer popup time until foreground and preserve remaining duration", async ({
  page,
}) => {
  await page.addInitScript(
    ({ task }) => {
      localStorage.setItem("career-task-handles-v1", JSON.stringify([task]));
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => "hidden",
      });
    },
    { task: handle(905) },
  );
  await page.route("**/api/product/task-status/product-drafts/*", (route) =>
    route.fulfill({ json: { state: "cancelled", selection: {} } }),
  );
  await page.goto(`${root}/apply/greeting`);
  await expect(page.getByLabel("未处理通知 1 条")).toBeVisible();
  await page.clock.install();
  const visibility = (value: string) =>
    page.evaluate((value) => {
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => value });
      document.dispatchEvent(new Event("visibilitychange"));
    }, value);
  await page.clock.fastForward(10000);
  await expect(page.getByLabel("新通知", { exact: true })).toHaveCount(0);
  await visibility("visible");
  await page.clock.runFor(20);
  await expect(page.getByLabel("新通知", { exact: true })).toBeVisible();
  await page.clock.runFor(4000);
  await visibility("hidden");
  await page.clock.fastForward(10000);
  await visibility("visible");
  await page.clock.runFor(2000);
  await expect(page.getByLabel("新通知", { exact: true })).toBeVisible();
  await page.clock.runFor(2100);
  await expect(page.getByLabel("新通知", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("未处理通知 1 条")).toBeVisible();
});

test("binding CAS conflict does not mislabel saved optimization as generation failure", async ({
  page,
  request,
}) => {
  await request.get("http://127.0.0.1:3111/__reset");
  let bindingWrites = 0;
  await page.route("**/api/product/applications/*/context", async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    bindingWrites++;
    await route.fulfill({ status: 409, json: { error: { code: "revision_conflict" } } });
  });
  await page.goto(`${root}/apply/resume`);
  await page.getByRole("button", { name: "开始优化", exact: true }).click();
  await page.getByRole("button", { name: "确认替换", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "简历已保存" })).toHaveText(
    "简历已保存，但申请使用的资料已变化。请重新选择要使用的简历。",
  );
  await expect(page.getByLabel("优化记录", { exact: true })).toBeVisible();
  expect(bindingWrites).toBe(1);
});

test("dismissing last popup does not permanently pause the next notification", async ({ page }) => {
  await page.addInitScript(
    ({ task }) => localStorage.setItem("career-task-handles-v1", JSON.stringify([task])),
    { task: handle(921) },
  );
  await page.route("**/api/product/task-status/product-drafts/*", (route) =>
    route.fulfill({
      json: { state: "failure", reason: "output_validation_failed", selection: {} },
    }),
  );
  await page.clock.install();
  await page.goto(`${root}/apply/greeting`);
  const popup = page.getByLabel("新通知", { exact: true });
  await expect(popup).toBeVisible();
  await popup.getByRole("button").click();
  await expect(page.getByLabel("任务通知", { exact: true })).toHaveCount(0);
  await page.mouse.move(0, 0);
  await page.evaluate((task) => {
    const tasks = JSON.parse(localStorage.getItem("career-task-handles-v1")!);
    tasks.push(task);
    localStorage.setItem("career-task-handles-v1", JSON.stringify(tasks));
    window.dispatchEvent(new Event("career-task-handles"));
  }, handle(922));
  await expect(popup).toBeVisible();
  await page.clock.runFor(8200);
  await expect(popup).toHaveCount(0);
  await expect(page.getByLabel("未处理通知 1 条")).toBeVisible();
  await page.getByLabel("未处理通知 1 条").click();
  await page.mouse.move(0, 0);
  await page.clock.runFor(10000);
  await expect(page.getByLabel("未处理通知", { exact: true })).toBeVisible();
  await page.getByLabel("未处理通知 1 条").click();
  await page.mouse.move(0, 0);
  await page.evaluate((task) => {
    const tasks = JSON.parse(localStorage.getItem("career-task-handles-v1")!);
    tasks.push(task);
    localStorage.setItem("career-task-handles-v1", JSON.stringify(tasks));
    window.dispatchEvent(new Event("career-task-handles"));
  }, handle(923));
  await page.clock.runFor(2600);
  await expect(popup).toBeVisible();
  await page.clock.runFor(8200);
  await expect(popup).toHaveCount(0);
  await expect(page.getByLabel("未处理通知 2 条")).toBeVisible();
});

test("submission section headings and field labels have equal computed typography", async ({
  page,
}, info) => {
  await page.goto(`${root}/apply/submissions`);
  const typography = (element: Element) => {
    const css = getComputedStyle(element);
    return { size: css.fontSize, weight: css.fontWeight, height: css.lineHeight };
  };
  const create = page.getByRole("heading", { name: "新增投递", exact: true });
  await expect(create).toBeVisible();
  expect(
    await page.getByRole("heading", { name: "投递记录", exact: true }).evaluate(typography),
  ).toEqual(await create.evaluate(typography));
  const labels = page.locator("label");
  const resume = await labels.filter({ hasText: /^简历$/ }).evaluate(typography);
  expect(await labels.filter({ hasText: /^招呼语$/ }).evaluate(typography)).toEqual(resume);
  expect(await labels.filter({ hasText: /^备注$/ }).evaluate(typography)).toEqual(resume);
  await page.screenshot({ path: info.outputPath("submission-typography.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.screenshot({
    path: info.outputPath("submission-typography-narrow.png"),
    fullPage: true,
  });
});

test("an unattended notification collapses after eight real foreground seconds", async ({
  page,
}, info) => {
  await page.addInitScript(
    ({ task }) => localStorage.setItem("career-task-handles-v1", JSON.stringify([task])),
    { task: handle(924) },
  );
  await page.route("**/api/product/task-status/product-drafts/*", (route) =>
    route.fulfill({
      json: { state: "failure", reason: "output_validation_failed", selection: {} },
    }),
  );
  await page.goto(`${root}/apply/greeting`);
  const popup = page.getByLabel("新通知", { exact: true });
  await expect(popup).toBeVisible();
  const began = Date.now();
  await expect(popup).toHaveCount(0, { timeout: 11000 });
  const elapsed = Date.now() - began;
  expect(elapsed).toBeGreaterThan(7000);
  await info.attach("foreground-collapse-milliseconds", {
    body: String(elapsed),
    contentType: "text/plain",
  });
  await expect(page.getByLabel("未处理通知 1 条")).toBeVisible();
});
