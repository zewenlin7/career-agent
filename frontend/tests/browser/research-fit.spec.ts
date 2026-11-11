import { test, expect } from "@playwright/test";
import { id } from "../fixtures/product-api";
const root = `/applications/${id(1)}/research-fit`;
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});

test("subpages preserve legacy exact links, expired history and retry identity without execution", async ({
  page,
  request,
}) => {
  const history = await (
    await request.get(`http://127.0.0.1:3111/api/v1/companies/${id(1001)}/research`)
  ).json();
  const rows = Array.from({ length: 101 }, (_, n) => ({
    ...history.items[0],
    id: id(20000 + n),
    fetched_at: "2026-10-01T00:00:00Z",
  }));
  await page.route(`**/api/product/companies/${id(1001)}/research?*`, async (route) => {
    const q = new URL(route.request().url()).searchParams,
      offset = Number(q.get("offset") || 0),
      limit = Number(q.get("limit") || 100);
    await route.fulfill({
      json: {
        items: rows.slice(offset, offset + limit),
        limit,
        offset,
        has_more: offset + limit < rows.length,
      },
    });
  });
  let unavailable = true;
  await page.route(
    `**/api/product/companies/${id(1001)}/research/${rows[100].id}`,
    async (route) => {
      if (unavailable)
        await route.fulfill({ status: 503, json: { error: { code: "request_failed" } } });
      else await route.fulfill({ json: rows[100] });
    },
  );
  await page.goto(`${root}?research=${rows[100].id}`);
  await expect(page).toHaveURL(new RegExp(`/company\\?research=${rows[100].id}$`));
  const selector = page.getByLabel("研究记录");
  await expect(selector.locator("option")).toHaveCount(101);
  await expect(selector).toHaveValue(rows[100].id);
  await expect(
    page.getByRole("region", { name: "公司研究", exact: true }).getByRole("alert"),
  ).toBeVisible();
  unavailable = false;
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.getByText("公司提供数据服务。", { exact: true })).toBeVisible();
  await expect(selector).toHaveValue(rows[100].id);
  await expect(page.getByText("外部证据与来源", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "下一页" })).toHaveCount(0);
  await page.getByRole("button", { name: "研究与匹配" }).click();
  await page.getByRole("menuitem", { name: "职位描述", exact: true }).click();
  await expect(page.getByRole("heading", { name: "职位描述", exact: true })).toHaveCount(1);
  await page.goBack();
  await expect(selector).toHaveValue(rows[100].id);
  const writes = (await (await request.get("http://127.0.0.1:3111/__requests")).json()).filter(
    (r: { method: string }) => r.method !== "GET",
  );
  expect(writes).toEqual([]);
});

test("description uses matching readable dimensions and grows with content on desktop and narrow screen", async ({
  page,
}, info) => {
  await page.goto(`${root}/description`);
  const area = page.locator("#job-description");
  await expect(area.locator("time")).toHaveText("2026-10-24 12:00");
  await page.screenshot({ path: info.outputPath("description-read-desktop.png"), fullPage: true });
  const body = area.locator("p.whitespace-pre-wrap");
  await expect(body).toBeVisible();
  const before = await body.evaluate((el) => ({
    width: el.getBoundingClientRect().width,
    font: getComputedStyle(el).fontSize,
    line: getComputedStyle(el).lineHeight,
  }));
  await area.getByRole("button", { name: "编辑", exact: true }).click();
  const input = area.getByRole("textbox", { name: "职位描述" });
  const edit = await input.evaluate((el) => ({
    width: el.getBoundingClientRect().width,
    font: getComputedStyle(el).fontSize,
    line: getComputedStyle(el).lineHeight,
  }));
  expect(edit).toEqual(before);
  await input.fill(Array.from({ length: 40 }, (_, n) => `职位要求 ${n + 1}`).join("\n"));
  await expect.poll(() => input.evaluate((el) => el.clientHeight)).toBeGreaterThan(800);
  await page.screenshot({
    path: info.outputPath("research-description-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({
    path: info.outputPath("research-description-narrow.png"),
    fullPage: true,
  });
  await area.getByRole("button", { name: "取消", exact: true }).click();
  await expect(input).toHaveCount(0);
});

test("failed explicit research keeps the exact readable report and never resets selection", async ({
  page,
}) => {
  await page.goto(`${root}/company?research=${id(7999)}`);
  const selected = page.getByLabel("研究记录");
  await expect(selected).toHaveValue(id(7999));
  await expect(page.getByText("公司提供数据服务。", { exact: true })).toBeVisible();
  await page.route("**/api/product/operations/*/execute", (route) =>
    route.fulfill({ status: 503, json: { error: { code: "request_failed" } } }),
  );
  await page.getByRole("button", { name: "重新研究", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "公司研究", exact: true }).getByRole("alert"),
  ).toBeVisible();
  await expect(selected).toHaveValue(id(7999));
  await expect(page.getByText("公司提供数据服务。", { exact: true })).toBeVisible();
});

