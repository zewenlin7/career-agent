import { test, expect } from "@playwright/test";
import { id } from "../fixtures/product-api";

const root = `/applications/${id(1)}`;
test.beforeEach(async ({ request }) => {
  await request.get("http://127.0.0.1:3111/__reset");
});

for (const [route, action] of [
  ["interview/preparation", "开始面试准备"],
  ["apply/resume", "开始优化"],
  ["apply/greeting", "生成"],
]) {
  test(`${route} keeps sources only at the main generation entry`, async ({ page }) => {
    await page.goto(`${root}/${route}`);
    await page.getByRole("button", { name: action, exact: true }).click();
    if (route === "apply/resume")
      await page.getByRole("button", { name: "取消替换", exact: true }).click();
    const record = page.locator("[data-result-destination]");
    await expect(record.getByRole("button", { name: "调整", exact: true })).toBeVisible();
    await expect(record.locator("p").filter({ hasText: /^基于.*生成$/ })).toHaveCount(0);
    await expect(page.locator("p").filter({ hasText: /^基于.*生成$/ })).toHaveCount(1);
    await expect(page.getByRole("link", { name: "职位描述", exact: true })).toHaveAttribute(
      "href",
      `${root}/research-fit/description?revision=${id(4001)}`,
    );
    await record.getByRole("button", { name: "调整", exact: true }).click();
    await expect(record.locator("p").filter({ hasText: /^基于.*生成$/ })).toHaveCount(0);
    await expect(page.locator("p").filter({ hasText: /^基于.*生成$/ })).toHaveCount(1);
  });
}

test("the same exact research has one name in generation sources and record selectors", async ({
  page,
}) => {
  await page.route(
    `**/api/product/companies/${id(1001)}/research/current?mode=live`,
    async (route) => {
      const response = await route.fetch({
        url: route.request().url().replace("mode=live", "mode=fixture"),
      });
      await route.fulfill({ response });
    },
  );
  await page.goto(`${root}/apply/greeting`);
  const href = `${root}/research-fit/company?research=${id(7999)}`;
  const source = page.locator(`a[href="${href}"]`);
  await expect(source).toHaveText("晨星科技 · 2026-10-24 12:00");
  const name = await source.textContent();
  await source.click();
  await expect(page.getByLabel("研究记录", { exact: true })).toHaveValue(id(7999));
  await expect(page.getByLabel("研究记录", { exact: true }).locator("option:checked")).toHaveText(
    name!,
  );
  await page.reload();
  await expect(page.getByLabel("研究记录", { exact: true }).locator("option:checked")).toHaveText(
    name!,
  );
});
