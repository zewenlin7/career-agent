import { expect, test } from "@playwright/test";
import { id, application, job, summaryFixture } from "../fixtures/product-api";

test("Applications filters, company discovery, URL pagination and refresh", async ({ page }) => {
  await page.goto("/applications");
  await expect(page.getByRole("list", { name: "申请列表" }).getByRole("listitem")).toHaveCount(20);
  await page
    .getByRole("navigation", { name: "申请分页" })
    .getByRole("link", { name: "下一页" })
    .click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByRole("list", { name: "申请列表" }).getByRole("listitem")).toHaveCount(4);
  await page.reload();
  await expect(page.getByText("第 2 页", { exact: false })).toBeVisible();
  await page.getByLabel("状态", { exact: true }).selectOption("applied");
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(page).not.toHaveURL(/page=2/);
  await expect(page.getByRole("list", { name: "申请列表" }).getByRole("listitem")).toHaveCount(1);
  await page.getByLabel("公司", { exact: true }).fill("晨星");
  await page.getByRole("option", { name: "晨星科技", exact: true }).click();
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`company_ids=${id(1001)}`));
  await expect(page).toHaveURL(/status=applied/);
  await expect(page.getByRole("link", { name: /后端工程师/ })).toBeVisible();
});

test("workspace exact context, same-company switch and inherited placeholder", async ({
  page,
}, info) => {
  await page.goto(`/applications/${id(1)}/summary`);
  const context = page.getByRole("region", { name: "当前申请" });
  await expect(context.getByText("后端工程师", { exact: true })).toBeVisible();
  await expect(context.getByText("已投递", { exact: true })).toBeVisible();
  await expect(context.getByText(id(2001), { exact: true })).toHaveCount(0);
  await context.getByText("同公司职位 / 申请切换", { exact: true }).click();
  await context.getByRole("link", { name: /Agent 工程师/ }).click();
  await expect(page).toHaveURL(new RegExp(`/applications/${id(2)}/summary`));
  await expect(
    page.getByRole("region", { name: "当前申请" }).getByText("面试中", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "投递材料", exact: true }).click();
  await page.getByRole("menuitem", { name: "简历优化", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/applications/${id(2)}/apply/resume`));
  await expect(
    page.getByRole("region", { name: "当前申请" }).getByText("Agent 工程师", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "简历优化", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: info.outputPath("workspace-mobile.png"), fullPage: true });
});

test("Summary has ten aligned cards, bounded notes, Chinese context and no internal versions", async ({
  page,
}, info) => {
  await page.goto(`/applications/${id(1)}/summary`);
  const titles = [
    "职位描述",
    "最新准备结果",
    "当前使用简历",
    "申请状态",
    "最新投递材料",
    "最新模拟面试",
    "真实面试记录",
    "面试复盘",
    "申请笔记",
    "申请记录",
  ];
  for (const title of titles)
    await expect(page.getByRole("region", { name: title, exact: true })).toBeVisible();
  const boxes = await Promise.all(
    titles.map((title) => page.getByRole("region", { name: title, exact: true }).boundingBox()),
  );
  for (let i = 0; i < 10; i += 2) expect(boxes[i]!.y).toEqual(boxes[i + 1]!.y);
  expect(boxes[8]!.height).toBe(boxes[9]!.height);
  await expect(
    page.getByRole("region", { name: "最新准备结果" }).getByText("尚未生成"),
  ).toHaveCount(5);
  await expect(
    page
      .getByRole("region", { name: "当前申请" })
      .getByRole("link", { name: "晨星科技", exact: true }),
  ).toHaveCount(0);
  expect(await page.locator("main").innerText()).not.toMatch(
    /JD|第 2 版|事件序号|generation|selected result/,
  );
  expect(await page.evaluate(() => Object.hasOwn(window, "__injected"))).toBe(false);
  await page.screenshot({ path: info.outputPath("summary-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("summary-mobile.png"), fullPage: true });
  await page.goto(`/applications/${id(24)}/summary`);
  await expect(page.getByText("同公司职位 / 申请切换", { exact: true })).toHaveCount(0);
});

test("bad bindings and invalid queries fail closed without exposing provider errors", async ({
  page,
}) => {
  await page.goto("/applications?status=success");
  await expect(page.getByRole("main").getByRole("alert")).toHaveText("筛选或分页参数无效。");
  await page.goto(`/applications/${id(999)}/summary`);
  await expect(page.getByRole("heading", { name: "申请不可访问" })).toBeVisible();
  await expect(
    page.getByText("该申请已删除或不存在，无法打开工作区。", { exact: true }),
  ).toBeVisible();
  await page.goto(`/applications/${id(88)}/summary`);
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "暂时无法读取申请及职位关联",
  );
  await expect(page.getByRole("region", { name: "当前申请" })).toHaveCount(0);
  await page.goto(`/applications?company_id=${id(1003)}`);
  await expect(page.getByText("当前筛选下没有申请记录。", { exact: true })).toBeVisible();
});

test("Applications/Summary reads stay GET-only, no Internal paths and no Ops header", async ({
  page,
  request,
}) => {
  await page.goto(`/applications/${id(1)}/summary`);
  const calls = await (await request.get("http://127.0.0.1:3111/__requests")).json();
  expect(calls.length).toBeGreaterThan(0);
  for (const call of calls) {
    expect(call.method).toBe("GET");
    expect(call.hasOpsToken).toBe(false);
    expect(call.path).not.toMatch(/\/ops\/|\/evaluation\/|\/execute/);
  }
});

test("filter edits wait for explicit application", async ({ page }) => {
  await page.goto("/applications");
  const items = page.getByRole("list", { name: "申请列表" }).getByRole("listitem");
  await expect(items).toHaveCount(20);
  await page.getByLabel("状态", { exact: true }).selectOption("applied");
  await page.waitForTimeout(500);
  await expect(page).toHaveURL(/\/applications$/);
  await expect(items).toHaveCount(20);
  await page.getByLabel("公司", { exact: true }).fill("晨星");
  await page.getByRole("option", { name: "晨星科技", exact: true }).click();
  await expect(page).toHaveURL(/\/applications$/);
  await expect(items).toHaveCount(20);
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(items).toHaveCount(1);
  await expect(page.getByRole("navigation", { name: "申请分页" })).toHaveCount(0);
});

test("company tags apply together, paging ignores pending edits, clear resets everything", async ({
  page,
}, info) => {
  await page.goto("/applications");
  const items = page.getByRole("list", { name: "申请列表" }).getByRole("listitem");
  const search = page.getByLabel("公司", { exact: true });
  for (const [q, name] of [
    ["晨星", "晨星科技"],
    ["远山", "远山实验室"],
  ]) {
    await search.fill(q);
    await page.getByRole("option", { name, exact: true }).click();
    await expect(search).toHaveValue("");
    await expect(items).toHaveCount(20);
  }
  await search.fill("晨星");
  await expect(page.getByRole("option", { name: "晨星科技", exact: true })).toBeDisabled();
  await expect(page.getByRole("list", { name: "已选公司" }).getByRole("listitem")).toHaveCount(2);
  await search.fill("");
  await page.getByLabel("状态", { exact: true }).selectOption("tracking");
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(page).toHaveURL(/status=tracking/);
  expect(new URL(page.url()).searchParams.getAll("company_ids")).toEqual([id(1001), id(1002)]);
  await page.getByRole("button", { name: "移除远山实验室" }).click();
  await page.getByLabel("状态", { exact: true }).selectOption("applied");
  await page
    .getByRole("navigation", { name: "申请分页" })
    .getByRole("link", { name: "下一页" })
    .click();
  await expect(items).toHaveCount(2);
  await expect(page).toHaveURL(/status=tracking/);
  expect(new URL(page.url()).searchParams.getAll("company_ids")).toHaveLength(2);
  await expect(page.getByLabel("状态", { exact: true })).toHaveValue("applied");
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(items).toHaveCount(1);
  await expect(page).not.toHaveURL(/page=2/);
  expect(new URL(page.url()).searchParams.getAll("company_ids")).toEqual([id(1001)]);
  await expect(page.getByRole("navigation", { name: "申请分页" })).toHaveCount(0);
  await expect(page.getByText("已在第一页")).toHaveCount(0);
  await expect(page.getByText("1 条申请", { exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("filters-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("filters-mobile.png"), fullPage: true });
  await search.fill("不存在");
  await expect(page.getByText("没有找到公司")).toBeVisible();
  await expect(items).toHaveCount(1);
  await page.getByRole("button", { name: "清除筛选", exact: true }).click();
  await expect(page).toHaveURL(/\/applications$/);
  await expect(items).toHaveCount(20);
  await expect(search).toHaveValue("");
  await expect(page.getByLabel("状态", { exact: true })).toHaveValue("");
  await expect(page.getByRole("list", { name: "已选公司" })).toHaveCount(0);
  await page
    .getByRole("navigation", { name: "申请分页" })
    .getByRole("link", { name: "下一页" })
    .click();
  await expect(page).toHaveURL(/page=2/);
  await page.getByLabel("状态", { exact: true }).selectOption("applied");
  await page.getByRole("button", { name: "清除筛选", exact: true }).click();
  await expect(page).toHaveURL(/\/applications$/);
  await expect(items).toHaveCount(20);
  await expect(page.getByLabel("状态", { exact: true })).toHaveValue("");
});

test("company lookup respects IME and debounce and discards stale responses", async ({ page }) => {
  const queries: string[] = [];
  let releaseOld: (() => void) | undefined;
  await page.route("**/api/product/companies?*", async (route) => {
    const q = new URL(route.request().url()).searchParams.get("q")!;
    queries.push(q);
    if (q === "旧")
      await new Promise<void>((resolve) => {
        releaseOld = resolve;
      });
    await route
      .fulfill({
        json: {
          items: [{ id: id(q === "旧" ? 1001 : 1002), name: `${q}公司` }],
          has_more: false,
          limit: 8,
          offset: 0,
        },
      })
      .catch(() => {});
  });
  await page.goto("/applications");
  const search = page.getByLabel("公司", { exact: true });
  // Confirm hydration through a completed interaction before synthetic IME events.
  await search.fill("就绪");
  await expect(page.getByRole("option", { name: "就绪公司", exact: true })).toBeVisible();
  await search.fill("");
  queries.length = 0;
  await search.dispatchEvent("compositionstart");
  await search.fill("zhong");
  await page.waitForTimeout(450);
  expect(queries).toEqual([]);
  await search.fill("中");
  await search.dispatchEvent("compositionend", { data: "中" });
  await expect(page.getByRole("option", { name: "中公司", exact: true })).toBeVisible();
  expect(queries).toEqual(["中"]);
  await search.fill("旧");
  await expect.poll(() => queries).toContain("旧");
  await search.fill("新");
  await search.fill("最新");
  await expect(page.getByRole("option", { name: "最新公司", exact: true })).toBeVisible();
  releaseOld!();
  await page.waitForTimeout(350);
  expect(queries).toEqual(["中", "旧", "最新"]);
  await expect(page.getByRole("option", { name: "旧公司", exact: true })).toHaveCount(0);
  await expect(page).toHaveURL(/\/applications$/);
  await expect(page.getByRole("list", { name: "申请列表" }).getByRole("listitem")).toHaveCount(20);
});

test("company dropdown anchors without layout shift, supports keyboard and outside dismissal", async ({
  page,
}, info) => {
  await page.goto("/applications");
  const input = page.getByRole("combobox", { name: "公司", exact: true });
  const status = page.getByRole("combobox", { name: "状态", exact: true });
  const panel = page.getByRole("region", { name: "申请筛选" });
  const before = await panel.boundingBox();
  await input.fill("样本");
  const menu = page.getByRole("listbox", { name: "公司候选" });
  await expect(menu).toBeVisible();
  const field = (await input.boundingBox())!,
    box = (await menu.boundingBox())!;
  expect(box.x).toBeCloseTo(field.x, 0);
  expect(box.width).toBeCloseTo(field.width, 0);
  expect(box.y).toBeGreaterThanOrEqual(field.y + field.height);
  expect((await panel.boundingBox())!.height).toEqual(before!.height);
  expect(field.x).toBeLessThan((await status.boundingBox())!.x);
  expect(await menu.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await page.screenshot({ path: info.outputPath("company-dropdown-desktop.png"), fullPage: true });
  await input.press("ArrowDown");
  await input.press("ArrowDown");
  await expect(menu.getByRole("option", { name: "样本公司 2", exact: true })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await input.press("Enter");
  await expect(menu).toHaveCount(0);
  await expect(input).toBeFocused();
  await expect(input).toHaveValue("");
  await expect(page.getByRole("button", { name: "移除样本公司 2" })).toBeVisible();
  await expect(page).toHaveURL(/\/applications$/);
  await input.fill("不存在");
  await expect(menu.getByText("没有找到公司")).toBeVisible();
  await input.press("Escape");
  await expect(menu).toHaveCount(0);
  await input.press("ArrowDown");
  await expect(menu).toBeVisible();
  await page.getByRole("heading", { name: "申请", exact: true }).click();
  await expect(menu).toHaveCount(0);
  await input.focus();
  await expect(menu).toBeVisible();
  await input.press("Tab");
  await expect(status).toBeFocused();
  await expect(menu).toHaveCount(0);
  await input.fill("");
  await expect(menu).toHaveCount(0);
});

test("chips wrap across the panel and the mobile menu leaves filter controls accessible", async ({
  page,
}, info) => {
  await page.goto("/applications");
  await page.setViewportSize({ width: 375, height: 812 });
  const input = page.getByRole("combobox", { name: "公司", exact: true });
  for (const name of ["晨星科技", "远山实验室", "尚无申请公司"]) {
    await input.fill(name);
    await page.getByRole("option", { name, exact: true }).click();
  }
  const chips = page.getByRole("list", { name: "已选公司" });
  const first = (await chips.getByRole("listitem").first().boundingBox())!;
  const last = (await chips.getByRole("listitem").last().boundingBox())!;
  expect(last.y).toBeGreaterThan(first.y);
  expect(first.x).toBeCloseTo((await input.boundingBox())!.x, 0);
  await input.fill("样本");
  const menu = page.getByRole("listbox", { name: "公司候选" });
  await expect(menu).toBeVisible();
  const menuBox = (await menu.boundingBox())!;
  const clear = page.getByRole("button", { name: "清除筛选", exact: true });
  expect(menuBox.x + menuBox.width).toBeLessThanOrEqual((await clear.boundingBox())!.x);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("company-dropdown-mobile.png"), fullPage: true });
  await clear.click();
  await expect(menu).toHaveCount(0);
  await expect(chips).toHaveCount(0);
  await expect(input).toHaveValue("");
});

test("Summary uses the real early-end enum and historical target without dispatch", async ({
  page,
}) => {
  const data = summaryFixture(application(1), job(1));
  await page.route(`**/api/product/applications/${id(1)}/summary`, (route) =>
    route.fulfill({
      json: {
        ...data,
        mock: {
          label: "第 2 次模拟面试",
          href: `/applications/${id(1)}/interview/history?session=${id(8601)}`,
          created_at: application(1).created_at,
          status: "completed",
          completion_type: "user_ended_early",
          stale: true,
        },
      },
    }),
  );
  await page.goto(`/applications/${id(1)}/summary`);
  const card = page.getByRole("region", { name: "最新模拟面试", exact: true });
  await expect(card.getByText("提前结束", { exact: true })).toBeVisible();
  await expect(card.getByText("基于修改前的职位描述", { exact: true })).toBeVisible();
  await expect(card.getByRole("link")).toHaveAttribute(
    "href",
    `/applications/${id(1)}/interview/history?session=${id(8601)}`,
  );
});

test("Summary desktop sizing and closed edit menus", async ({ page }, info) => {
  await page.setViewportSize({ width: 960, height: 900 });
  await page.goto(`/applications/${id(1)}/summary`);
  const jd = page.getByRole("region", { name: "职位描述", exact: true });
  const prep = page.getByRole("region", { name: "最新准备结果", exact: true });
  await expect(jd).toBeVisible();
  const a = await jd.boundingBox(),
    b = await prep.boundingBox();
  expect(a!.y).toBe(b!.y);
  expect(b!.x).toBeGreaterThan(a!.x + a!.width);
  for (const title of await page.locator(".summary-title").all()) {
    await expect(title).toHaveCSS("font-size", "20px");
    await expect(title).toHaveCSS("font-weight", "700");
  }
  await expect(
    page
      .getByRole("region", { name: "申请状态", exact: true })
      .getByText("已投递", { exact: true }),
  ).toHaveCSS("font-size", "16px");
  await expect(
    page
      .getByRole("region", { name: "申请状态", exact: true })
      .getByText("已投递", { exact: true }),
  ).toHaveCSS("font-weight", "400");
  await expect(jd.locator("time")).toHaveCSS("font-size", "14px");
  await expect(prep.getByRole("link").first()).toHaveCSS("font-size", "16px");
  await page.getByRole("button", { name: "添加申请笔记" }).click();
  const notes = page.getByRole("region", { name: "申请笔记", exact: true });
  await expect(notes.getByRole("button", { name: "保存", exact: true })).toBeHidden();
  await notes.getByRole("button", { name: "编辑操作" }).click();
  await expect(page.getByRole("menuitem", { name: "取消", exact: true })).toBeVisible();
  const trigger = notes.getByRole("button", { name: "编辑操作" });
  const menu = page.getByRole("menu", { name: "编辑操作" });
  const triggerBox = (await trigger.boundingBox())!,
    menuBox = (await menu.boundingBox())!;
  expect(Math.abs(menuBox.x + menuBox.width - triggerBox.x - triggerBox.width)).toBeLessThan(2);
  expect(Math.abs(menuBox.y - triggerBox.y - triggerBox.height - 2)).toBeLessThan(2);
  await page.screenshot({ path: info.outputPath("summary-menu-desktop.png"), fullPage: true });
  await notes.getByRole("textbox", { name: "新笔记" }).click();
  await notes.getByRole("textbox", { name: "新笔记" }).fill("输入仍保留");
  await expect(page.getByRole("menuitem", { name: "取消", exact: true })).toBeHidden();
  await expect(notes.getByRole("textbox", { name: "新笔记" })).toHaveValue("输入仍保留");
});

test("Summary edits keep the opposite column still and focus ring inside scrollport", async ({
  page,
}, info) => {
  const summary = summaryFixture(application(1), job(1));
  summary.jd.text = Array.from({ length: 20 }, (_, i) => `职位描述第 ${i + 1} 行`).join("\n");
  const mockRecord = {
    label: "第 2 次模拟面试",
    href: `${`/applications/${id(1)}`}/interview/mock?session=${id(8601)}`,
    created_at: application(1).created_at,
    status: "waiting_answer",
    completion_type: null,
  };
  await page.route(`**/api/product/applications/${id(1)}/summary`, (route) =>
    route.fulfill({ json: { ...summary, mock: mockRecord } }),
  );
  await page.goto(`/applications/${id(1)}/summary`);
  const preview = page
    .getByRole("region", { name: "职位描述", exact: true })
    .locator(".line-clamp-6");
  await expect(preview).toBeVisible();
  expect(
    await preview.evaluate(
      (node) => node.getBoundingClientRect().height / parseFloat(getComputedStyle(node).lineHeight),
    ),
  ).toBeLessThanOrEqual(6);
  const resume = page.getByRole("region", { name: "当前使用简历", exact: true });
  const materials = page.getByRole("region", { name: "最新投递材料", exact: true });
  const status = page.getByRole("region", { name: "申请状态", exact: true });
  await expect(resume).toBeVisible();
  const before = await resume.boundingBox(),
    next = await materials.boundingBox();
  const beforeScroll = await page.evaluate(() => scrollY);
  await status.getByRole("button", { name: "更改", exact: true }).click();
  await expect(status.getByRole("textbox")).toBeVisible();
  expect((await resume.boundingBox())!.height).toBe(before!.height);
  expect((await materials.boundingBox())!.y + (await page.evaluate(() => scrollY))).toBe(
    next!.y + beforeScroll,
  );
  await status.getByRole("button", { name: "取消", exact: true }).click();
  expect((await resume.boundingBox())!.height).toBe(before!.height);
  const mock = page.getByRole("region", { name: "最新模拟面试", exact: true });
  const mockName = (await mock.getByRole("link").boundingBox())!;
  await expect(mock.getByText("进行中", { exact: true })).toHaveCSS("font-size", "14px");
  const mockStatus = (await mock.getByText("进行中", { exact: true }).boundingBox())!;
  expect(mockStatus.x).toBeGreaterThan(mockName.x + mockName.width);
  expect(Math.abs(mockStatus.y - mockName.y)).toBeLessThan(5);
  const rightBefore = (await mock.boundingBox())!.y + (await page.evaluate(() => scrollY));
  await resume.getByRole("button", { name: "更换", exact: true }).click();
  await expect(resume.getByRole("button", { name: "取消", exact: true })).toBeVisible();
  expect((await mock.boundingBox())!.y + (await page.evaluate(() => scrollY))).toBe(rightBefore);
  await page.screenshot({
    path: info.outputPath("summary-independent-columns.png"),
    fullPage: true,
  });
  await resume.getByRole("button", { name: "取消", exact: true }).click();
  const notes = page.getByRole("region", { name: "申请笔记", exact: true });
  await notes.getByRole("button", { name: "添加申请笔记" }).click();
  const text = notes.getByRole("textbox", { name: "新笔记" });
  await expect(text).toBeFocused();
  const bounds = await text.evaluate((node) => {
    let parent = node.parentElement!;
    while (getComputedStyle(parent).overflowY !== "auto") parent = parent.parentElement!;
    const input = node.getBoundingClientRect(),
      scroll = parent.getBoundingClientRect();
    return { left: input.left - scroll.left, right: scroll.right - input.right };
  });
  expect(bounds.left).toBeGreaterThanOrEqual(5);
  expect(bounds.right).toBeGreaterThanOrEqual(5);
  await page.screenshot({ path: info.outputPath("summary-focused.png"), fullPage: true });
  await expect(
    page.getByRole("region", { name: "职位描述", exact: true }).locator(".line-clamp-6"),
  ).toHaveCount(1);
});
