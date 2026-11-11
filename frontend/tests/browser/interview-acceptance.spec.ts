import { test, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { id } from "../fixtures/product-api";
const root = `/applications/${id(1)}`;
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});
test("Interview full-page roles, settings, management and narrow layouts", async ({
  page,
}, info) => {
  const styles: Record<string, unknown> = {};
  const role = (selector: string) =>
    page
      .locator(selector)
      .first()
      .evaluate((n) => {
        const s = getComputedStyle(n);
        return { size: s.fontSize, weight: s.fontWeight, line: s.lineHeight, color: s.color };
      });
  await page.goto(`${root}/research-fit/company`);
  await expect(page.getByText("公司提供数据服务。", { exact: true })).toBeVisible();
  const referenceTitle = await role("h1"),
    referenceSection = await role("article h3"),
    referenceBody = await role("article > section > ul > li > p");

  for (const [route, title] of [
    ["research-fit/company", "公司研究"],
    ["research-fit/fit", "岗位匹配"],
    ["apply/greeting", "招呼语"],
    ["apply/resume", "简历优化"],
    ["interview/preparation", "面试准备"],
    ["interview/mock", "模拟面试"],
    ["interview/actual", "记录真实面试"],
    ["interview/history", "历史面试"],
  ]) {
    await page.setViewportSize({ width: 1280, height: 900 });
    if (route === "interview/history")
      await page.route(`**/api/product/interviews/${id(8701)}`, async (request) => {
        const response = await request.fetch();
        const record = await response.json();
        record.round_name = "1";
        record.entries[0].question = "长链接问题 https://example.com/" + "question".repeat(25);
        record.entries[0].answer = "完整回答 " + "LongAnswerWithoutSpaces".repeat(25);
        record.notes = [{ text: "补充笔记独立于问答展示。", recorded_at: record.created_at }];
        await request.fulfill({ json: record });
      });
    await page.goto(
      `${root}/${route}${route === "interview/history" ? `?actual=${id(8701)}` : ""}`,
    );
    await expect(page.getByRole("heading", { name: title, exact: true }).first()).toBeVisible();
    if (route === "research-fit/fit") {
      await page.getByLabel("简历", { exact: true }).selectOption(id(8401));
      await page.getByRole("button", { name: "开始匹配", exact: true }).click();
      await expect(page.getByRole("heading", { name: "不确定", exact: true })).toBeVisible();
    }
    if (["apply/greeting", "apply/resume", "interview/preparation"].includes(route)) {
      await page.getByRole("button", { name: /^(开始优化|生成|开始面试准备)$/ }).click();
      if (route === "apply/resume")
        await page.getByRole("button", { name: "取消替换", exact: true }).click();
      await expect(
        page.getByRole("button", { name: /^(开始优化|生成|开始面试准备)$/ }),
      ).toBeEnabled();
    }
    if (route === "interview/actual") {
      await page.getByRole("button", { name: "新增记录", exact: true }).click();
      await page.getByRole("button", { name: "添加问题", exact: true }).click();
      await page
        .getByPlaceholder("输入问题")
        .fill("问题含长链接 https://example.com/" + "long".repeat(30));
    }
    if (route === "interview/history") {
      await expect(page.getByRole("heading", { name: "笔记", exact: true })).toBeVisible();
      await expect(page.getByText("补充笔记独立于问答展示。", { exact: true })).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "晨星科技 · 后端工程师 · 第1轮 · 技术", exact: true }),
      ).toBeVisible();
    }
    if (route === "interview/preparation") {
      await expect(page.getByLabel("公司研究", { exact: true })).toHaveValue("none");
      await expect(page.getByRole("option", { name: "最新可用研究" })).toHaveCount(0);
    }
    if (["research-fit/company", "research-fit/fit", "interview/preparation"].includes(route)) {
      const del = page.getByRole("button", { name: "删除记录", exact: true });
      await expect(del).toBeVisible();
      await expect(del.locator("..").getByRole("heading")).toHaveCount(1);
      await expect(del).toHaveCSS("color", "rgb(145, 32, 24)");
    }
    if (route.startsWith("interview/")) expect(await role("h1")).toEqual(referenceTitle);
    if (route === "interview/preparation") {
      for (const h of await page.locator("[data-result-destination] h3").all())
        expect(
          await h.evaluate((n) => {
            const s = getComputedStyle(n);
            return { size: s.fontSize, weight: s.fontWeight, line: s.lineHeight, color: s.color };
          }),
        ).toEqual(referenceSection);
      expect(await role("[data-result-destination] article article p")).toEqual(referenceBody);
      const bodies: Record<string, unknown>[] = [];
      page.on("request", (r) => {
        if (r.method() === "POST" && r.url().endsWith("/api/product/operations"))
          bodies.push(r.postDataJSON());
      });
      await page.getByRole("button", { name: "开始面试准备", exact: true }).click();
      await expect(page.getByRole("button", { name: "开始面试准备", exact: true })).toBeEnabled();
      expect(bodies.at(-1)).toMatchObject({
        request: { use_company_research: false, research_report_id: null },
      });
    }
    if (route === "interview/mock") {
      const focus = await page.getByLabel("练习重点", { exact: true }).boundingBox();
      const mode = await page.getByLabel("问题数量模式", { exact: true }).boundingBox();
      expect(Math.abs(focus!.y - mode!.y)).toBeLessThan(2);
      const group = await page
        .getByLabel("练习重点", { exact: true })
        .locator("../..")
        .boundingBox();
      expect(Math.abs(group!.x + group!.width / 2 - 640)).toBeLessThan(2);
      for (const name of ["练习重点", "问题数量模式"]) {
        const select = page.getByLabel(name, { exact: true });
        const box = await select.boundingBox();
        const label = await select.locator("..").locator("label").boundingBox();
        expect(Math.abs(box!.y + box!.height / 2 - label!.y - label!.height / 2)).toBeLessThan(2);
        await expect(select).toHaveCSS("font-weight", "400");
      }
    }
    if (route === "interview/preparation") {
      const selector = page.getByLabel("公司研究", { exact: true });
      // Read both rectangles in one frame: result adoption may scroll between awaits.
      const { group, start } = await selector.evaluate((select) => {
        const group = select.parentElement!.getBoundingClientRect();
        const button = [...document.querySelectorAll("button")].find(
          (node) => node.textContent === "开始面试准备",
        )!;
        const start = button.getBoundingClientRect();
        return { group: group.toJSON(), start: start.toJSON() };
      });
      expect(Math.abs(group!.x + group!.width / 2 - 640)).toBeLessThan(2);
      expect(start!.y).toBeGreaterThan(group!.y + group!.height);
    }
    expect(
      await page
        .locator("select,select option")
        .evaluateAll((nodes) => nodes.every((n) => getComputedStyle(n).fontWeight === "400")),
    ).toBe(true);
    styles[route] = await page
      .locator("h1,h2,h3,h4,label,select,option,p,li")
      .evaluateAll((nodes) =>
        nodes.map((n) => {
          const s = getComputedStyle(n);
          return {
            tag: n.tagName,
            text: (n.textContent || "").slice(0, 70),
            size: s.fontSize,
            weight: s.fontWeight,
            line: s.lineHeight,
            color: s.color,
            family: s.fontFamily,
          };
        }),
      );
    await page.screenshot({
      path: info.outputPath(route.replaceAll("/", "-") + "-desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 375, height: 812 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.screenshot({
      path: info.outputPath(route.replaceAll("/", "-") + "-375.png"),
      fullPage: true,
    });
  }
  const stylesPath = info.outputPath("role-styles.json");
  await writeFile(stylesPath, JSON.stringify(styles, null, 2));
  await info.attach("role-styles.json", {
    path: stylesPath,
    contentType: "application/json",
  });
});
test("Actual unified text time, ownership controls and cancel destinations", async ({ page }) => {
  await page.goto(`${root}/interview/actual`);
  await page.getByRole("button", { name: "新增记录", exact: true }).click();
  await expect(page.getByText("← 返回操作选择", { exact: true })).toHaveCount(0);
  const time = page.getByPlaceholder("YYYY-MM-DD HH:mm");
  await time.fill("2026-11-07 14:25");
  await expect(time).toHaveValue("2026-11-07 14:25");
  await page.getByRole("button", { name: "添加问题", exact: true }).click();
  await page.getByPlaceholder("输入问题").fill("测试问题");
  await expect(page.getByLabel("归属", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "调整归属", exact: true }).click();
  await expect(page.getByLabel("归属", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
  await expect(page.getByRole("button", { name: "新增记录", exact: true })).toBeVisible();
});

test("record removal rejection is a dismissible centered dialog for all three result kinds", async ({
  page,
}) => {
  for (const route of ["research-fit/company", "research-fit/fit", "interview/preparation"]) {
    await page.goto(`${root}/${route}`);
    if (route === "research-fit/fit") {
      await page.getByLabel("简历", { exact: true }).selectOption(id(8401));
      await page.getByRole("button", { name: "开始匹配", exact: true }).click();
    }
    if (route === "interview/preparation")
      await page.getByRole("button", { name: "开始面试准备", exact: true }).click();
    await page.route("**/api/product/**", async (r) => {
      if (r.request().method() === "DELETE")
        await r.fulfill({ json: { deleted: false, used_by: ["面试准备（2026-11-07 09:30）"] } });
      else await r.fallback();
    });
    await page.getByRole("button", { name: "删除记录", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "确定", exact: true }).click();
    const notice = page.getByRole("dialog", { name: "无法删除记录", exact: true });
    await expect(notice).toContainText("面试准备（2026-11-07 09:30）");
    const rect = await notice.boundingBox();
    const viewport = page.viewportSize()!;
    expect(Math.abs(rect!.x + rect!.width / 2 - viewport.width / 2)).toBeLessThan(2);
    await notice.getByRole("button", { name: "知道了", exact: true }).click();
    await expect(notice).not.toBeVisible();
    await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
  }
});