test("company and matching use readable typography and compact subnavigation", async ({
  page,
}, info) => {
  await page.goto(`${root}/company`);
  const conclusion = page.getByText("公司提供数据服务。", { exact: true });
  await expect(conclusion).toBeVisible();
  expect(
    await conclusion.evaluate((el) => ({
      size: getComputedStyle(el).fontSize,
      weight: getComputedStyle(el).fontWeight,
    })),
  ).toEqual({ size: "16px", weight: "400" });
  await page.screenshot({ path: info.outputPath("company-desktop.png"), fullPage: true });
  await page.getByRole("button", { name: "研究与匹配" }).click();
  await page.getByRole("menuitem", { name: "岗位匹配", exact: true }).click();
  await page.getByLabel("简历").selectOption(id(8401));
  await page.getByRole("button", { name: "开始匹配", exact: true }).click();
  await expect(page.getByRole("heading", { name: "不确定", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/fit\?result=/);
  await expect(page.getByRole("heading", { name: "不确定", exact: true })).toBeVisible();
  await expect(page.getByText("本次结果", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("fit-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("fit-narrow.png"), fullPage: true });
});

test("research navigation menu and selector typography", async ({ page }, info) => {
  await page.goto(`${root}/company`);
  const trigger = page.getByRole("button", { name: "研究与匹配" });
  await expect(trigger).toBeVisible();
  await trigger.hover();
  const menu = page.getByRole("menu", { name: "研究与匹配" });
  await expect(menu).toBeVisible();
  await menu.hover();
  await expect(menu).toBeVisible();
  await page.screenshot({ path: info.outputPath("research-menu-desktop.png"), fullPage: true });
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await trigger.click();
  await menu.getByRole("menuitem", { name: "岗位匹配" }).click();
  await expect(page.getByRole("heading", { name: "岗位匹配", exact: true })).toBeVisible();
  await expect(menu).toBeHidden();
  await expect(page.getByText("请选择个人资料或简历。", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "开始匹配" })).toBeDisabled();
  await page.getByLabel("简历", { exact: true }).selectOption(id(8401));
  await page.getByRole("button", { name: "开始匹配", exact: true }).click();
  await expect(page.getByLabel("匹配记录")).toBeVisible();
  for (const label of ["个人资料", "简历", "匹配记录"]) {
    const select = page.getByRole("combobox", { name: label, exact: true });
    await expect(select).toHaveCSS("font-weight", "400");
    await expect(select).toHaveCSS("font-size", "16px");
    await expect(select.locator("option").first()).toHaveCSS("font-weight", "400");
  }
  const profileBox = (await page.getByLabel("个人资料", { exact: true }).boundingBox())!;
  const resumeBox = (await page.getByLabel("简历", { exact: true }).boundingBox())!;
  const actionBox = (await page
    .getByRole("button", { name: "开始匹配", exact: true })
    .boundingBox())!;
  expect(resumeBox.width).toBeGreaterThan(profileBox.width);
  expect(Math.abs(profileBox.y - resumeBox.y)).toBeLessThan(2);
  expect(Math.abs(actionBox.y + actionBox.height - resumeBox.y - resumeBox.height)).toBeLessThan(2);
  const fitBox = (await page.getByLabel("匹配记录").boundingBox())!;
  await page.screenshot({ path: info.outputPath("fit-controls-desktop.png"), fullPage: true });
  await trigger.focus();
  await trigger.press("ArrowDown");
  await expect(menu.getByRole("menuitem").first()).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "公司研究", exact: true })).toBeVisible();
  await expect(page.getByLabel("研究记录")).toHaveCSS("font-weight", "400");
  const box = await page.getByLabel("研究记录").boundingBox();
  const label = await page
    .locator("label")
    .filter({ hasText: /^研究记录$/ })
    .boundingBox();
  expect(Math.abs(box!.y - label!.y)).toBeLessThan(20);
  expect(box!.width).toBeLessThan(350);
  expect(fitBox.width).toBeGreaterThan(box!.width + 100);
  await page.screenshot({ path: info.outputPath("company-controls-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("company-narrow.png"), fullPage: true });
  await trigger.click();
  await page.getByRole("heading", { name: "公司研究", exact: true }).click();
  await expect(menu).toBeHidden();
});

test("Application modules share dropdown navigation without persistent subnav", async ({
  page,
}, info) => {
  await page.goto(root + "/description");
  for (const [module, child, suffix] of [
    ["投递材料", "招呼语", "/apply/greeting"],
    ["面试", "历史面试", "/interview/history"],
    ["复盘", "求职笔记", "/review/knowledge-notes"],
  ]) {
    const trigger = page.getByRole("button", { name: module, exact: true });
    const menu = page.getByRole("menu", { name: module, exact: true });
    await trigger.hover();
    await menu.hover();
    await expect(menu).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    await trigger.click();
    await menu.getByRole("menuitem", { name: child, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(suffix + "$"));
    await expect(menu).toBeHidden();
    await trigger.focus();
    await trigger.press("ArrowDown");
    await expect(menu.getByRole("menuitem").first()).toBeFocused();
    await expect(menu.getByRole("menuitem", { name: child, exact: true })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await page.keyboard.press("Escape");
    await trigger.click();
    await page.getByRole("region", { name: "当前申请", exact: true }).click();
    await expect(menu).toBeHidden();
    await expect(page.locator("nav").filter({ hasText: child })).toHaveCount(0);
  }
  await page.screenshot({ path: info.outputPath("module-navigation.png"), fullPage: true });
});

test("research history failure is not empty and sole referenced refusal preserves exact selection", async ({
  page,
  request,
}) => {
  const base = `http://127.0.0.1:3111/api/v1/companies/${id(1001)}/research`;
  const existing = (await (await request.get(base)).json()).items[0];
  let failed = true;
  await page.route(`**/api/product/companies/${id(1001)}/research?*`, (route) =>
    failed
      ? route.fulfill({ status: 503, json: { error: { code: "request_failed" } } })
      : route.fulfill({ json: { items: [existing], has_more: false, limit: 100, offset: 0 } }),
  );
  await page.goto(`${root}/company`);
  await expect(
    page.getByRole("region", { name: "公司研究", exact: true }).getByRole("alert"),
  ).toBeVisible();
  await expect(page.getByText("暂无记录。", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("研究记录", { exact: true })).toHaveCount(0);
  failed = false;
  await page.reload();
  const selector = page.getByLabel("研究记录", { exact: true });
  await expect(selector).toHaveValue(existing.id);
  const result = page.locator(`[data-result-destination="${existing.id}"]`);
  await expect(result).toBeVisible();
  const body = await result.innerText();
  await page.route(`**/api/product/companies/${id(1001)}/research/${existing.id}`, (route) =>
    route.request().method() === "DELETE"
      ? route.fulfill({ json: { deleted: false, used_by: ["面试准备（合成记录）"] } })
      : route.continue(),
  );
  await page.getByRole("button", { name: "删除记录", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("面试准备");
  await page.getByRole("dialog").getByRole("button", { name: "知道了", exact: true }).click();
  await expect(selector).toHaveValue(existing.id);
  await expect(selector.locator("option")).toHaveCount(1);
  expect(await result.innerText()).toBe(body);
  const writes = (await (await request.get("http://127.0.0.1:3111/__requests")).json()).filter(
    (r: { method: string }) => r.method !== "GET",
  );
  expect(writes).toEqual([]);
});
